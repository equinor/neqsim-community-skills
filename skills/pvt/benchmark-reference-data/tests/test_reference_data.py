from __future__ import annotations

import pytest

from benchmark_reference_data.reference_data import (
    ANCHOR_POINTS,
    AnchorNotFoundError,
    anchors_for,
    available_fluids,
    find_anchor,
    normalise_fluid,
)


def test_every_anchor_resolves_to_a_registered_source():
    for point in ANCHOR_POINTS:
        assert point.source.citation


def test_every_anchor_has_a_unit_and_positive_value():
    for point in ANCHOR_POINTS:
        assert point.unit
        assert point.value > 0.0


def test_water_critical_point_matches_iapws95():
    assert find_anchor("water", "critical_temperature").value == pytest.approx(647.096)
    assert find_anchor("water", "critical_pressure").value == pytest.approx(22.064e6)


def test_co2_critical_point_matches_span_wagner():
    point = find_anchor("carbon dioxide", "critical_temperature")
    assert point.value == pytest.approx(304.1282)
    assert point.source_key == "span_wagner_co2"


def test_aliases_resolve_to_canonical_fluid_names():
    assert normalise_fluid("H2O") == "water"
    assert normalise_fluid("C1") == "methane"
    assert normalise_fluid("Methane") == "methane"


def test_state_filter_selects_the_right_point():
    point = find_anchor("water", "density", temperature_K=298.15, pressure_Pa=101325.0)
    assert point.value == pytest.approx(997.047)
    assert point.state["temperature_K"] == pytest.approx(298.15)


def test_state_filter_rejects_a_state_that_is_not_tabulated():
    with pytest.raises(AnchorNotFoundError):
        find_anchor("water", "density", temperature_K=350.0, pressure_Pa=101325.0)


def test_missing_property_error_lists_available_fluids():
    with pytest.raises(AnchorNotFoundError) as excinfo:
        find_anchor("methane", "not_a_property")
    assert "methane" in str(excinfo.value)


def test_anchors_for_returns_only_that_fluid():
    points = anchors_for("nitrogen")
    assert points
    assert {p.fluid for p in points} == {"nitrogen"}


def test_available_fluids_covers_the_common_light_ends():
    fluids = set(available_fluids())
    assert {"water", "co2", "methane", "nitrogen", "ethane", "propane"} <= fluids


def test_effective_uncertainty_falls_back_to_the_source():
    point = find_anchor("co2", "critical_temperature")
    assert point.effective_uncertainty_pct() == pytest.approx(0.1)


def test_state_summary_is_readable():
    point = find_anchor("water", "density", temperature_K=298.15, pressure_Pa=101325.0)
    assert "temperature_K=298.15" in point.state_summary()
    assert find_anchor("water", "critical_temperature").state_summary() == "-"
