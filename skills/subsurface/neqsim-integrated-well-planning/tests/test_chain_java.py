"""NeqSim-backed tests. They run when the wellplanning classes are on the classpath and skip with an explicit reason otherwise."""

import json
from pathlib import Path

import pytest

from integrated_well_planning import examples_data as ed, handoff, model_chain
from integrated_well_planning.runtime import ensure_runtime

pytestmark = pytest.mark.usefixtures("java")


@pytest.fixture(scope="module")
def oil_model():
    from integrated_well_planning.producers import ProducerModel

    return ProducerModel(ed.oil_producer_platform())


@pytest.fixture(scope="module")
def oil_ops(oil_model):
    return {c: oil_model.operating_point(c) for c in ("low", "base", "high")}


@pytest.fixture(scope="module")
def gc_model():
    from integrated_well_planning.producers import ProducerModel

    return ProducerModel(ed.gas_condensate_producer_subsea())


def test_runtime_reports_all_wellplanning_classes(runtime):
    assert runtime.jvm_started and runtime.wellplanning_available
    assert runtime.core["SystemSrkEos"] and runtime.has("NodalAnalysis")


def test_standard_factors_mass_balance():
    f = model_chain.standard_factors(ed.oil_producer_platform())
    assert 600.0 < f["kg_per_sm3_stock_tank_liquid"] < 1100.0 and f["gor_sm3_per_sm3"] > 10.0
    assert f["kg_per_sm3_gas_equivalent"] == pytest.approx(f["mw_kg_per_mol"] / 0.023645, rel=1e-9)
    g = model_chain.standard_factors(ed.gas_condensate_producer_subsea())
    assert g["cgr_sm3_per_msm3"] > 50.0


def test_water_moles_follow_water_cut():
    b = ed.oil_producer_platform()
    assert model_chain.water_moles_for_cut(b, 0.0) == 0.0
    assert model_chain.water_moles_for_cut(b, 0.5) > model_chain.water_moles_for_cut(b, 0.2) > 0.0


def test_oil_operating_point_is_consistent_with_ipr(oil_model, oil_ops):
    base = oil_ops["base"]
    assert base["status"] == "STABLE" and base["q_op"] > 0.0
    ipr = oil_model.ipr("base")
    assert float(ipr["pwf"](base["q_op"])) == pytest.approx(base["bhp_op"], abs=1.0)
    assert base["target_met"] == (base["surplus_at_target_bar"] >= 0.0)
    assert base["drawdown_bar"] == pytest.approx(base["params"]["pressure_bara"] - base["bhp_op"])


def test_oil_cases_are_ordered_low_base_high(oil_ops):
    assert oil_ops["low"]["q_op"] < oil_ops["base"]["q_op"] < oil_ops["high"]["q_op"]


def test_oil_profile_is_physical(oil_ops):
    prof = oil_ops["base"]["profile"]
    assert prof["pressure_bara"][0] < prof["pressure_bara"][-1]  # index 0 = wellhead
    assert all(0.0 <= h <= 1.0 for h in prof["liquid_holdup"])
    assert prof["temperature_C"][-1] > prof["temperature_C"][0] > 0.0
    wh = oil_ops["base"]["wellhead"]
    assert wh["pressure_bara"] >= oil_ops["base"]["params"]["host_pressure_bara"]


def test_larger_tubing_never_reduces_rate(oil_model):
    rows = oil_model.sweep("base", "tubing_id_m", [0.085, 0.12])
    assert rows[1]["q_op"] >= rows[0]["q_op"]


def test_higher_host_pressure_reduces_rate(oil_model):
    rows = oil_model.sweep("base", "host_pressure_bara", [20.0, 60.0])
    assert rows[1]["q_op"] < rows[0]["q_op"]


def test_gas_lift_increases_or_keeps_rate(oil_model):
    rows = oil_model.sweep("base", "lift_gas_sm3d", [0.0, 2.0e5])
    assert rows[1]["q_op"] >= rows[0]["q_op"] * 0.98


def test_java_nodal_cross_check_with_python_solver():
    from integrated_well_planning.nodal import solve_nodal
    from integrated_well_planning.runtime import jclass

    b = ed.oil_producer_platform()
    fluid = model_chain.build_fluid(b, 60.0, 30.0)
    Hyd, Nodal = jclass("DriftFluxWellboreHydraulics"), jclass("NodalAnalysis")
    hyd = Hyd(fluid).setTubing(0.1, 4.5e-5).setStraightWell(2500.0, 0.0, 10).setLinearTemperature(40.0, 90.0)
    java = Nodal(Nodal.linearInflow(250.0, 0.3), Nodal.fromDriftFlux(hyd, 30.0, 1.0)).setRateRange(1.0, 60.0).setScanPoints(24).solve().getOperatingPoint()

    def vlp(q):
        h = Hyd(model_chain.build_fluid(b, 60.0, 30.0)).setMassFlowRate(float(q)).setTubing(0.1, 4.5e-5).setStraightWell(2500.0, 0.0, 10).setLinearTemperature(40.0, 90.0)
        return float(h.calculateFromWellhead(30.0).getBottomholePressureBara())

    py = solve_nodal(lambda q: 250.0 - q / 0.3, vlp, 1.0, 60.0, n_scan=24, refine=10).operating_point
    assert py.rate == pytest.approx(float(java.getRate()), rel=0.05)


def test_gas_condensate_operating_point_and_dew_point(gc_model):
    r = gc_model.operating_point("base")
    assert r["dew_point_bara"] > 100.0 and r["status"] == "STABLE" and r["q_op"] > 0
    assert r["bottomhole"]["pressure_bara"] < r["params"]["pressure_bara"]
    assert r["tubing"]["turner_min"] is not None and r["wellhead"]["flowline_dp_bar"] > 0.0
    assert r["wellhead"]["pressure_bara"] > r["params"]["host_pressure_bara"]


def test_gas_condensate_ipr_is_monotonic(gc_model):
    t = gc_model.ipr("base")["table"]
    assert all(b >= a for a, b in zip(t["q"], t["q"][1:])) and all(b <= a + 1e-6 for a, b in zip(t["pwf"], t["pwf"][1:]))


def test_water_injector_whp_fracture_and_duty():
    from integrated_well_planning.injectors import InjectorModel

    m = InjectorModel(ed.water_injector_onshore())
    base = m.operating_point("base")
    assert base["status"] == "OK" and 0.0 < base["whp_required_bara"] < base["bhp_bara"]
    assert base["fracture_margin_bar"] > 0.0 and base["power_kw"] > 0.0 and base["bottomhole_temperature_C"] < 40.0
    assert base["gravity_gain_bar"] > base["friction_loss_bar"]
    hi = m.operating_point("base", rate=2500.0)
    assert hi["whp_required_bara"] > base["whp_required_bara"]
    rows = m.injectivity_curve("base", [40.0, 100.0])
    assert rows[1]["rate_m3d"] > rows[0]["rate_m3d"]


def test_gas_injector_pressure_and_compression():
    from integrated_well_planning.injectors import InjectorModel

    m = InjectorModel(ed.gas_injector_platform())
    base = m.operating_point("base")
    assert base["status"] == "OK" and base["whp_required_bara"] < base["bhp_bara"]
    d = base["surface_duty"]
    assert d["type"] == "compression" and d["power_kw"] > 0 and d["pressure_ratio"] > 1.5
    hi = m.operating_point("base", rate=2.0e6)
    assert hi["power_kw"] > base["power_kw"] and hi["bhp_required_bara"] > base["bhp_required_bara"]
    assert m.sweep_tubing("base", [0.1, 0.15])[1]["whp_required_bara"] <= m.sweep_tubing("base", [0.1])[0]["whp_required_bara"]


def test_integrity_block_for_producer(oil_ops):
    from integrated_well_planning.integrity import evaluate_integrity

    b = ed.oil_producer_platform()
    out = evaluate_integrity(b, producer=oil_ops["base"])
    states = {c["state"] for c in out["load_cases"]}
    assert {"production", "shut_in", "evacuated_tubing"} <= states
    assert out["apb"]["delta_pressure_bar"] > 0.0 and out["apb"]["delta_pressure_bar"] <= out["apb"]["rigid_limit_bar"] + 1e-6
    assert {m["packer_mode"] for m in out["tubing_movement"]} == {"FREE", "FIXED"}
    si = [c for c in out["load_cases"] if c["state"] == "shut_in"][0]
    assert si["pi_top_bara"] < 250.0
    assert all("NEEDS_REVIEW" in t["burst_status"] or t["burst_status"] in ("NOT_LOADED", "PASS", "FAIL") for t in out["tubing"] if t.get("rating_available"))


def test_design_factor_only_used_when_supplied(oil_ops):
    from integrated_well_planning.integrity import evaluate_integrity

    b = ed.oil_producer_platform()
    b["design_factors"] = {"burst": {"value": 1.1, "source": "operator casing-design standard (synthetic test value)"}}
    out = evaluate_integrity(b, producer=oil_ops["base"])
    rated = [t for t in out["tubing"] if t.get("rating_available") and t["burst_utilisation"] > 0]
    if rated:
        assert rated[0]["burst_status"] in ("PASS", "FAIL") and "burst_factor_source" in rated[0]


def test_hydrate_assessment_for_gas_condensate(gc_model):
    from integrated_well_planning.flow_assurance import hydrate_assessment

    r = gc_model.operating_point("base")
    r["shut_in_whp_bara"] = 300.0
    h = hydrate_assessment(ed.gas_condensate_producer_subsea(), r)
    assert h["status"] == "SCREENING" and h["wellhead_hydrate_T_C"] < 40.0
    assert h["inhibitor"]["required_weight_fraction"] >= 0.0 and h["shut_in_cooldown"]


def test_missing_wat_and_water_chemistry_are_not_performed():
    from integrated_well_planning.flow_assurance import scale_assessment, wax_assessment

    b = ed.oil_producer_platform()
    assert wax_assessment(b, {"profile": {"temperature_C": [20, 30]}})["status"] == "NOT_PERFORMED"
    assert scale_assessment(b)["status"] == "NOT_PERFORMED"
    b["fluid"]["wax_appearance_temperature_C"] = 25.0
    assert wax_assessment(b, {"profile": {"temperature_C": [20, 30]}})["margin_K"] == pytest.approx(-5.0)


def test_require_degrades_with_explicit_reason(monkeypatch):
    from integrated_well_planning.runtime import RuntimeStatus

    monkeypatch.setattr(model_chain, "ensure_runtime", lambda *a, **k: RuntimeStatus(jvm_started=True, wellplanning={"DriftFluxWellboreHydraulics": False}, reason="older NeqSim build"))
    with pytest.raises(model_chain.ModelUnavailable, match="not available.*older NeqSim build"):
        model_chain.require("DriftFluxWellboreHydraulics")


def test_end_to_end_water_injector_study(out_dir):
    from integrated_well_planning import study as st
    from integrated_well_planning.cli import main
    from integrated_well_planning.drawings_run import make_drawings
    from integrated_well_planning.report import build_report

    root = out_dir / "study"
    assert main(["init-study", str(root), "--well-type", "water_injector", "--environment", "onshore"]) == 0
    for sub in ("basis", "registers", "models", "results", "drawings", "report", "decisions"):
        assert (root / sub).is_dir()
    assert main(["validate-basis", str(root)]) == 0
    res = st.run_model(root)
    assert res["injector"]["base"]["status"] == "OK" and res["envelope"]["rows"]
    alt = st.alternatives(root, with_tornado=True)
    assert alt["recommendation"]["id"] and alt["tornado"]["rows"]
    st.envelope(root)
    d = make_drawings(root)
    assert any(r["status"] == "RENDERED" for r in d["register"]) and (root / "drawings" / "well_schematic.pdf").exists()
    rep = build_report(root)
    assert Path(rep["docx"]).stat().st_size > 50000 and rep["readiness"].startswith("SCREENING")
    text = Path(rep["md"]).read_text(encoding="utf-8")
    for heading in ("Executive summary", "Design basis", "Alternatives", "Operating-envelope", "Flow-assurance", "Validation evidence", "Revision control", "Drawings register", "Decision and action log"):
        assert heading in text
    assert "SYNTHETIC DEMONSTRATION" in text and "makes no compliance statement" in text
    for f in (root / "results" / "handoffs").glob("iwp_*.v1.json"):
        msg = json.loads(f.read_text(encoding="utf-8"))
        if msg.get("schema") == "iwp_handoff_envelope.v1":
            assert not handoff.validate_payload(msg["message_schema"], msg["payload"])
    assert (root / "models" / "rerun_model.py").exists()


def test_run_model_is_fail_closed_on_invalid_basis(out_dir):
    from integrated_well_planning import study as st
    from integrated_well_planning.basis import save_basis

    b = ed.water_injector_onshore()
    del b["reservoir"]["fracture_gradient_bar_per_m"]
    root = out_dir / "bad"
    st.init_study(root, basis=ed.water_injector_onshore())
    save_basis(b, root / "basis" / "planning_basis.yaml")
    with pytest.raises(ValueError, match="fail-closed"):
        st.run_model(root)


def test_oil_producer_full_run_model(out_dir):
    from integrated_well_planning import study as st

    root = out_dir / "oil"
    st.init_study(root, basis=ed.oil_producer_platform())
    res = st.run_model(root, segments=8)
    assert res["producer"]["base"]["q_op"] > 0 and res["flow_assurance"]["transient"]["status"] == "EXTERNAL_TOOL_REQUIRED"
    assert res["integrity"]["apb"] and res["envelope"]["summary"]["NEEDS_REVIEW"] > 0
    names = {p.name for p in (root / "results" / "handoffs").glob("*.json")}
    assert {"iwp_vfp_request.v1.json", "iwp_well_model.v1.json", "iwp_operating_envelope.v1.json", "iwp_trajectory.v1.json", "iwp_integrity_inputs.v1.json",
            "iwp_flow_assurance_requirements.v1.json"} <= names
    vfp = json.loads((root / "results" / "handoffs" / "iwp_vfp_request.v1.json").read_text())
    assert vfp["to_agent"] == "vfp-lift-curve-agent" and vfp["payload"]["table_kind"] == "VFPPROD"
