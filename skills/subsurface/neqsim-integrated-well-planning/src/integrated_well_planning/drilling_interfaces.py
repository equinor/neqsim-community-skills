"""Trajectory, drilling and completion interfaces.

Implemented here: minimum-curvature trajectory geometry/DLS check, casing-programme formula ratings (through the required
``well_design_study`` module), a pore/mud/fracture window arithmetic check. Everything else (anti-collision, geomechanics,
drilling hydraulics, cement placement, detailed mechanical design) is an INTERFACE SPECIFICATION with an unresolved
assessment: inputs available in the basis, inputs still missing, the receiving tool/agent and the expected return. No
number is fabricated for those assessments.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

from .datums import build_and_hold, check_datum_consistency, survey_summary
from .integrity import pipe_dimensions, tubular_ratings
from .registers import get_path


def trajectory_from_basis(basis: Dict[str, Any]) -> Dict[str, Any]:
    """Compute the survey from a supplied station table, or from the build-and-hold description, and check datum consistency."""
    traj = get_path(basis, "trajectory") or {}
    md = float(traj["md_m"])
    tvd = float(traj["tvd_m"])
    if traj.get("stations"):
        from .datums import minimum_curvature

        st = traj["stations"]
        survey = minimum_curvature([s["md_m"] for s in st], [s["inc_deg"] for s in st], [s["azi_deg"] for s in st])
        source = "supplied survey stations"
    else:
        sv = traj.get("survey") or {}
        survey = build_and_hold(float(sv.get("kop_md_m", md)), float(sv.get("build_rate_deg_per_30m", 2.0)), float(sv.get("hold_inclination_deg", 0.0)), md, float(sv.get("azimuth_deg", 0.0)))
        source = "build-and-hold from the basis description (synthetic path, NOT a surveyed trajectory)"
    summary = survey_summary(survey, traj.get("max_dls_deg_per_30m"))
    problems = check_datum_consistency(md, tvd, summary["max_inclination_deg"], survey, tol_m=max(5.0, 0.01 * md))
    return {"survey": survey, "summary": summary, "source": source, "consistency_problems": problems, "status": "PASS" if not problems else "REVIEW"}


def casing_ratings(basis: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Formula ratings of every casing string (no loads): burst, collapse, body yield; ``available`` False without the drilling module."""
    rows = []
    for c in get_path(basis, "completion.casing") or []:
        try:
            dims = pipe_dimensions(c["od_in"], c.get("weight_ppf"), c.get("wall_in"))
        except ValueError:
            rows.append({"string": c["name"], "available": False, "reason": "no weight or wall supplied"})
            continue
        r = tubular_ratings(dims["od_in"], dims["wall_in"], c.get("grade", ""), 20.0)
        rows.append({"string": c["name"], "od_in": c["od_in"], "wall_in": dims["wall_in"], "grade": c.get("grade"), **r})
    return rows


def pressure_window(basis: Dict[str, Any]) -> Dict[str, Any]:
    """Pore/mud/fracture arithmetic at the casing shoes. No trip, kick or fracture margins are applied (none supplied)."""
    pts = get_path(basis, "drilling.pressure_window") or []
    if not pts:
        return {"status": "NOT_ASSESSED", "reason": "no pressure_window supplied"}
    z = [p["tvd_m"] for p in pts]
    pore, frac, mud = [p["pore_bara"] for p in pts], [p["frac_bara"] for p in pts], [p["mud_bara"] for p in pts]
    rows = []
    for c in get_path(basis, "completion.casing") or []:
        zs = c.get("shoe_tvd_m")
        if zs is None:
            continue
        pw, fr, mw = (float(np.interp(zs, z, a)) for a in (pore, frac, mud))
        rows.append({"string": c["name"], "shoe_tvd_m": zs, "pore_bara": pw, "mud_bara": mw, "frac_bara": fr, "window_open": bool(pw < mw < fr), "mud_over_pore_bar": mw - pw, "frac_over_mud_bar": fr - mw})
    return {"status": "REVIEW (margins required by the operator are not defined)", "rows": rows, "tvd_m": z, "pore_bara": pore, "frac_bara": frac, "mud_bara": mud,
            "note": "arithmetic check only; kick tolerance, trip/swab margins and borehole stability are a drilling/geomechanics assessment (interface specs)"}


INTERFACES = [
    {"id": "IF-01", "assessment": "Anti-collision and survey uncertainty", "receiver": "well-trajectory-anticollision-agent (screening) then a Compass-class tool", "ledger": "L22",
     "needs": ["trajectory.stations", "offset well surveys with uncertainty models", "slot/surface location", "separation-factor rule"], "returns": "separation factors, governing offset, target pull-back"},
    {"id": "IF-02", "assessment": "Pore/fracture pressure and borehole stability (geomechanics)", "receiver": "geomechanics specialist", "ledger": "L23",
     "needs": ["drilling.pressure_window", "drilling.hazards", "offset logs/leak-off tests", "stress and rock-strength model"], "returns": "mud-weight window per section, stability limits per inclination"},
    {"id": "IF-03", "assessment": "Casing seats, kick tolerance, well control", "receiver": "well_design_study (screening) and the operator drilling engineer", "ledger": "L12",
     "needs": ["drilling.pressure_window", "kick basis (intensity, influx)", "BOP/rig basis"], "returns": "seat proposal, kick tolerance per section"},
    {"id": "IF-04", "assessment": "Drilling hydraulics (ECD, hole cleaning, torque and drag)", "receiver": "well_design_study (screening) / operator drilling software", "ledger": "L24",
     "needs": ["trajectory", "mud rheology", "string and BHA", "pump/rig limits"], "returns": "ECD, pump pressure, torque/drag envelope"},
    {"id": "IF-05", "assessment": "Cementing: objectives, placement and zonal isolation", "receiver": "cementing specialist / operator software", "ledger": "L24",
     "needs": ["hole sizes and casing programme", "pore/fracture window", "cement top objectives", "temperature profile"], "returns": "placement simulation, centralisation, expected top of cement"},
    {"id": "IF-06", "assessment": "Detailed casing/tubing mechanical design (ISO 13679-type load-case matrix)", "receiver": "operator casing-design software", "ledger": "L11",
     "needs": ["load cases from the integrity block", "operator design factors", "connection data", "material ratings"], "returns": "design-factor utilisation per load case and string"},
    {"id": "IF-07", "assessment": "Completion equipment selection (packer, DHSV, mandrels, sand control, tree interface)", "receiver": "completion engineer", "ledger": "L13",
     "needs": ["load envelope", "fluid/materials basis", "intervention strategy", "tree/wellhead datasheets"], "returns": "equipment list with verified ratings"},
]


def interface_specifications(basis: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Interface specification per specialist assessment with available/missing inputs and an UNRESOLVED status."""
    checks = {
        "trajectory.stations": bool(get_path(basis, "trajectory.stations")),
        "drilling.pressure_window": bool(get_path(basis, "drilling.pressure_window")),
        "drilling.hazards": bool(get_path(basis, "drilling.hazards")),
        "slot/surface location": bool(get_path(basis, "trajectory.surface_location")),
        "operator design factors": bool(get_path(basis, "design_factors")),
        "hole sizes and casing programme": bool(get_path(basis, "completion.casing")),
        "load cases from the integrity block": True,
        "trajectory": bool(get_path(basis, "trajectory")),
        "temperature profile": True,
        "intervention strategy": bool(get_path(basis, "operations.intervention_strategy")),
    }
    out = []
    for spec in INTERFACES:
        have = [n for n in spec["needs"] if checks.get(n, False)]
        miss = [n for n in spec["needs"] if not checks.get(n, False)]
        out.append({"schema": "iwp_interface_spec.v1", "id": spec["id"], "assessment": spec["assessment"], "receiver": spec["receiver"], "ledger_ref": spec["ledger"],
                    "inputs_available": have, "inputs_missing": miss, "expected_return": spec["returns"], "status": "UNRESOLVED",
                    "statement": "No calculation is claimed for this assessment; the specification defines the hand-off to the specialist tool."})
    return out
