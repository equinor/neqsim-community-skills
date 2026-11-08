import json

import pytest

from subsea_equipment_placement import (
    LIMIT_CATALOG, Limit, PlacementBasis, limits_gap_register, limits_template, load_limits, screen_site, write_limits_template,
)


def test_template_lists_every_catalogue_limit_with_no_value():
    t = limits_template()
    assert set(t["limits"]) == set(LIMIT_CATALOG)
    assert all(v["value"] is None and v["basis"] == "NONE" for v in t["limits"].values())
    assert all(lim.value is None and lim.basis == "NONE" for lim in load_limits(t).values())


def test_template_file_roundtrip(tmp_path):
    path = write_limits_template(tmp_path / "limits.json")
    assert set(json.load(open(path, encoding="utf-8"))["limits"]) == set(LIMIT_CATALOG)
    assert len(load_limits(path)) == len(LIMIT_CATALOG)


def test_load_limits_accepts_a_sourced_limit_and_keeps_an_assumed_one_unapproved():
    lims = load_limits({"limits": {"max_stepout_m": {"value": 25000.0, "unit": "m", "source": "catalogue 3.2", "basis": "SUPPLIED"},
                                   "max_slope_deg": {"value": 3.0, "unit": "deg", "basis": "ASSUMED"}}})
    assert lims["max_stepout_m"].approved
    assert not lims["max_slope_deg"].approved and lims["max_slope_deg"].basis == "ASSUMED"


@pytest.mark.parametrize("doc,fragment", [
    ({"nope": {"value": 1.0}}, "unknown limit key"),
    ({"max_stepout_m": {"value": 25000.0, "unit": "m", "basis": "SUPPLIED"}}, "needs a value and a source"),
    ({"max_stepout_m": {"value": 25000.0, "unit": "km", "source": "x", "basis": "SUPPLIED"}}, "does not match"),
    ({"max_stepout_m": {"value": "far", "unit": "m", "source": "x", "basis": "SUPPLIED"}}, "finite number"),
    ({"max_stepout_m": {"value": 1.0, "unit": "m", "source": "x", "basis": "GUESS"}}, "basis must be one of"),
])
def test_invalid_limits_are_rejected_with_a_reason(doc, fragment):
    with pytest.raises(ValueError, match=fragment):
        load_limits(doc)


def test_value_without_basis_is_treated_as_assumed_and_null_value_as_none():
    lims = load_limits({"max_slope_deg": {"value": 2.0}, "max_erd_ratio": {"value": None}})
    assert lims["max_slope_deg"].basis == "ASSUMED" and not lims["max_slope_deg"].approved
    assert lims["max_erd_ratio"].basis == "NONE"


def test_gap_register_names_what_closes_each_open_limit():
    lims = load_limits({"max_stepout_m": {"value": 25000.0, "unit": "m", "source": "catalogue 3.2", "basis": "SUPPLIED"},
                        "max_slope_deg": {"value": 3.0, "unit": "deg", "basis": "ASSUMED"}})
    rows = {r["key"]: r for r in limits_gap_register(lims)}
    assert rows["max_stepout_m"]["status"] == "CLOSED" and rows["max_stepout_m"]["closed_by"] == ""
    assert rows["max_slope_deg"]["status"] == "OPEN" and rows["max_slope_deg"]["closed_by"]
    assert rows["line_clearance_m"]["status"] == "OPEN" and "risk assessment" in rows["line_clearance_m"]["closed_by"]
    assert len(rows) == len(LIMIT_CATALOG)


def test_minimum_water_depth_check_is_added_only_when_a_limit_is_given():
    depth = lambda x, y: 95.0
    ok = PlacementBasis(depth_fn=depth, limits=load_limits({"min_water_depth_m": {"value": 80.0, "unit": "m", "source": "s", "basis": "SUPPLIED"},
                                                           "max_water_depth_m": {"value": 500.0, "unit": "m", "source": "s", "basis": "SUPPLIED"}}))
    rows = {c["id"]: c for c in screen_site((0.0, 0.0), ok)["checks"]}
    assert rows["DEPTH_MIN"]["status"] == "PASS" and rows["DEPTH"]["status"] == "PASS"
    shallow = PlacementBasis(depth_fn=lambda x, y: 60.0, limits=ok.limits)
    result = screen_site((0.0, 0.0), shallow)
    assert result["verdict"] == "FAIL" and "DEPTH_MIN" in result["hard_fail"]
    none = {c["id"] for c in screen_site((0.0, 0.0), PlacementBasis(depth_fn=depth))["checks"]}
    assert "DEPTH_MIN" not in none
