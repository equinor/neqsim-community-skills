import copy

import pytest

from integrated_well_planning import datums, examples_data as ed
from integrated_well_planning.basis import (CASES, basis_to_registers, case_value, load_basis, rng, save_basis, template_basis, validate_basis)
from integrated_well_planning.registers import Registers, RegisterItem, get_path, registers_from_basis


def _cases():
    return ed.all_cases()


@pytest.mark.parametrize("name", sorted(ed.all_cases()))
def test_worked_cases_validate_without_errors(name):
    rep = validate_basis(_cases()[name])
    assert rep.errors == []
    assert rep.status == "WARN"  # synthetic flag and open gaps are always visible


def test_four_cases_cover_types_and_environments():
    cs = _cases().values()
    assert {get_path(c, "well.type") for c in cs} == {"oil_producer", "gas_condensate_producer", "water_injector", "gas_injector"}
    assert {get_path(c, "well.environment") for c in cs} == {"platform", "subsea", "onshore"}


def test_synthetic_cases_are_flagged_and_never_measured():
    for c in _cases().values():
        assert get_path(c, "study.synthetic") is True
        assert all(m["class"] == "ASSUMED" for m in c["provenance"].values())


def test_missing_required_input_fails_closed():
    b = _cases()["oil_producer_platform"]
    del b["reservoir"]["permeability_md"]
    rep = validate_basis(b)
    assert rep.status == "FAIL" and any("permeability" in e for e in rep.errors)


def test_composition_must_sum_to_one():
    b = _cases()["oil_producer_platform"]
    b["fluid"]["components"][0]["mole_fraction"] = 0.9
    assert any("sums to" in e for e in validate_basis(b).errors)


def test_temperature_unit_sanity():
    b = _cases()["oil_producer_platform"]
    b["reservoir"]["temperature_C"] = 363.0  # Kelvin by mistake
    assert any("Celsius" in e for e in validate_basis(b).errors)


def test_tvd_cannot_exceed_md():
    b = _cases()["oil_producer_platform"]
    b["trajectory"]["tvd_m"] = b["trajectory"]["md_m"] + 50
    assert any("exceeds md" in e for e in validate_basis(b).errors)


def test_measured_not_allowed_in_synthetic_study():
    b = _cases()["oil_producer_platform"]
    b["provenance"]["reservoir.temperature_C"]["class"] = "MEASURED"
    assert any("MEASURED not allowed" in e for e in validate_basis(b).errors)


def test_supplied_needs_source():
    b = _cases()["oil_producer_platform"]
    b["study"]["synthetic"] = False
    b["provenance"]["reservoir.temperature_C"] = {"class": "SUPPLIED"}
    assert any("requires a source" in e for e in validate_basis(b).errors)


def test_strict_provenance_turns_warnings_into_errors():
    b = _cases()["oil_producer_platform"]
    b["provenance"].pop("reservoir.skin", None)
    assert validate_basis(b).errors == []
    assert any("no provenance" in e for e in validate_basis(b, strict_provenance=True).errors)


def test_range_helper_orders_and_rejects_bad_ranges():
    assert rng({"low": 1, "base": 2, "high": 3}) == (1.0, 2.0, 3.0)
    assert rng(5) == (5.0, 5.0, 5.0)
    with pytest.raises(ValueError):
        rng({"low": 3, "base": 2, "high": 1})
    assert case_value({"low": 1, "base": 2, "high": 3}, "high") == 3.0


def test_template_basis_for_every_well_type_and_environment():
    for wt in ("oil_producer", "gas_producer", "gas_condensate_producer", "water_injector", "gas_injector"):
        for env in ("onshore", "platform", "subsea"):
            b = template_basis(wt, env)
            assert b["well"]["type"] == wt and b["well"]["environment"] == env
            assert validate_basis(b).errors == []


def test_basis_round_trip_yaml_and_json(out_dir):
    b = _cases()["gas_injector_platform"]
    for name in ("b.yaml", "b.json"):
        save_basis(b, out_dir / name)
        assert load_basis(out_dir / name) == b


def test_planning_basis_schema_accepts_cases():
    jsonschema = pytest.importorskip("jsonschema")
    from integrated_well_planning.handoff import load_schema

    schema = load_schema("iwp_planning_basis.v1")
    for c in _cases().values():
        jsonschema.Draft7Validator(schema).validate(c)


def test_registers_gaps_decisions_actions_and_persistence(out_dir):
    reg = basis_to_registers(_cases()["oil_producer_platform"])
    assert reg.provenance_counts()["ASSUMED"] > 5
    assert any(g.key == "limits" or g.key == "fluid.pvt_measurements" for g in reg.gaps)
    d = reg.add_decision("Tubing", "100 mm", "meets target", ["85 mm"], "PROPOSED")
    a = reg.add_action("get PVT", "pvt lead")
    assert d.id == "D-001" and a.id == "A-001"
    reg.close_action(a.id)
    assert reg.open_actions() == []
    reg.save(out_dir)
    again = Registers.load(out_dir)
    assert len(again.decisions) == 1 and again.items.keys() == reg.items.keys()
    assert (out_dir / "source_register.csv").exists() and (out_dir / "data_gaps.csv").exists()


def test_register_item_rules():
    assert RegisterItem("x", 1, provenance="MEASURED", source="", synthetic=False).validate()
    assert RegisterItem("x", 1, provenance="MEASURED", source="lab", synthetic=True).validate()
    assert not RegisterItem("x", 1, provenance="ASSUMED").validate()


def test_get_path_navigates_lists_and_dicts():
    d = {"a": {"b": [{"c": 3}]}}
    assert get_path(d, "a.b.0.c") == 3 and get_path(d, "a.x", "none") == "none"


def test_minimum_curvature_vertical_and_build():
    s = datums.minimum_curvature([0, 500, 1000], [0, 0, 0], [0, 0, 0])
    assert s["tvd"][-1] == pytest.approx(1000.0) and max(s["dls"]) == 0.0
    b = datums.build_and_hold(500.0, 3.0, 30.0, 2000.0, 90.0)
    assert b["inc"][-1] == pytest.approx(30.0) and max(b["dls"]) == pytest.approx(3.0, rel=0.05)
    assert b["tvd"][-1] < 2000.0 and b["east"][-1] > 300.0


def test_datum_conversion_and_consistency():
    ref = datums.DepthReference(reference_elevation_msl_m=25.0, water_depth_m=300.0, environment="subsea")
    assert ref.tvdss(1025.0) == 1000.0 and ref.seabed_tvd_m() == 325.0
    assert datums.check_datum_consistency(1000.0, 1200.0)
    s = datums.build_and_hold(300.0, 2.0, 20.0, 1500.0)
    assert datums.check_datum_consistency(1500.0, s["tvd"][-1], 20.0, s) == []
    assert datums.barg_to_bara(10.0) == pytest.approx(11.01325)
