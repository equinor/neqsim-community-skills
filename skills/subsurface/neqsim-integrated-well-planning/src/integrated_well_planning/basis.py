"""Planning-basis loading, templates and fail-closed validation.

The planning basis is a dictionary (YAML or JSON) following ``iwp_planning_basis.v1``. Scalars that
carry uncertainty are written as ``{low, base, high}``. The ``provenance`` map attaches a class
(SUPPLIED / MEASURED / FITTED / CALCULATED / ASSUMED) and source to dotted paths.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .registers import PROVENANCE_CLASSES, Registers, get_path, registers_from_basis

WELL_TYPES = (
    "oil_producer",
    "gas_producer",
    "gas_condensate_producer",
    "water_injector",
    "gas_injector",
)
ENVIRONMENTS = ("onshore", "platform", "subsea")
MATURITIES = (
    "concept",
    "selection",
    "detailed_engineering_support",
    "operating_well_evaluation",
)
CASES = ("low", "base", "high")
PRODUCER_TYPES = ("oil_producer", "gas_producer", "gas_condensate_producer")
INJECTOR_TYPES = ("water_injector", "gas_injector")

COMMON_REQUIRED = [
    "study.id",
    "study.maturity",
    "well.type",
    "well.environment",
    "datums.reference_elevation_msl_m",
    "trajectory.md_m",
    "trajectory.tvd_m",
    "reservoir.pressure_bara",
    "reservoir.temperature_C",
    "fluid.components",
    "completion.tubing.id_m",
    "facility.host_pressure_bara",
    "targets.rate",
]
PRODUCER_REQUIRED = [
    "reservoir.permeability_md",
    "reservoir.thickness_m",
    "reservoir.skin",
    "reservoir.drainage_radius_m",
]
INJECTOR_REQUIRED = [
    "reservoir.permeability_md",
    "reservoir.thickness_m",
    "reservoir.skin",
    "reservoir.drainage_radius_m",
    "reservoir.fracture_gradient_bar_per_m",
]
PROVENANCE_EXEMPT = {"study.id", "study.maturity", "well.type", "well.environment"}
IMPORTANT_OPTIONAL = {
    "fluid.pvt_measurements": (
        "no laboratory PVT supplied",
        "EOS is uncalibrated; saturation pressure, GOR and viscosity carry EOS error",
    ),
    "fluid.water_chemistry": (
        "no water analysis supplied",
        "scale, compatibility and corrosion assessments are NOT_PERFORMED",
    ),
    "operations.life_years": (
        "operating life not stated",
        "life-cycle load cases and intervention strategy cannot be sized",
    ),
    "operations.abandonment": (
        "abandonment requirement not stated",
        "abandonment barrier state is a placeholder",
    ),
    "limits": (
        "no approved operating limits supplied",
        "operating-envelope rows are NEEDS_REVIEW until limits with sources are supplied",
    ),
    "drilling.hazards": (
        "no geological hazard list supplied",
        "drilling interface specification stays unresolved",
    ),
    "standards.jurisdiction": (
        "jurisdiction and governing requirements not identified",
        "standards register stays TO_VERIFY",
    ),
}


@dataclass
class ValidationReport:
    """Result of :func:`validate_basis`."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    gaps: list[dict[str, str]] = field(default_factory=list)

    @property
    def status(self) -> str:
        """FAIL when any error, WARN when warnings/gaps, else PASS."""
        if self.errors:
            return "FAIL"
        return "WARN" if (self.warnings or self.gaps) else "PASS"

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly dictionary."""
        return {
            "status": self.status,
            "errors": self.errors,
            "warnings": self.warnings,
            "gaps": self.gaps,
        }


def load_basis(path: Path) -> dict[str, Any]:
    """Load a planning basis from YAML or JSON."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        import yaml

        return yaml.safe_load(text)
    return json.loads(text)


def save_basis(basis: dict[str, Any], path: Path) -> None:
    """Write a planning basis as YAML or JSON (by suffix)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() in (".yaml", ".yml"):
        import yaml

        path.write_text(
            yaml.safe_dump(basis, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
    else:
        path.write_text(json.dumps(basis, indent=2), encoding="utf-8")


def rng(
    value: Any, key_order: tuple[str, str, str] = CASES
) -> tuple[float, float, float]:
    """Return (low, base, high) from a scalar or a {low, base, high} mapping.

    Raises:
        ValueError: if the value is missing/non-numeric or low > high.
    """
    if value is None:
        raise ValueError("missing value")
    if isinstance(value, dict):
        base = value.get("base")
        low = value.get("low", base)
        high = value.get("high", base)
        if base is None:
            raise ValueError("range needs a base value")
    else:
        low = base = high = value
    low, base, high = float(low), float(base), float(high)
    if not (low <= base <= high):
        raise ValueError(
            f"range must satisfy low <= base <= high, got {low} {base} {high}"
        )
    return low, base, high


def case_value(value: Any, case: str) -> float:
    """Pick the low/base/high value of a range-or-scalar for a case name."""
    low, base, high = rng(value)
    return {"low": low, "base": base, "high": high}[case]


def _is_missing(basis: dict[str, Any], path: str) -> bool:
    v = get_path(basis, path)
    return v is None or v == [] or v == {}


def validate_basis(
    basis: dict[str, Any], strict_provenance: bool = False
) -> ValidationReport:
    """Fail-closed validation of a planning basis.

    Errors block any calculation. Warnings and gaps do not block but must be carried into the report.
    """
    rep = ValidationReport()
    if basis.get("schema") != "iwp_planning_basis.v1":
        rep.errors.append("schema must be 'iwp_planning_basis.v1'")
    wtype = get_path(basis, "well.type")
    env = get_path(basis, "well.environment")
    if wtype not in WELL_TYPES:
        rep.errors.append(f"well.type must be one of {WELL_TYPES}")
    if env not in ENVIRONMENTS:
        rep.errors.append(f"well.environment must be one of {ENVIRONMENTS}")
    if get_path(basis, "study.maturity") not in MATURITIES:
        rep.errors.append(f"study.maturity must be one of {MATURITIES}")

    required = list(COMMON_REQUIRED)
    if wtype in PRODUCER_TYPES:
        required += PRODUCER_REQUIRED
    if wtype in INJECTOR_TYPES:
        required += INJECTOR_REQUIRED
    for path in required:
        if _is_missing(basis, path):
            rep.errors.append("required input missing: " + path)

    for path in (
        "reservoir.pressure_bara",
        "facility.host_pressure_bara",
        "targets.rate",
        "reservoir.permeability_md",
        "reservoir.thickness_m",
    ):
        v = get_path(basis, path)
        if v is not None:
            try:
                low, _base, high = rng(
                    v
                    if path != "targets.rate"
                    else (v.get("values", v) if isinstance(v, dict) else v)
                )
                if low <= 0:
                    rep.errors.append(f"{path} must be positive")
            except (ValueError, TypeError, AttributeError) as exc:
                rep.errors.append(f"{path}: {exc}")

    t_res = get_path(basis, "reservoir.temperature_C")
    if isinstance(t_res, (int, float)) and not (-20.0 <= t_res <= 260.0):
        rep.errors.append(
            f"reservoir.temperature_C {t_res} outside -20..260 C (check units: Celsius expected)"
        )

    comps = get_path(basis, "fluid.components") or []
    if comps:
        try:
            total = sum(float(c["mole_fraction"]) for c in comps)
            if abs(total - 1.0) > 0.01:
                rep.errors.append(
                    f"fluid composition sums to {total:.4f}, expected 1.0 (+-0.01)"
                )
        except (KeyError, TypeError, ValueError):
            rep.errors.append(
                "fluid.components entries need name and numeric mole_fraction"
            )

    md, tvd = get_path(basis, "trajectory.md_m"), get_path(basis, "trajectory.tvd_m")
    if isinstance(md, (int, float)) and isinstance(tvd, (int, float)):
        if tvd > md + 1e-6:
            rep.errors.append("trajectory.tvd_m exceeds md_m")
        if get_path(basis, "reservoir.datum_tvd_m") is None and tvd <= 0:
            rep.errors.append("trajectory.tvd_m must be positive")

    for key in ("standard_conditions",):
        if get_path(basis, "datums." + key) is None:
            rep.warnings.append(
                f"datums.{key} not stated; defaulting to 15 C / 1.01325 bara"
            )
    if get_path(basis, "datums.pressure_reference") is None:
        rep.warnings.append(
            "datums.pressure_reference not stated; all pressures are read as bara"
        )

    for path, (desc, consequence) in IMPORTANT_OPTIONAL.items():
        if _is_missing(basis, path):
            rep.gaps.append(
                {
                    "key": path,
                    "description": desc,
                    "consequence": consequence,
                    "severity": "MAJOR" if path in ("limits",) else "MINOR",
                }
            )

    prov = basis.get("provenance") or {}
    synthetic = bool(get_path(basis, "study.synthetic"))
    for path, meta in prov.items():
        cls = meta.get("class")
        if cls not in PROVENANCE_CLASSES:
            rep.errors.append(f"provenance[{path}]: class '{cls}' invalid")
            continue
        if cls == "MEASURED" and synthetic:
            rep.errors.append(
                f"provenance[{path}]: MEASURED not allowed in a synthetic study"
            )
        if cls in ("SUPPLIED", "MEASURED", "FITTED") and not meta.get("source"):
            rep.errors.append(f"provenance[{path}]: {cls} requires a source")
        if get_path(basis, path) is None:
            rep.warnings.append(
                f"provenance[{path}] points at a path that does not exist"
            )
    for path in required:
        if (
            path not in prov
            and not _is_missing(basis, path)
            and path not in PROVENANCE_EXEMPT
        ):
            msg = f"no provenance recorded for {path}"
            (rep.errors if strict_provenance else rep.warnings).append(msg)
    assumed = [p for p, m in prov.items() if m.get("class") == "ASSUMED"]
    if assumed and not synthetic:
        rep.warnings.append(
            "{} ASSUMED inputs in a non-synthetic study: {}".format(
                len(assumed), ", ".join(assumed[:6])
            )
        )
    if synthetic:
        rep.warnings.append(
            "SYNTHETIC study: values are demonstration assumptions, not field data"
        )
    return rep


def basis_to_registers(basis: dict[str, Any]) -> Registers:
    """Create the source register and gap entries from a planning basis."""
    reg = registers_from_basis(basis)
    rep = validate_basis(basis)
    for g in rep.gaps:
        reg.add_gap(
            g["key"], g["description"], g["consequence"], g.get("severity", "MAJOR")
        )
    for e in rep.errors:
        if e.startswith("required input missing"):
            reg.add_gap(
                e.split(": ", 1)[1], e, "calculation blocked until supplied", "BLOCKING"
            )
    return reg


def template_basis(
    well_type: str = "oil_producer", environment: str = "platform"
) -> dict[str, Any]:
    """Return a synthetic, internally consistent starting basis for ``well_type``/``environment``."""
    if well_type not in WELL_TYPES:
        raise ValueError("unknown well type " + well_type)
    if environment not in ENVIRONMENTS:
        raise ValueError("unknown environment " + environment)
    import importlib.resources  # noqa: F401  (kept for packaged-template discovery)

    from . import examples_data

    return (
        copy.deepcopy(examples_data.CASES[well_type + ":" + environment])
        if (well_type + ":" + environment) in examples_data.CASES
        else copy.deepcopy(examples_data.generic(well_type, environment))
    )
