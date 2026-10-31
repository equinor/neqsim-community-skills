import pytest

from integrated_well_planning import barriers, drilling_interfaces as di, envelope, examples_data as ed, handoff, ledger, standards
from integrated_well_planning.nodal import composite_oil_ipr, solve_nodal
from integrated_well_planning.registers import get_path


# ----------------------------------------------------------------------------- envelope
def test_envelope_missing_source_is_needs_review_not_pass():
    r = envelope.evaluate_row("E1", "p", "c", "bar", 10.0, "calc", max_limit=100.0, limit_source="", limit_basis="APPROVED")
    assert r.status == "NEEDS_REVIEW" and r.indicative_status == "PASS"


def test_envelope_unapproved_limit_stays_needs_review_but_indicates():
    r = envelope.evaluate_row("E1", "p", "c", "bar", 120.0, "calc", max_limit=100.0, limit_source="synthetic", limit_basis="SYNTHETIC")
    assert r.status == "NEEDS_REVIEW" and r.indicative_status == "FAIL" and r.margin_to_limit == pytest.approx(-20.0)


def test_envelope_approved_limits_traffic_lights():
    mk = lambda v: envelope.evaluate_row("E", "p", "c", "-", v, "calc", max_limit=1.0, limit_source="datasheet", limit_basis="APPROVED")  # noqa: E731
    assert mk(0.5).status == "PASS" and mk(0.95).status == "WARN" and mk(1.2).status == "FAIL"


def test_envelope_min_limit_and_margin_factor_requires_source():
    r = envelope.evaluate_row("E", "m", "c", "K", 5.0, "calc", min_limit=3.0, limit_source="operator", limit_basis="APPROVED")
    assert r.status == "PASS" and r.margin_to_limit == pytest.approx(2.0)
    with_src = envelope.evaluate_row("E", "m", "c", "K", 5.0, "calc", min_limit=3.0, limit_source="operator", limit_basis="APPROVED", margin_factor=2.0, margin_source="design basis")
    assert with_src.status == "FAIL"  # effective minimum 6 K
    no_src = envelope.evaluate_row("E", "m", "c", "K", 5.0, "calc", min_limit=3.0, limit_source="operator", limit_basis="APPROVED", margin_factor=2.0)
    assert no_src.status == "PASS" and "IGNORED" in no_src.design_margin


def test_envelope_without_prediction_is_not_assessed():
    assert envelope.evaluate_row("E", "p", "c", "-", None, "", max_limit=1.0, limit_source="x", limit_basis="APPROVED").status == "NOT_ASSESSED"


def test_envelope_rejects_unknown_limit_basis():
    with pytest.raises(ValueError):
        envelope.evaluate_row("E", "p", "c", "-", 1.0, "", limit_basis="MADE_UP")


def test_envelope_markdown_and_summary():
    rows = [envelope.evaluate_row("E1", "a", "c", "-", 0.5, "calc", max_limit=1.0, limit_source="s", limit_basis="APPROVED")]
    assert "| E1 | a |" in envelope.to_markdown(rows) and envelope.summarise(rows)["PASS"] == 1


# ----------------------------------------------------------------------------- standards
def test_standards_register_starts_unverified():
    reg = standards.seed_register()
    assert len(reg) >= 10 and all(e.status == "TO_VERIFY" and e.edition_checked == "NOT_VERIFIED" for e in reg)
    assert not standards.ready_for_compliance_statement(reg)
    assert any("D-010" in e.source_document for e in reg) and any("ISO 16530" in e.source_document for e in reg) and any("15156" in e.source_document for e in reg)


def test_standards_compliance_needs_evidence_and_edition():
    reg = standards.seed_register()
    with pytest.raises(ValueError):
        standards.update_entry(reg, "STD-001", status="COMPLIANT_EVIDENCE_REVIEWED")
    e = standards.update_entry(reg, "STD-001", status="COMPLIANT_EVIDENCE_REVIEWED", evidence="review report R-1", edition_checked="verified edition (operator document control)")
    assert e.status == "COMPLIANT_EVIDENCE_REVIEWED"
    with pytest.raises(KeyError):
        standards.update_entry(reg, "STD-999", status="TO_VERIFY")


def test_standards_contains_no_numeric_design_factors():
    text = " ".join(e.requirement_topic + e.verification_method for e in standards.seed_register())
    assert "design factor of" not in text.lower()


# ----------------------------------------------------------------------------- ledger
def test_ledger_uses_exactly_the_four_labels_and_covers_all_classes():
    from integrated_well_planning.runtime import RuntimeStatus

    rt = RuntimeStatus(jvm_started=True, wellplanning={n: True for n in ("WellboreThermalModel", "DriftFluxWellboreHydraulics", "GasCondensateInflowModel", "AnnularPressureBuildup", "TubingMovementCalculator",
                                                                          "WellChemicalTreatment", "InjectionWellHydraulics", "NodalAnalysis")}, core={"SystemSrkEos": True, "ThermodynamicOperations": True})
    rows = ledger.ledger_rows(rt)
    assert {r["status"] for r in rows} == set(ledger.STATUS)
    text = " ".join(r["implementation"] for r in rows)
    for cls in ("WellboreThermalModel", "DriftFluxWellboreHydraulics", "GasCondensateInflowModel", "AnnularPressureBuildup", "TubingMovementCalculator", "WellChemicalTreatment", "InjectionWellHydraulics", "NodalAnalysis"):
        assert cls in text
    assert all(r["available"] for r in rows)


def test_ledger_marks_missing_classes_unavailable():
    from integrated_well_planning.runtime import RuntimeStatus

    rt = RuntimeStatus(jvm_started=True, wellplanning={"WellboreThermalModel": False}, core={})
    rows = {r["id"]: r for r in ledger.ledger_rows(rt)}
    assert rows["L01"]["available"] is False and rows["L25"]["available"] is True
    assert ledger.JAVA_FOLLOW_UPS


def test_external_tool_rows_carry_a_route():
    for e in ledger.build_ledger():
        if e.status == "EXTERNAL_TOOL_REQUIRED":
            assert e.route_if_not_available


# ----------------------------------------------------------------------------- barriers and interfaces
def test_barrier_states_have_both_envelopes_and_are_unverified():
    b = ed.oil_producer_platform()
    states = barriers.propose_barriers(b)
    assert {s.state for s in states} >= {"production", "shut_in", "intervention", "abandonment"}
    for s in states:
        assert {e.envelope for e in s.elements} == {"primary", "secondary"}
        assert all(e.verification_status == "UNVERIFIED" for e in s.elements)
    assert barriers.barrier_summary(states)["compliance_statement"].startswith("NONE")


def test_injector_barriers_use_injection_state_and_subsea_valves():
    s = barriers.propose_barriers(ed.gas_condensate_producer_subsea())
    assert any("subsea" in e.name for e in s[0].elements)
    assert barriers.propose_barriers(ed.water_injector_onshore())[0].state == "injection"


def test_barrier_verification_requires_evidence():
    states = barriers.propose_barriers(ed.oil_producer_platform())
    with pytest.raises(ValueError):
        barriers.set_verification(states, "P1", "production", "VERIFIED", "")
    barriers.set_verification(states, "P1", "production", "VERIFIED", "test record T-1")
    assert [e for e in states[0].elements if e.id == "P1"][0].verification_status == "VERIFIED"


def test_interface_specs_are_unresolved_and_state_missing_inputs():
    specs = di.interface_specifications(ed.oil_producer_platform())
    assert len(specs) >= 6 and all(s["status"] == "UNRESOLVED" for s in specs)
    assert any(s["inputs_missing"] for s in specs)
    assert all("No calculation is claimed" in s["statement"] for s in specs)


def test_trajectory_geometry_and_pressure_window():
    t = di.trajectory_from_basis(ed.oil_producer_platform())
    assert t["status"] == "PASS" and t["summary"]["max_inclination_deg"] == 0.0
    t2 = di.trajectory_from_basis(ed.gas_condensate_producer_subsea())
    assert t2["status"] == "PASS" and t2["summary"]["max_dls_deg_per_30m"] <= 3.05
    w = di.pressure_window(ed.oil_producer_platform())
    assert w["rows"] and all(r["window_open"] for r in w["rows"])


def test_casing_ratings_need_drilling_module_or_say_so():
    rows = di.casing_ratings(ed.oil_producer_platform())
    assert rows and all("available" in r for r in rows)
    if rows[0]["available"]:
        assert rows[0]["burst_bar"] > 0 and rows[0]["collapse_bar"] > 0


# ----------------------------------------------------------------------------- nodal
def test_composite_ipr_inverse_and_aof():
    c = composite_oil_ipr(250.0, 120.0, 20.0)
    assert c["rate"](250.0) == pytest.approx(0.0, abs=1e-9)
    assert c["rate"](200.0) == pytest.approx(1000.0)
    assert c["pwf"](c["rate"](60.0)) == pytest.approx(60.0, abs=1e-6)
    assert c["aof"] == pytest.approx(20.0 * 130.0 + 20.0 * 120.0 / 1.8)


def test_nodal_stable_and_unstable_intersections():
    ipr = lambda q: 250.0 - q / 20.0  # noqa: E731
    u_vlp = lambda q: 120.0 + 0.00008 * (q - 1500.0) ** 2  # U-shaped outflow
    res = solve_nodal(ipr, u_vlp, 50.0, 5000.0, n_scan=60)
    assert res.status == "STABLE"
    stab = [i for i in res.intersections if i.stable]
    unst = [i for i in res.intersections if not i.stable]
    assert stab and unst and stab[-1].rate > unst[0].rate
    assert res.operating_point.rate == stab[-1].rate and res.outflow_min_rate == pytest.approx(1500.0, rel=0.1)


def test_nodal_no_intersection():
    res = solve_nodal(lambda q: 100.0, lambda q: 300.0, 10.0, 100.0)
    assert res.status == "NO_INTERSECTION" and res.operating_point is None


def test_nodal_linear_closed_form():
    res = solve_nodal(lambda q: 250.0 - q / 20.0, lambda q: 100.0 + q / 100.0, 10.0, 5000.0, n_scan=40, refine=20)
    q_star = (250.0 - 100.0) / (1 / 20.0 + 1 / 100.0)
    assert res.operating_point.rate == pytest.approx(q_star, rel=1e-3)


# ----------------------------------------------------------------------------- hand-off
def test_all_schemas_load_and_are_versioned():
    for name in handoff.MESSAGES:
        s = handoff.load_schema(name)
        assert s["$id"] == name and name.endswith(".v1")
    assert handoff.load_schema("iwp_handoff_envelope.v1")["required"]


def test_envelope_validation_rejects_bad_payload():
    with pytest.raises(ValueError):
        handoff.make_envelope("iwp_host_constraints.v1", {"host_id": "H"}, "well-planning-engineer", "S1")
    ok = handoff.make_envelope("iwp_host_constraints.v1", {"host_id": "H", "pressure_bara": {"base": 50.0}}, "well-planning-engineer", "S1", from_agent="tie-in-screening-agent")
    assert ok["schema"] == "iwp_handoff_envelope.v1" and ok["status"] == "DRAFT"


def test_apply_host_constraints_records_supplied_provenance():
    b = ed.oil_producer_platform()
    msg = handoff.make_envelope("iwp_host_constraints.v1", {"host_id": "H1", "pressure_bara": {"low": 40, "base": 45, "high": 50}, "temperature_C": 35.0, "source": "host study R2"},
                                "well-planning-engineer", "IWP-DEMO-A", from_agent="tie-in-screening-agent")
    out = handoff.apply_host_constraints(b, msg)
    assert out["facility"]["host_pressure_bara"]["base"] == 45
    assert out["provenance"]["facility.host_pressure_bara"]["class"] == "SUPPLIED" and "tie-in-screening-agent" in out["provenance"]["facility.host_pressure_bara"]["source"]
    assert b["facility"]["host_pressure_bara"]["base"] == 25.0  # input not mutated


def test_apply_fluid_and_trajectory_messages():
    b = ed.oil_producer_platform()
    fm = handoff.make_envelope("iwp_fluid_basis.v1", {"fluid_id": "F1", "eos": "PR", "components": [{"name": "methane", "mole_fraction": 0.6}, {"name": "n-decane", "mole_fraction": 0.4}],
                                                      "wax_appearance_temperature_C": 28.0, "source": "lab report L-7"}, "well-planning-engineer", "S", from_agent="fluid-characterization-agent")
    out = handoff.apply_fluid_basis(b, fm)
    assert out["fluid"]["eos"] == "PR" and out["fluid"]["wax_appearance_temperature_C"] == 28.0
    tm = handoff.make_envelope("iwp_trajectory.v1", {"well_id": "A-1", "depth_reference": "RKB", "stations": [{"md_m": 0, "inc_deg": 0, "azi_deg": 0, "tvd_m": 0}, {"md_m": 2500, "inc_deg": 0, "azi_deg": 0, "tvd_m": 2500}]},
                               "well-planning-engineer", "S", from_agent="well-trajectory-anticollision-agent")
    out2 = handoff.apply_trajectory(b, tm)
    assert out2["trajectory"]["md_m"] == 2500 and out2["provenance"]["trajectory.stations"]["class"] == "SUPPLIED"


def test_wrong_message_type_is_refused():
    b = ed.oil_producer_platform()
    msg = handoff.make_envelope("iwp_host_constraints.v1", {"host_id": "H", "pressure_bara": 40.0}, "x", "S")
    with pytest.raises(ValueError):
        handoff.apply_fluid_basis(b, msg)


def test_route_table_names_only_catalog_style_agents():
    names = {a for r in handoff.ROUTES.values() for k in ("in_from", "out_to") for a in r.get(k, [])}
    assert "vfp-lift-curve-agent" in names and "well-trajectory-anticollision-agent" in names and "asset-economics-agent" in names
    assert all(n == n.lower() and " " not in n for n in names)
