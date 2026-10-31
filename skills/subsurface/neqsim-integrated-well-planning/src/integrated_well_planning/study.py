"""Study folder layout and the end-to-end workflow steps (init, validate, run, envelope, alternatives, drawings).

Folder layout::

    <study>/basis/       planning_basis.yaml, inbound hand-off messages
    <study>/registers/   source register, data gaps, standards register, capability ledger
    <study>/models/      rerun_model.py (re-executes the numbers), model_results copy
    <study>/results/     validation.json, model_results.json, envelope.*, alternatives.json, handoffs/
    <study>/drawings/    PNG (300 dpi), PDF/SVG sheets, provenance sidecars, drawings_register.csv
    <study>/report/      well-planning report (docx + md)
    <study>/decisions/   decision_log.csv, action_log.csv
"""

from __future__ import annotations

import copy
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from . import __version__
from .alternatives import (default_alternatives, deliverability_profile, evaluate_alternatives, pareto_front, scorecard, sensitivity_grid, tornado)
from .barriers import barrier_summary, propose_barriers, to_rows as barrier_rows
from .basis import CASES, PRODUCER_TYPES, basis_to_registers, load_basis, save_basis, template_basis, validate_basis
from .drilling_interfaces import casing_ratings, interface_specifications, pressure_window, trajectory_from_basis
from .envelope import build_envelope, summarise as envelope_summary, to_markdown as envelope_md, to_rows as envelope_rows
from .flow_assurance import assess_flow_assurance
from .handoff import (cost_profile_message, envelope_message, flow_assurance_requirements, integrity_inputs_message, trajectory_message, vfp_request, well_model_message)
from .integrity import evaluate_integrity, shut_in_wellhead_pressure
from .ledger import JAVA_FOLLOW_UPS, ledger_rows
from .registers import Registers, get_path
from .runtime import ensure_runtime
from .standards import seed_register, to_rows as standards_rows

SUBDIRS = ("basis", "registers", "models", "results", "drawings", "report", "decisions")


def study_paths(root: Path) -> Dict[str, Path]:
    """Return the study sub-folder paths."""
    root = Path(root)
    return {name: root / name for name in SUBDIRS}


def _dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=_default), encoding="utf-8")


def _default(o: Any) -> Any:
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def load_json(path: Path) -> Any:
    """Read a JSON file."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def init_study(root: Path, well_type: str = "oil_producer", environment: str = "platform", basis: Optional[Dict[str, Any]] = None, overwrite: bool = False) -> Dict[str, Path]:
    """Create the study folder layout, the starting basis (synthetic template unless supplied) and the initial registers."""
    paths = study_paths(root)
    for p in paths.values():
        p.mkdir(parents=True, exist_ok=True)
    bfile = paths["basis"] / "planning_basis.yaml"
    if bfile.exists() and not overwrite:
        raise FileExistsError("{} exists (use overwrite=True)".format(bfile))
    b = copy.deepcopy(basis) if basis else template_basis(well_type, environment)
    save_basis(b, bfile)
    reg = basis_to_registers(b)
    reg.add_decision("Study scope and maturity", "Run the {} workflow at {} maturity".format(get_path(b, "well.type"), get_path(b, "study.maturity")), "defined in the planning basis", status="PROPOSED")
    reg.add_action("Identify jurisdiction, operator and company requirements and fill standards.jurisdiction", discipline="well integrity")
    reg.save(paths["decisions"])
    reg.save(paths["registers"])
    _dump(paths["registers"] / "standards_register.json", standards_rows(seed_register(get_path(b, "standards.jurisdiction") or "TO_BE_IDENTIFIED")))
    _dump(paths["registers"] / "capability_ledger.json", {"ledger": ledger_rows(), "java_follow_ups": JAVA_FOLLOW_UPS})
    return paths


def validate(root: Path) -> Dict[str, Any]:
    """Validate the basis; write results/validation.json and refresh the registers."""
    paths = study_paths(root)
    basis = load_basis(paths["basis"] / "planning_basis.yaml")
    rep = validate_basis(basis)
    out = rep.to_dict()
    _dump(paths["results"] / "validation.json", out)
    reg = Registers.load(paths["decisions"])
    fresh = basis_to_registers(basis)
    fresh.decisions, fresh.actions = reg.decisions, reg.actions
    fresh.save(paths["registers"])
    fresh.save(paths["decisions"])
    return out


def _model_for(basis: Dict[str, Any], segments: int):
    from .injectors import InjectorModel
    from .producers import ProducerModel

    return ProducerModel(basis, segments=segments) if get_path(basis, "well.type") in PRODUCER_TYPES else InjectorModel(basis, segments=segments)


def run_model(root: Path, segments: int = 10) -> Dict[str, Any]:
    """Run the chain for low/base/high, then flow assurance, integrity, barriers, interfaces and hand-offs; write results/model_results.json."""
    paths = study_paths(root)
    basis = load_basis(paths["basis"] / "planning_basis.yaml")
    rep = validate_basis(basis)
    if rep.errors:
        raise ValueError("basis validation failed (fail-closed): " + "; ".join(rep.errors))
    rt = ensure_runtime()
    if not rt.wellplanning_available:
        raise RuntimeError("NeqSim wellplanning classes not available: " + rt.reason)
    wtype = get_path(basis, "well.type")
    producer = wtype in PRODUCER_TYPES
    model = _model_for(basis, segments)
    res: Dict[str, Any] = {"schema": "iwp_model_results.v1", "tool_version": __version__, "meta": {"well_type": wtype, "gas_well": wtype in ("gas_producer", "gas_condensate_producer"),
                           "synthetic": bool(get_path(basis, "study.synthetic")), "runtime": rt.to_dict(), "cases_definition": "outcome cases: low = pessimistic, high = optimistic; target rate = base in every case"}}
    key = "producer" if producer else "injector"
    res[key] = {c: (model.operating_point(c) if not producer else model.operating_point(c, detail=True)) for c in CASES}
    base = res[key]["base"]
    if producer:
        pres_hi = model.params("high")["pressure_bara"]
        base["shut_in_whp_bara"] = shut_in_wellhead_pressure(basis, pres_hi)["whp_bara"]
        d0 = float(get_path(basis, "completion.tubing.id_m"))
        fam = model.nodal_family("base", "tubing_id_m", [round(d0 * f, 4) for f in (0.85, 1.0, 1.2)])
        fam["ipr_low"] = [float(model.ipr("low")["pwf"](q)) for q in fam["q"]]
        fam["ipr_high"] = [float(model.ipr("high")["pwf"](q)) for q in fam["q"]]
        res["charts"] = {"nodal_family": fam}
        res["flow_assurance"] = assess_flow_assurance(basis, base, None, res["meta"]["gas_well"])
        res["integrity"] = evaluate_integrity(basis, producer=base)
    else:
        res["flow_assurance"] = assess_flow_assurance(basis, None, base, False)
        whps = [float(x) for x in np.linspace(max(10.0, 0.4 * base.get("whp_required_bara", 100.0)), 1.6 * base.get("whp_required_bara", 100.0), 5)] if base.get("whp_required_bara") else []
        res["charts"] = {"injectivity_curve": {c: model.injectivity_curve(c, whps) for c in ("base",)} if whps else {}}
        res["integrity"] = evaluate_integrity(basis, injector=base)
    traj = trajectory_from_basis(basis)
    res["trajectory"] = {"summary": traj["summary"], "source": traj["source"], "status": traj["status"], "consistency_problems": traj["consistency_problems"], "survey": traj["survey"]}
    res["casing_ratings"] = casing_ratings(basis)
    res["pressure_window"] = pressure_window(basis)
    states = propose_barriers(basis)
    res["barriers"] = {"states": [__import__("dataclasses").asdict(s) for s in states], "summary": barrier_summary(states)}
    res["interface_specs"] = interface_specifications(basis)
    rows = build_envelope(basis, res)
    res["envelope"] = {"rows": envelope_rows(rows), "summary": envelope_summary(rows)}
    _dump(paths["results"] / "model_results.json", res)
    write_rerun_script(paths)
    write_handoffs(paths, basis, res)
    _write_envelope_files(paths, res["envelope"]["rows"])
    return res


def _write_envelope_files(paths: Dict[str, Path], rows: List[Dict[str, Any]]) -> None:
    _dump(paths["results"] / "operating_envelope.json", rows)
    with (paths["results"] / "operating_envelope.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["id"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    from .envelope import EnvelopeRow

    (paths["results"] / "operating_envelope.md").write_text(envelope_md([EnvelopeRow(**r) for r in rows]), encoding="utf-8")


def envelope(root: Path, warn_utilisation: float = 0.9) -> List[Dict[str, Any]]:
    """Rebuild the operating-envelope table from saved results and the (possibly updated) limits in the basis."""
    paths = study_paths(root)
    basis = load_basis(paths["basis"] / "planning_basis.yaml")
    res = load_json(paths["results"] / "model_results.json")
    rows = build_envelope(basis, res, warn_utilisation)
    res["envelope"] = {"rows": envelope_rows(rows), "summary": envelope_summary(rows)}
    _dump(paths["results"] / "model_results.json", res)
    _write_envelope_files(paths, res["envelope"]["rows"])
    return res["envelope"]["rows"]


def alternatives(root: Path, with_tornado: bool = True, profile_years: Optional[List[float]] = None, segments: int = 10) -> Dict[str, Any]:
    """Compare alternatives (tubing/lift), tornado, optional deliverability profile; writes results/alternatives.json and hand-offs."""
    paths = study_paths(root)
    basis = load_basis(paths["basis"] / "planning_basis.yaml")
    wtype = get_path(basis, "well.type")
    producer = wtype in PRODUCER_TYPES
    model = _model_for(basis, segments)
    alts = get_path(basis, "alternatives") or default_alternatives(basis)
    rows = evaluate_alternatives(model, basis, alts, CASES, producer)
    sc = scorecard(rows, get_path(basis, "alternatives_weights"), producer)
    labels = {r["id"]: r["label"] for r in rows}
    out: Dict[str, Any] = {"alternatives": rows, "scorecard": sc, "labels": labels, "recommendation": None, "statement": "deliverability-based comparison; recovery and project value are not inferred"}
    if producer:
        pts = {r["id"]: ((r["lift_gas_sm3d"] or 0.0) + 1.0e-3, r["q_op"]["base"] or 0.0) for r in rows}
        out["pareto_front"] = pareto_front(pts, (False, True))
        out["pareto_points"] = pts
    else:
        pts = {r["id"]: (r["power_kw"]["base"] or 0.0, -(r["whp_required"]["base"] or 0.0)) for r in rows}
        out["pareto_front"] = pareto_front(pts, (False, True))
        out["pareto_points"] = {k: (v[0], -v[1]) for k, v in pts.items()}
    feasible = [r["id"] for r in rows if (all(r["target_met"].values()) if producer and "target_met" in r else r["status"]["base"] == "OK")]
    base_ok = [r["id"] for r in rows if (r["target_met"]["base"] if producer else r["status"]["base"] == "OK")]
    pool = feasible or base_ok
    if pool:
        best = max(pool, key=lambda i: sc["totals"][i])
        out["recommendation"] = {"id": best, "label": labels[best], "basis": "highest weighted score among alternatives that meet the target in {}".format(
            "all cases" if feasible else "the base case"), "weights": sc["weights_source"], "feasible_all_cases": feasible, "feasible_base": base_ok}
    else:
        out["recommendation"] = {"id": None, "label": "no alternative meets the target", "basis": "all alternatives fail the base case; artificial lift, lower back pressure or a different well design is needed"}
    if with_tornado:
        out["tornado"] = tornado(model, basis, producer)
        if producer:
            d0 = float(get_path(basis, "completion.tubing.id_m"))
            out["sensitivity_grid"] = sensitivity_grid(model, "base", "tubing_id_m", [round(d0 * f, 4) for f in (0.85, 1.0, 1.2)], "host_pressure_bara",
                                                       [model.params("base")["host_pressure_bara"] + d for d in (-5.0, 0.0, 10.0)])
    if profile_years and producer:
        out["deliverability_profile"] = deliverability_profile(model, basis, profile_years, CASES)
    _dump(paths["results"] / "alternatives.json", out)
    res = load_json(paths["results"] / "model_results.json") if (paths["results"] / "model_results.json").exists() else {}
    if profile_years and producer:
        paths["results"].joinpath("handoffs").mkdir(exist_ok=True)
        msg = cost_profile_message(basis, out["deliverability_profile"])
        _dump(paths["results"] / "handoffs" / "iwp_cost_profile.v1.json", msg)
    return out


def write_handoffs(paths: Dict[str, Path], basis: Dict[str, Any], res: Dict[str, Any]) -> List[str]:
    """Write the outbound hand-off messages that can be built from the model results."""
    d = paths["results"] / "handoffs"
    d.mkdir(parents=True, exist_ok=True)
    msgs = {"iwp_vfp_request.v1": vfp_request(basis, res), "iwp_flow_assurance_requirements.v1": flow_assurance_requirements(basis, res),
            "iwp_integrity_inputs.v1": integrity_inputs_message(basis, res.get("integrity", {}), res["barriers"]["states"], [s["id"] + ": " + s["assessment"] for s in res["interface_specs"]]),
            "iwp_well_model.v1": well_model_message(basis, res, ["models/rerun_model.py", "results/model_results.json"]),
            "iwp_operating_envelope.v1": envelope_message(basis, res["envelope"]["rows"], res["envelope"]["summary"]),
            "iwp_trajectory.v1": trajectory_message(basis, res["trajectory"]["survey"])}
    names = []
    for k, m in msgs.items():
        _dump(d / (k + ".json"), m)
        names.append(k)
    for spec in res["interface_specs"]:
        _dump(d / "iwp_interface_spec.v1.{}.json".format(spec["id"]), spec)
    return names


RERUN = '''"""Re-run the numbers of this study (generated by integrated_well_planning {version}).

Run with the shared NeqSim Python interpreter: <python> models/rerun_model.py
Needs the integrated_well_planning package and a NeqSim runtime that contains the wellplanning classes.
"""
import json
from pathlib import Path

from integrated_well_planning.study import run_model, validate

ROOT = Path(__file__).resolve().parents[1]
print(json.dumps(validate(ROOT), indent=2))
results = run_model(ROOT)
print("operating envelope summary:", results["envelope"]["summary"])
'''


def write_rerun_script(paths: Dict[str, Path]) -> Path:
    """Write models/rerun_model.py so a reviewer can reproduce the results."""
    p = paths["models"] / "rerun_model.py"
    p.write_text(RERUN.format(version=__version__), encoding="utf-8")
    return p
