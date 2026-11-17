"""Write a completor case file from a structured completion design, with checks completor does late or not at all."""

from __future__ import annotations

from typing import Any

ANNULUS = {"GP", "OA", "PA"}
DEVICE_TYPES = {"PERF", "AICD", "ICD", "VALVE", "DENSITY"}
DEVICE_KEYWORD = {"AICD": "aicd", "ICD": "icd", "VALVE": "valve", "DENSITY": "density"}

_AICD_COLUMNS = (
    "strength",
    "x",
    "y",
    "a",
    "b",
    "c",
    "d",
    "e",
    "f",
    "rho_cal",
    "mu_cal",
    "z",
)
_ICD_COLUMNS = ("strength", "rho_cal", "mu_cal", "critical_value")
_DENSITY_COLUMNS = (
    "cv",
    "ac_oil",
    "ac_gas",
    "ac_water",
    "wvf_low",
    "wvf_high",
    "gvf_low",
    "gvf_high",
)
_AICD_DEFAULTS = {
    "a": 1.0,
    "b": 1.0,
    "c": 1.0,
    "d": 1.0,
    "e": 1.0,
    "f": 1.0,
    "rho_cal": 1000.25,
    "mu_cal": 1.45,
    "z": 1.0,
}
_ICD_DEFAULTS = {"rho_cal": 1000.25, "mu_cal": 1.45, "critical_value": 0.5}


def validate_design(design: dict[str, Any]) -> list[str]:
    """Return a list of problems in a completion design; empty when completor can be run."""
    problems: list[str] = []
    rows = design.get("completion") or []
    if not rows:
        problems.append("completion: at least one interval is needed")
    for i, row in enumerate(rows):
        where = f"completion[{i}] ({row.get('well')})"
        for key in ("well", "start_md", "end_md", "annulus", "device_type"):
            if key not in row:
                problems.append(f"{where}: missing {key}")
        if row.get("annulus") not in ANNULUS:
            problems.append(f"{where}: annulus must be one of GP, OA, PA")
        kind = str(row.get("device_type", "")).upper()
        if kind not in DEVICE_TYPES:
            problems.append(
                f"{where}: device_type must be one of {sorted(DEVICE_TYPES)}"
            )
        start, end = float(row.get("start_md", 0)), float(row.get("end_md", 0))
        if end < start or (end == start and row.get("annulus") != "PA"):
            problems.append(
                f"{where}: end_md must exceed start_md (only packers, annulus PA, have zero length)"
            )
        if kind in DEVICE_KEYWORD:
            number = int(row.get("device_number", 0))
            table = design.get(DEVICE_KEYWORD[kind]) or []
            if number not in {int(d.get("number", -1)) for d in table}:
                problems.append(
                    f"{where}: {kind} device {number} is not defined under '{DEVICE_KEYWORD[kind]}'"
                )
            if (
                float(row.get("devices_per_joint", 0)) <= 0
                and row.get("annulus") != "PA"
            ):
                problems.append(
                    f"{where}: devices_per_joint must be positive for {kind}"
                )
    for key, columns in (
        ("aicd", ("strength", "x", "y")),
        ("icd", ("strength",)),
        ("valve", ("cv", "ac")),
        ("density", _DENSITY_COLUMNS),
    ):
        for d in design.get(key) or []:
            missing = [c for c in ("number",) + columns if c not in d]
            if missing:
                problems.append(
                    f"{key} device {d.get('number')}: missing {', '.join(missing)}"
                )
    return problems


def _fmt(value: Any) -> str:
    if isinstance(value, str):
        return value
    return f"{float(value):.6g}"


def build_case(design: dict[str, Any]) -> str:
    """Return completor case-file text for a design dict.

    ``design`` keys: ``completion`` (rows with well, branch, start_md, end_md, screen_diameter_m,
    casing_diameter_m, roughness_m, annulus, devices_per_joint, device_type, device_number), device tables
    ``aicd``/``icd``/``valve``/``density`` (rows with ``number`` and the device fields), and optional
    ``joint_length_m``, ``segment_length`` (0 = grid cells), ``use_strict`` and ``gp_perf_devicelayer``.
    """
    problems = validate_design(design)
    if problems:
        raise ValueError("completion design is not valid:\n- " + "\n- ".join(problems))
    lines = [
        "-- Completor case file written by msw_completion (neqsim-multisegment-well-completion)",
        "",
        "COMPLETION",
        "-- Well Branch StartMD EndMD Screen Casing Roughness Annulus Nvalve/Joint ValveType DeviceNumber",
    ]
    for row in design["completion"]:
        lines.append(
            "  ".join(
                [
                    f"'{row['well']}'",
                    str(int(row.get("branch", 1))),
                    _fmt(row["start_md"]),
                    _fmt(row["end_md"]),
                    _fmt(row.get("screen_diameter_m", 0.15)),
                    _fmt(row.get("casing_diameter_m", 0.216)),
                    _fmt(row.get("roughness_m", 1.0e-4)),
                    row["annulus"],
                    _fmt(row.get("devices_per_joint", 0)),
                    str(row["device_type"]).upper(),
                    str(int(row.get("device_number", 0))),
                ]
            )
        )
    lines += ["/", ""]
    lines += ["JOINTLENGTH", _fmt(design.get("joint_length_m", 12.0)), "/", ""]
    if "segment_length" in design:
        lines += ["SEGMENTLENGTH", str(design["segment_length"]), "/", ""]
    if "use_strict" in design:
        lines += ["USE_STRICT", "TRUE" if design["use_strict"] else "FALSE", "/", ""]
    if design.get("gp_perf_devicelayer"):
        lines += ["GP_PERF_DEVICELAYER", "TRUE", "/", ""]
    if design.get("aicd"):
        lines += ["WSEGAICD", "-- Number " + " ".join(_AICD_COLUMNS)]
        for d in design["aicd"]:
            values = dict(_AICD_DEFAULTS, **d)
            lines.append(
                f"  {int(d['number'])} "
                + " ".join(_fmt(values[c]) for c in _AICD_COLUMNS)
            )
        lines += ["/", ""]
    if design.get("icd"):
        lines += ["WSEGSICD", "-- Number " + " ".join(_ICD_COLUMNS)]
        for d in design["icd"]:
            values = dict(_ICD_DEFAULTS, **d)
            lines.append(
                f"  {int(d['number'])} "
                + " ".join(_fmt(values[c]) for c in _ICD_COLUMNS)
            )
        lines += ["/", ""]
    if design.get("valve"):
        lines += ["WSEGVALV", "-- Number Cv Ac Defaults Ac_max"]
        for d in design["valve"]:
            lines.append(
                f"  {int(d['number'])} {_fmt(d['cv'])} {_fmt(d['ac'])} 5* {_fmt(d.get('ac_max', d['ac']))}"
            )
        lines += ["/", ""]
    if design.get("density"):
        lines += ["WSEGDENSITY", "-- Number " + " ".join(_DENSITY_COLUMNS)]
        for d in design["density"]:
            lines.append(
                f"  {int(d['number'])} "
                + " ".join(_fmt(d[c]) for c in _DENSITY_COLUMNS)
            )
        lines += ["/", ""]
    return "\n".join(lines) + "\n"
