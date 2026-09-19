"""Turn a retrieved static model into OPM Flow GRID and PROPS input.

The counterpart to building a model from scratch: somebody has already built a
geo/simulation grid, and the task is to get it into a deck without corrupting
it in transit. That is mostly validation, because the ways this goes wrong are
quiet ones -- an array of the wrong length still writes, a zero-based region
array still runs, a fraction stored in percent still initialises.

Plant-agnostic, offline, no dependency beyond the standard library. It accepts
arrays from any source (RESQML via a data platform, an RMS export, a CSV) and
refuses to write anything it cannot justify.

Cell ordering is Eclipse ordering throughout: I fastest, then J, then K.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence

#: Written into the GRID section.
GRID_KEYWORDS = ("PORO", "PERMX", "PERMY", "PERMZ", "NTG", "ACTNUM", "MULTNUM")

#: Written into the REGIONS section. Eclipse region indices are one-based.
REGION_KEYWORDS = ("SATNUM", "EQLNUM", "FIPNUM", "PVTNUM", "MULTNUM", "ROCKNUM")

#: Without these the deck cannot be run.
REQUIRED_KEYWORDS = ("PORO", "PERMX")

#: Physical bounds a deck array must satisfy. ``None`` means unbounded.
KEYWORD_BOUNDS: dict[str, dict[str, Any]] = {
    "PORO": {"low": 0.0, "high": 1.0, "unit": "fraction", "integer": False},
    "NTG": {"low": 0.0, "high": 1.0, "unit": "fraction", "integer": False},
    "SWAT": {"low": 0.0, "high": 1.0, "unit": "fraction", "integer": False},
    "SWL": {"low": 0.0, "high": 1.0, "unit": "fraction", "integer": False},
    "PERMX": {"low": 0.0, "high": None, "unit": "mD", "integer": False},
    "PERMY": {"low": 0.0, "high": None, "unit": "mD", "integer": False},
    "PERMZ": {"low": 0.0, "high": None, "unit": "mD", "integer": False},
    "ACTNUM": {"low": 0, "high": 1, "unit": "flag", "integer": True},
    "SATNUM": {"low": 1, "high": None, "unit": "index", "integer": True},
    "EQLNUM": {"low": 1, "high": None, "unit": "index", "integer": True},
    "FIPNUM": {"low": 1, "high": None, "unit": "index", "integer": True},
    "PVTNUM": {"low": 1, "high": None, "unit": "index", "integer": True},
    "MULTNUM": {"low": 1, "high": None, "unit": "index", "integer": True},
    "ROCKNUM": {"low": 1, "high": None, "unit": "index", "integer": True},
}

#: Each entry is a mistake that produces a deck which RUNS and is wrong.
SILENT_FAILURE_MODES: tuple[dict[str, str], ...] = (
    {
        "mode": "array length not equal to nx*ny*nz",
        "why_quiet": (
            "A short array is padded or a long one truncated by the reader, so "
            "the run starts and every cell after the mismatch holds a value "
            "belonging to a different cell."
        ),
        "guard": "validate_array() compares length against the declared grid.",
    },
    {
        "mode": "zero-based region array",
        "why_quiet": (
            "Eclipse region indices are one-based. A zero from a geomodel is "
            "read as an out-of-range region and the cell silently falls into "
            "region 1, mixing rock types."
        ),
        "guard": "validate_array() rejects region index 0 and offers rebase_regions().",
    },
    {
        "mode": "porosity or NTG stored in percent",
        "why_quiet": (
            "A run with PORO of 32 initialises and reports a pore volume ~100x "
            "too large. Nothing errors; the profile is simply wrong."
        ),
        "guard": "Bounds check on the fraction keywords.",
    },
    {
        "mode": "KLOGH used for PERMZ as well as PERMX",
        "why_quiet": (
            "Vertical permeability equal to horizontal removes the barrier to "
            "coning and gravity segregation. The model is optimistic, not broken."
        ),
        "guard": "PERMZ must be supplied or an explicit kv/kh ratio declared.",
    },
    {
        "mode": "inactive cells carrying an undefined value",
        "why_quiet": (
            "A sentinel such as -999 in an inactive cell is harmless until "
            "ACTNUM is regenerated from a different source."
        ),
        "guard": "validate_array() reports non-finite and sentinel-like values.",
    },
)


@dataclass(frozen=True)
class GridDimensions:
    """The IJK grid an array set belongs to."""

    nx: int
    ny: int
    nz: int
    source: Optional[str] = None

    @property
    def cell_count(self) -> int:
        return int(self.nx) * int(self.ny) * int(self.nz)

    def as_dict(self) -> dict[str, Any]:
        return {"nx": self.nx, "ny": self.ny, "nz": self.nz,
                "cell_count": self.cell_count, "source": self.source}


@dataclass
class StaticModelArrays:
    """Cell arrays keyed by Eclipse keyword, with the grid they belong to."""

    grid: GridDimensions
    arrays: dict[str, Sequence[float]] = field(default_factory=dict)
    units: dict[str, str] = field(default_factory=dict)
    provenance: dict[str, str] = field(default_factory=dict)

    def add(self, keyword: str, values: Sequence[float], *,
            unit: Optional[str] = None, source: Optional[str] = None) -> "StaticModelArrays":
        key = str(keyword).strip().upper()
        self.arrays[key] = list(values)
        if unit:
            self.units[key] = unit
        if source:
            self.provenance[key] = source
        return self


def _sentinel_like(value: float) -> bool:
    return value in (-999.0, -999.25, -9999.0, 9999.0, 1e30, -1e30)


def validate_array(
    keyword: str,
    values: Sequence[float],
    grid: GridDimensions,
    *,
    unit: Optional[str] = None,
) -> dict[str, Any]:
    """Check one cell array against the grid and the keyword's physical bounds."""
    key = str(keyword).strip().upper()
    data = list(values or [])
    issues: list[dict[str, str]] = []

    if len(data) != grid.cell_count:
        issues.append({
            "severity": "blocking",
            "detail": (
                f"{key} has {len(data)} values but the grid has "
                f"{grid.cell_count} cells ({grid.nx}x{grid.ny}x{grid.nz}). A "
                "length mismatch misaligns every subsequent cell."
            ),
        })

    finite = [v for v in data if isinstance(v, (int, float)) and math.isfinite(v)]
    non_finite = len(data) - len(finite)
    if non_finite:
        issues.append({
            "severity": "blocking",
            "detail": f"{key} contains {non_finite} non-finite value(s).",
        })

    sentinels = sum(1 for v in finite if _sentinel_like(float(v)))
    if sentinels:
        issues.append({
            "severity": "warning",
            "detail": (
                f"{key} contains {sentinels} value(s) that look like undefined "
                "sentinels. Confirm they sit only in inactive cells."
            ),
        })

    bounds = KEYWORD_BOUNDS.get(key)
    low = min(finite) if finite else None
    high = max(finite) if finite else None
    if bounds and finite:
        if bounds["low"] is not None and low < bounds["low"]:
            issues.append({
                "severity": "blocking",
                "detail": (
                    f"{key} minimum {low} is below the physical floor "
                    f"{bounds['low']} ({bounds['unit']})."
                    + (" Eclipse region indices are one-based; a 0 is not a region."
                       if key in REGION_KEYWORDS else "")
                ),
            })
        if bounds["high"] is not None and high > bounds["high"]:
            issues.append({
                "severity": "blocking",
                "detail": (
                    f"{key} maximum {high} exceeds {bounds['high']} "
                    f"({bounds['unit']}). A fraction stored in percent "
                    "initialises without error and is wrong by ~100x."
                ),
            })
        if bounds["integer"] and any(float(v) != int(v) for v in finite):
            issues.append({
                "severity": "blocking",
                "detail": f"{key} is an integer keyword but holds non-integer values.",
            })

    return {
        "keyword": key,
        "count": len(data),
        "expected_count": grid.cell_count,
        "min": low,
        "max": high,
        "declared_unit": unit,
        "expected_unit": (bounds or {}).get("unit"),
        "issues": issues,
        "usable": not any(i["severity"] == "blocking" for i in issues),
    }


def rebase_regions(values: Sequence[int]) -> dict[str, Any]:
    """Shift a zero-based region array to Eclipse's one-based convention.

    Returns the shift applied so it appears in the provenance rather than
    happening invisibly.
    """
    data = [int(v) for v in values or []]
    if not data:
        return {"values": [], "shift": 0, "note": "Empty array; nothing to rebase."}
    shift = 1 if min(data) == 0 else 0
    return {
        "values": [v + shift for v in data],
        "shift": shift,
        "note": (
            "Rebased from zero-based to one-based region indices."
            if shift else "Already one-based; unchanged."
        ),
    }


def derive_permz(
    permx: Sequence[float],
    *,
    kv_kh: float,
) -> dict[str, Any]:
    """Derive PERMZ from PERMX and an explicit kv/kh ratio.

    There is no default ratio: leaving PERMZ equal to PERMX is an optimistic
    model, so the assumption has to be stated by the caller.
    """
    if not (0.0 < float(kv_kh) <= 1.0):
        raise ValueError(
            f"kv_kh must be in (0, 1]; got {kv_kh}. A ratio above 1 means "
            "vertical permeability exceeds horizontal, which needs its own "
            "justification."
        )
    ratio = float(kv_kh)
    return {
        "values": [float(v) * ratio for v in permx],
        "kv_kh": ratio,
        "provenance": f"derived: PERMZ = {ratio} x PERMX (assumed kv/kh)",
    }


def _format_values(values: Sequence[float], *, integer: bool, per_line: int = 8) -> list[str]:
    lines: list[str] = []
    row: list[str] = []
    for value in values:
        row.append(str(int(value)) if integer else f"{float(value):.6g}")
        if len(row) == per_line:
            lines.append("  " + " ".join(row))
            row = []
    if row:
        lines.append("  " + " ".join(row))
    return lines


def write_keyword_include(
    keyword: str,
    values: Sequence[float],
    *,
    comment: Optional[str] = None,
) -> str:
    """Render one keyword as an OPM Flow INCLUDE file body."""
    key = str(keyword).strip().upper()
    integer = bool(KEYWORD_BOUNDS.get(key, {}).get("integer"))
    header = [f"-- {key}"]
    if comment:
        header.extend(f"-- {line}" for line in str(comment).splitlines())
    body = _format_values(values, integer=integer)
    return "\n".join(header + [key] + body + ["/", ""])


def build_static_model_deck_input(
    model: StaticModelArrays,
    *,
    kv_kh: Optional[float] = None,
    rebase_zero_based_regions: bool = False,
) -> dict[str, Any]:
    """Validate a retrieved static model and render its GRID/PROPS includes.

    Returns ``deck_writable=False`` with reasons rather than emitting a deck
    that runs and is wrong. Nothing is silently corrected: a region rebase or a
    derived PERMZ appears in ``adjustments`` and in the include-file comment.
    """
    grid = model.grid
    validations: list[dict[str, Any]] = []
    adjustments: list[dict[str, Any]] = []
    arrays = dict(model.arrays)

    if rebase_zero_based_regions:
        for key in list(arrays):
            if key in REGION_KEYWORDS:
                rebased = rebase_regions(arrays[key])
                if rebased["shift"]:
                    arrays[key] = rebased["values"]
                    adjustments.append({"keyword": key, "action": "rebase_regions",
                                        **{k: rebased[k] for k in ("shift", "note")}})

    if "PERMZ" not in arrays and "PERMX" in arrays and kv_kh is not None:
        derived = derive_permz(arrays["PERMX"], kv_kh=kv_kh)
        arrays["PERMZ"] = derived["values"]
        model.provenance["PERMZ"] = derived["provenance"]
        adjustments.append({"keyword": "PERMZ", "action": "derive_permz",
                            "kv_kh": derived["kv_kh"]})

    if "PERMY" not in arrays and "PERMX" in arrays:
        arrays["PERMY"] = list(arrays["PERMX"])
        model.provenance.setdefault("PERMY", "copied from PERMX (isotropic in plan)")
        adjustments.append({"keyword": "PERMY", "action": "copy_from_permx",
                            "note": "Areal isotropy assumed."})

    for key in sorted(arrays):
        validations.append(
            validate_array(key, arrays[key], grid, unit=model.units.get(key))
        )

    missing = [kw for kw in REQUIRED_KEYWORDS if kw not in arrays]
    blocking = [v for v in validations if not v["usable"]]

    reasons: list[str] = []
    if missing:
        reasons.append(f"required keyword(s) absent: {missing}")
    if blocking:
        reasons.append(
            f"{len(blocking)} array(s) failed validation: "
            f"{[v['keyword'] for v in blocking]}"
        )
    if "PERMZ" not in arrays:
        reasons.append(
            "PERMZ is neither supplied nor derived. Supply it, or pass kv_kh to "
            "state the vertical-permeability assumption explicitly."
        )

    includes: dict[str, str] = {}
    if not reasons:
        for key in sorted(arrays):
            includes[f"{key.lower()}.inc"] = write_keyword_include(
                key, arrays[key], comment=model.provenance.get(key)
            )
        includes["specgrid.inc"] = (
            "-- SPECGRID\nSPECGRID\n"
            f"  {grid.nx} {grid.ny} {grid.nz} 1 F /\n"
        )

    return {
        "grid": grid.as_dict(),
        "keywords_present": sorted(arrays),
        "missing_required_keywords": missing,
        "validations": validations,
        "adjustments": adjustments,
        "provenance": dict(model.provenance),
        "deck_writable": not reasons,
        "blocked_because": reasons or None,
        "include_files": includes,
        "geometry_note": (
            "SPECGRID declares the dimensions only. COORD and ZCORN carry the "
            "corner-point geometry and must come from the source grid; they "
            "cannot be reconstructed from cell arrays."
        ),
        "silent_failure_modes": [dict(mode) for mode in SILENT_FAILURE_MODES],
    }


def reconcile_volume(
    *,
    computed_stoiip_m3: float,
    reported_p50_m3: float,
    reported_p10_m3: Optional[float] = None,
    reported_p90_m3: Optional[float] = None,
    tolerance_fraction: float = 0.15,
) -> dict[str, Any]:
    """Check a rebuilt in-place volume against the reported one.

    The one test that catches a transit error the array checks cannot: unit,
    ordering and contact mistakes all move the volume.
    """
    computed = float(computed_stoiip_m3)
    reported = float(reported_p50_m3)
    if reported == 0:
        raise ValueError("reported_p50_m3 must be non-zero to form a ratio.")
    ratio = computed / reported
    deviation = abs(ratio - 1.0)
    within_range = None
    if reported_p90_m3 is not None and reported_p10_m3 is not None:
        low, high = sorted((float(reported_p90_m3), float(reported_p10_m3)))
        within_range = low <= computed <= high

    record = {
        "computed_m3": computed,
        "reported_p50_m3": reported,
        "ratio": ratio,
        "deviation_fraction": deviation,
        "tolerance_fraction": float(tolerance_fraction),
        "within_p90_p10": within_range,
        "match": deviation <= float(tolerance_fraction),
    }
    if not record["match"]:
        record["diagnosis"] = (
            "A rebuilt volume this far from the reported one is usually a "
            "transit error, not geology. Check in order: a fraction stored in "
            "percent (~100x), a bulk-volume unit (m3 vs rm3), the fluid contact "
            "depth reference (TVD vs TVDSS), and whether NTG was already "
            "included in the porosity."
        )
    return record


def static_model_checklist() -> list[dict[str, str]]:
    """The checks to run before a retrieved model is trusted in a deck."""
    return [
        {"check": "grid identity",
         "detail": "Every array belongs to ONE grid. Arrays from a geo grid and a "
                   "simulation grid have different cell counts and orderings."},
        {"check": "array length",
         "detail": "len(array) == nx*ny*nz for every keyword."},
        {"check": "units",
         "detail": "Fractions in [0,1], permeability in mD, and a declared unit "
                   "for each. A dimensionless label on a physical quantity is a "
                   "defect, not a default."},
        {"check": "region base",
         "detail": "Region indices are one-based. A zero-based array is a "
                   "different model."},
        {"check": "vertical permeability",
         "detail": "PERMZ supplied, or kv/kh stated. Never left equal to PERMX "
                   "by omission."},
        {"check": "geometry",
         "detail": "COORD and ZCORN come from the source grid; SPECGRID alone "
                   "is not a geometry."},
        {"check": "volume reconciliation",
         "detail": "Rebuilt in-place volume compared against the reported P50, "
                   "and inside P90-P10 where those are published."},
    ]
