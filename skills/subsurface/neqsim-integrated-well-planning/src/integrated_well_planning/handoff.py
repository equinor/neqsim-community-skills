"""Versioned hand-off messages (``iwp_*.v1``) to and from the agents the planning engineer coordinates.

Pattern (see the agent hand-off skill): an envelope ``iwp_handoff_envelope.v1`` carries the sender, receiver, study id, status and a
payload validated against the named message schema. Builders create outbound messages from the basis and results; ``apply_*`` functions
ingest inbound messages into the basis and always record SUPPLIED provenance with the message source - an inbound value is never
silently treated as a calculated one.
"""

from __future__ import annotations

import copy
import datetime as _dt
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from .registers import get_path

AGENT_NAME = "well-planning-engineer"
MESSAGES = (
    "iwp_well_model.v1", "iwp_vfp_request.v1", "iwp_trajectory.v1", "iwp_host_constraints.v1", "iwp_fluid_basis.v1", "iwp_cost_profile.v1",
    "iwp_flow_assurance_requirements.v1", "iwp_integrity_inputs.v1", "iwp_operating_envelope.v1", "iwp_interface_spec.v1", "iwp_planning_basis.v1",
)

# Which agent normally sends / receives each message (community catalog; the enterprise overlay maps the same schemas to internal agents).
ROUTES = {
    "iwp_planning_basis.v1": {"in_from": ["reservoir-simulator-agent", "fluid-characterization-agent", "field-development"], "out_to": []},
    "iwp_well_model.v1": {"out_to": ["field-development", "reservoir-to-facility-screening-agent", "production-optimization-agent"]},
    "iwp_vfp_request.v1": {"out_to": ["vfp-lift-curve-agent"]},
    "iwp_trajectory.v1": {"in_from": ["well-trajectory-anticollision-agent"], "out_to": ["well-trajectory-anticollision-agent"]},
    "iwp_host_constraints.v1": {"in_from": ["tie-in-screening-agent", "debottlenecking-agent", "production-optimization-agent"]},
    "iwp_fluid_basis.v1": {"in_from": ["fluid-characterization-agent", "pvt-agent", "e300-fluid-agent"]},
    "iwp_cost_profile.v1": {"out_to": ["asset-economics-agent", "field-development", "concept-selection-agent"]},
    "iwp_flow_assurance_requirements.v1": {"in_from": ["flow-assurance-study-agent", "flow-assurance-engineer-agent"], "out_to": ["flow-assurance-study-agent", "flow-assurance-engineer-agent"]},
    "iwp_integrity_inputs.v1": {"out_to": ["process-safety-agent"], "in_from": []},
    "iwp_operating_envelope.v1": {"out_to": ["production-optimization-agent", "debottlenecking-agent"]},
    "iwp_interface_spec.v1": {"out_to": ["well-trajectory-anticollision-agent", "near-well-injectivity-agent", "artificial-lift-agent"]},
}


def schema_dir() -> Path:
    """Directory holding the JSON schemas (``IWP_SCHEMA_DIR`` overrides the skill-root ``schemas`` folder)."""
    env = os.environ.get("IWP_SCHEMA_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    for cand in (here.parents[2] / "schemas", here.parent / "schemas"):
        if cand.is_dir():
            return cand
    raise FileNotFoundError("schemas folder not found next to the skill (set IWP_SCHEMA_DIR)")


def load_schema(message_schema: str) -> Dict[str, Any]:
    """Load one schema by id (``iwp_vfp_request.v1``)."""
    p = schema_dir() / (message_schema + ".json")
    if not p.exists():
        raise KeyError("unknown message schema " + message_schema)
    return json.loads(p.read_text(encoding="utf-8"))


def validate_payload(message_schema: str, payload: Dict[str, Any]) -> List[str]:
    """Return validation errors for a payload against its schema (empty = valid)."""
    schema = load_schema(message_schema)
    try:
        import jsonschema
    except ImportError:  # minimal fallback: required keys only
        return ["missing required key: {}".format(k) for k in schema.get("required", []) if k not in payload]
    v = jsonschema.Draft7Validator(schema)
    return ["{}: {}".format("/".join(str(x) for x in e.path) or "<root>", e.message) for e in sorted(v.iter_errors(payload), key=lambda e: list(e.path))]


def make_envelope(message_schema: str, payload: Dict[str, Any], to_agent: str, study_id: str, revision: str = "A", from_agent: str = AGENT_NAME, status: str = "DRAFT",
                  synthetic: bool = False, open_items: Optional[List[str]] = None, provenance: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Wrap a payload in the envelope, validating both. Raises ValueError listing every problem."""
    problems = validate_payload(message_schema, payload)
    env = {"schema": "iwp_handoff_envelope.v1", "message_schema": message_schema, "study_id": study_id, "revision": revision, "from_agent": from_agent, "to_agent": to_agent,
           "created": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"), "status": status, "synthetic": synthetic, "open_items": list(open_items or []),
           "provenance": list(provenance or []), "payload": payload}
    problems += ["envelope: " + p for p in validate_payload("iwp_handoff_envelope.v1", env)]
    if problems:
        raise ValueError("invalid {} message: {}".format(message_schema, "; ".join(problems)))
    return env


def _study(basis: Dict[str, Any]) -> Dict[str, Any]:
    return {"study_id": get_path(basis, "study.id"), "revision": get_path(basis, "study.revision") or "A", "synthetic": bool(get_path(basis, "study.synthetic"))}


def vfp_request(basis: Dict[str, Any], results: Dict[str, Any]) -> Dict[str, Any]:
    """Build the VFPPROD/VFPINJ request for the vfp-lift-curve-agent (grids around the base-case operating region)."""
    from .model_chain import effective_tubing_depths

    d = effective_tubing_depths(basis)
    wtype = get_path(basis, "well.type")
    injector = wtype in ("water_injector", "gas_injector")
    rate = get_path(basis, "targets.rate")
    q_lo, q_hi = float(rate["low"]) * 0.2, float(rate["high"]) * 2.0
    whp = [float(x) for x in np.linspace(10.0 if not injector else 30.0, 120.0 if not injector else 300.0, 6)]
    payload = {
        "table_kind": "VFPINJ" if injector else "VFPPROD", "well_id": get_path(basis, "well.id"), "datum_depth_m": d["tvd_m"],
        "tubing": {"id_m": float(get_path(basis, "completion.tubing.id_m")), "md_m": d["md_m"], "tvd_m": d["tvd_m"], "roughness_m": float(get_path(basis, "completion.tubing.roughness_m") or 4.5e-5)},
        "survey": get_path(basis, "trajectory.survey") or {}, "thermal": {"reservoir_temperature_C": float(get_path(basis, "reservoir.temperature_C")), "overall_u_w_m2k": get_path(basis, "completion.overall_u_w_m2k")},
        "fluid_basis": {"eos": get_path(basis, "fluid.eos"), "components": get_path(basis, "fluid.components"), "water_cut_range": get_path(basis, "reservoir.water_cut")},
        "grids": {"rate": [float(x) for x in np.linspace(q_lo, q_hi, 7)], "whp_bara": whp, "water_cut": [0.0, 0.2, 0.5] if not injector else [], "gor": [], "lift_gas": []},
        "rate_unit": rate.get("kind", "Sm3/d") if isinstance(rate, dict) else "Sm3/d",
        "calibration": {"note": "calibrate the VLP to well tests when available (neqsim-vfp-lift-curves); synthetic until then"},
        "expected_return": "VFPPROD/VFPINJ tables, validation (IPR x VFP intersection) and the export deck with provenance",
    }
    return make_envelope("iwp_vfp_request.v1", payload, "vfp-lift-curve-agent", **_study(basis))


def trajectory_message(basis: Dict[str, Any], survey: Dict[str, Any]) -> Dict[str, Any]:
    """Outbound trajectory for the anti-collision agent."""
    st = [{"md_m": m, "inc_deg": i, "azi_deg": a, "tvd_m": t, "north_m": n, "east_m": e} for m, i, a, t, n, e in zip(survey["md"], survey["inc"], survey["azi"], survey["tvd"], survey["north"], survey["east"])]
    payload = {"well_id": get_path(basis, "well.id"), "depth_reference": get_path(basis, "datums.reference") or "RKB", "reference_elevation_msl_m": get_path(basis, "datums.reference_elevation_msl_m"),
               "coordinate_system": get_path(basis, "datums.coordinate_system") or "", "stations": st, "uncertainty_model": "TO_BE_SUPPLIED (ISCWSA model of the survey tool)",
               "offset_wells": [], "status": "PLANNING_GEOMETRY"}
    return make_envelope("iwp_trajectory.v1", payload, "well-trajectory-anticollision-agent", **_study(basis))


def cost_profile_message(basis: Dict[str, Any], profile: Dict[str, Any], to_agent: str = "asset-economics-agent") -> Dict[str, Any]:
    """Outbound deliverability profile and supplied cost basis (no recovery and no value)."""
    cost = get_path(basis, "cost") or {}
    payload = {"well_id": get_path(basis, "well.id"), "profile": {"years": profile["years"], "cases": profile["cases"], "unit": (get_path(basis, "targets.rate.kind") or "Sm3/d")},
               "cost": {"currency": cost.get("currency") or get_path(basis, "study.currency") or "NOT_SUPPLIED", **{k: v for k, v in cost.items() if k in ("capex", "opex_per_year", "source", "price_basis_year")}},
               "energy_demand": profile.get("energy", {}), "exclusions": ["reservoir recovery", "project value", "drilling cost unless supplied", "abandonment cost unless supplied"],
               "statement": "Deliverability only: not a production forecast and not a value estimate (ledger L25)."}
    return make_envelope("iwp_cost_profile.v1", payload, to_agent, **_study(basis))


def flow_assurance_requirements(basis: Dict[str, Any], results: Dict[str, Any]) -> Dict[str, Any]:
    """Outbound conditions the flow-assurance study must cover, with the open threats."""
    prod = (results.get("producer") or {}).get("base") or {}
    inj = (results.get("injector") or {}).get("base") or {}
    conds = []
    if prod.get("wellhead"):
        conds.append({"state": "production wellhead", "pressure_bara": prod["wellhead"]["pressure_bara"], "temperature_C": prod["wellhead"]["temperature_C"], "rate": prod.get("q_op")})
        conds.append({"state": "production bottom hole", "pressure_bara": prod["bottomhole"]["pressure_bara"], "temperature_C": prod["bottomhole"]["temperature_C"], "rate": prod.get("q_op")})
    if inj.get("whp_required_bara"):
        conds.append({"state": "injection wellhead", "pressure_bara": inj["whp_required_bara"], "temperature_C": inj.get("wellhead_temperature_C", 0.0), "rate": inj.get("rate")})
    fa = results.get("flow_assurance") or {}
    threats = [k for k, v in fa.items() if isinstance(v, dict) and str(v.get("status", "")).startswith(("NOT_PERFORMED", "EXTERNAL"))]
    payload = {"well_id": get_path(basis, "well.id"), "conditions": conds, "inhibitor_basis": (fa.get("hydrate") or {}).get("inhibitor", {}), "open_threats": threats,
               "lab_data_needed": ["hydrate dissociation data (with inhibitor)", "wax appearance temperature", "water chemistry and compatibility"]}
    return make_envelope("iwp_flow_assurance_requirements.v1", payload, "flow-assurance-study-agent", **_study(basis))


def integrity_inputs_message(basis: Dict[str, Any], integrity: Dict[str, Any], barrier_states: List[Dict[str, Any]], open_items: List[str]) -> Dict[str, Any]:
    """Outbound load cases and barrier proposal for the well-integrity review."""
    payload = {"well_id": get_path(basis, "well.id"), "load_cases": integrity.get("load_cases", []), "tubing": {"rows": integrity.get("tubing", [])}, "apb": integrity.get("apb", {}),
               "tubing_movement": integrity.get("tubing_movement", []), "barrier_states": barrier_states, "limits_supplied": get_path(basis, "limits") or [], "open_items": open_items}
    return make_envelope("iwp_integrity_inputs.v1", payload, "process-safety-agent", **_study(basis))


def well_model_message(basis: Dict[str, Any], results: Dict[str, Any], model_files: List[str], to_agent: str = "field-development") -> Dict[str, Any]:
    """Outbound well model summary."""
    cases = {}
    for kind in ("producer", "injector"):
        for c, r in (results.get(kind) or {}).items():
            cases[c] = {k: r.get(k) for k in ("status", "q_op", "target_rate", "target_met", "bhp_op", "whp_required_bara", "bhp_bara", "fracture_margin_bar", "power_kw", "rate") if k in r}
    payload = {"well_id": get_path(basis, "well.id"), "well_type": get_path(basis, "well.type"), "environment": get_path(basis, "well.environment"), "depth_datum": get_path(basis, "datums.reference"),
               "pressure_reference": get_path(basis, "datums.pressure_reference") or "bara", "standard_conditions": get_path(basis, "datums.standard_conditions") or {}, "cases": cases,
               "ledger_refs": ["L01", "L02", "L03", "L04", "L05", "L06", "L07"], "model_files": model_files, "tubing": get_path(basis, "completion.tubing"), "assumptions": ["see registers/source_register.csv"]}
    return make_envelope("iwp_well_model.v1", payload, to_agent, **_study(basis))


def envelope_message(basis: Dict[str, Any], rows: List[Dict[str, Any]], summary: Dict[str, int], to_agent: str = "production-optimization-agent") -> Dict[str, Any]:
    """Outbound operating-envelope table."""
    return make_envelope("iwp_operating_envelope.v1", {"well_id": get_path(basis, "well.id"), "rows": rows, "summary": summary}, to_agent, **_study(basis))


# --------------------------------------------------------------------------- inbound
def _record(basis: Dict[str, Any], path: str, source: str, unit: str = "") -> None:
    basis.setdefault("provenance", {})[path] = {"class": "SUPPLIED", "source": source, "unit": unit, "synthetic": False}


def apply_host_constraints(basis: Dict[str, Any], message: Dict[str, Any]) -> Dict[str, Any]:
    """Merge an inbound ``iwp_host_constraints.v1`` envelope into a copy of the basis (provenance SUPPLIED with the message source)."""
    problems = validate_payload("iwp_handoff_envelope.v1", message)
    if message.get("message_schema") != "iwp_host_constraints.v1":
        problems.append("not an iwp_host_constraints.v1 message")
    p = message.get("payload", {})
    problems += validate_payload("iwp_host_constraints.v1", p)
    if problems:
        raise ValueError("; ".join(problems))
    out = copy.deepcopy(basis)
    src = "{} from {} ({})".format(message["message_schema"], message["from_agent"], p.get("source", "no source stated"))
    out.setdefault("facility", {})["host_pressure_bara"] = p["pressure_bara"]
    _record(out, "facility.host_pressure_bara", src, "bara")
    if "temperature_C" in p:
        out["facility"]["host_temperature_C"] = p["temperature_C"]
        _record(out, "facility.host_temperature_C", src, "C")
    if "power_kw_available" in p:
        out["facility"]["max_power_kw"] = p["power_kw_available"]
        _record(out, "facility.max_power_kw", src, "kW")
    if p.get("max_rates"):
        out["facility"]["max_rates"] = p["max_rates"]
    return out


def apply_fluid_basis(basis: Dict[str, Any], message: Dict[str, Any]) -> Dict[str, Any]:
    """Merge an inbound ``iwp_fluid_basis.v1`` envelope (composition, EOS, PVT evidence, WAT, water chemistry)."""
    p = message.get("payload", {})
    problems = validate_payload("iwp_fluid_basis.v1", p)
    if message.get("message_schema") != "iwp_fluid_basis.v1":
        problems.append("not an iwp_fluid_basis.v1 message")
    if problems:
        raise ValueError("; ".join(problems))
    out = copy.deepcopy(basis)
    src = "{} from {} ({})".format(message["message_schema"], message["from_agent"], p.get("source", "no source stated"))
    f = out.setdefault("fluid", {})
    f["eos"] = p["eos"]
    f["components"] = p["components"]
    _record(out, "fluid.components", src)
    for k_in, k_out in (("pvt_measurements", "pvt_measurements"), ("water_chemistry", "water_chemistry"), ("wax_appearance_temperature_C", "wax_appearance_temperature_C")):
        if p.get(k_in) not in (None, [], {}):
            f[k_out] = p[k_in]
            _record(out, "fluid." + k_out, src)
    return out


def apply_trajectory(basis: Dict[str, Any], message: Dict[str, Any]) -> Dict[str, Any]:
    """Merge an inbound ``iwp_trajectory.v1`` envelope: stations, MD and TVD at TD (provenance SUPPLIED)."""
    p = message.get("payload", {})
    problems = validate_payload("iwp_trajectory.v1", p)
    if message.get("message_schema") != "iwp_trajectory.v1":
        problems.append("not an iwp_trajectory.v1 message")
    if problems:
        raise ValueError("; ".join(problems))
    out = copy.deepcopy(basis)
    src = "{} from {}".format(message["message_schema"], message["from_agent"])
    st = p["stations"]
    out.setdefault("trajectory", {})["stations"] = st
    out["trajectory"]["md_m"] = st[-1]["md_m"]
    if "tvd_m" in st[-1]:
        out["trajectory"]["tvd_m"] = st[-1]["tvd_m"]
    for path in ("trajectory.stations", "trajectory.md_m", "trajectory.tvd_m"):
        _record(out, path, src, "m")
    return out
