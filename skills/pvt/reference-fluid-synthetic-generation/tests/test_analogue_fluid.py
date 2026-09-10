"""Tests for the analogue fluid basis - the no-PVT-data path.

The cases here are the ways a synthetic fluid basis misleads: a hydrostatic
pressure taken as truth, a depth trend extrapolated past its analogues, a GOR
quoted without its definition, and a synthetic basis presented as if it were
measured.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reference_fluid import (  # noqa: E402
    FluidAnalogue,
    api_to_density,
    build_analogue_fluid_basis,
    classify_fluid_type,
    density_to_api,
    estimate_reservoir_conditions,
    interpolate_by_depth,
    reconcile_gor_definitions,
    reconcile_with_measured,
)

ANALOGUES = [
    FluidAnalogue("Shallow", "brent", 1800.0, 35.0, 120.0),
    FluidAnalogue("Mid", "brent", 2600.0, 38.0, 180.0),
    FluidAnalogue("Deep", "brent", 2800.0, 39.0, 250.0),
    FluidAnalogue("HPHT", "brent", 4000.0, 45.0, 900.0),
]


# -- conditions ------------------------------------------------------------
def test_temperature_uses_the_depth_below_mudline_not_the_tvdss():
    shallow_water = estimate_reservoir_conditions(
        datum_tvdss_m=3000.0, water_depth_m=100.0, sea_area="north_sea")
    deep_water = estimate_reservoir_conditions(
        datum_tvdss_m=3000.0, water_depth_m=1500.0, sea_area="north_sea")
    assert deep_water["temperature_C"]["value"] < shallow_water["temperature_C"]["value"]


def test_a_measured_temperature_is_labelled_measured_and_keeps_the_estimate():
    record = estimate_reservoir_conditions(
        datum_tvdss_m=3590.0, water_depth_m=381.0, sea_area="north_sea",
        measured_temperature_C=129.0)
    assert record["temperature_C"]["value"] == 129.0
    assert record["temperature_C"]["provenance"] == "measured"
    assert "estimate_if_measured_supplied" in record["temperature_C"]
    assert "deviation_from_correlation_C" in record["temperature_C"]


def test_overpressure_is_quantified_against_hydrostatic():
    record = estimate_reservoir_conditions(
        datum_tvdss_m=3590.0, water_depth_m=381.0, sea_area="north_sea",
        measured_pressure_bara=542.0)
    assert record["pressure_bara"]["overpressure_bar"] > 150
    assert "refuted" in record["pressure_bara"]["note"]


def test_hydrostatic_carries_a_warning_because_it_is_an_assumption():
    record = estimate_reservoir_conditions(datum_tvdss_m=3000.0)
    assert record["pressure_bara"]["provenance"] == "correlation"
    assert any("assumption" in w for w in record["warnings"])


def test_a_strong_overpressure_regime_raises_the_estimate():
    hydro = estimate_reservoir_conditions(datum_tvdss_m=3590.0)
    over = estimate_reservoir_conditions(
        datum_tvdss_m=3590.0, pressure_regime="strong_overpressure")
    assert over["pressure_bara"]["value"] > hydro["pressure_bara"]["value"] + 100


@pytest.mark.parametrize("bad", [{"sea_area": "mars"}, {"pressure_regime": "guess"}])
def test_an_unknown_regime_is_refused(bad):
    with pytest.raises(ValueError):
        estimate_reservoir_conditions(datum_tvdss_m=3000.0, **bad)


def test_a_negative_datum_is_refused():
    with pytest.raises(ValueError):
        estimate_reservoir_conditions(datum_tvdss_m=-10.0)


# -- fluid type ------------------------------------------------------------
@pytest.mark.parametrize("gor,expected", [
    (10.0, "heavy_oil"), (120.0, "black_oil"), (290.0, "volatile_oil"),
    (700.0, "near_critical"), (5000.0, "gas_condensate"), (50000.0, "dry_gas"),
])
def test_fluid_type_bands(gor, expected):
    assert classify_fluid_type(gor)["fluid_type"] == expected


def test_a_fluid_near_a_band_edge_is_flagged_not_forced():
    record = classify_fluid_type(480.0)
    assert record["on_boundary"] is True
    assert "not firm" in record["boundary_note"]


def test_a_gas_condensate_is_told_it_needs_pvtg_not_pvto():
    assert "PVTG" in classify_fluid_type(5000.0)["modelling_note"]


def test_a_light_gor_with_a_heavy_api_is_called_inconsistent():
    record = classify_fluid_type(300.0, api_degrees=14.0)
    assert "inconsistent" in record["inconsistency"]


def test_a_negative_gor_is_refused():
    with pytest.raises(ValueError):
        classify_fluid_type(-1.0)


# -- density conversions ---------------------------------------------------
def test_api_and_density_round_trip():
    assert density_to_api(api_to_density(41.0)) == pytest.approx(41.0, abs=1e-6)


def test_a_light_oil_is_less_dense_than_a_heavy_one():
    assert api_to_density(45.0) < api_to_density(20.0)


def test_an_unphysical_api_is_refused():
    with pytest.raises(ValueError):
        api_to_density(-200.0)


# -- analogue trend --------------------------------------------------------
def test_interpolation_reports_which_analogues_bracket_the_target():
    record = interpolate_by_depth(ANALOGUES, 2700.0, "gor_sm3_sm3")
    assert record["extrapolated"] is False
    assert record["bracketing"] == ["Mid", "Deep"]
    assert 180.0 < record["value"] < 250.0


def test_beyond_the_deepest_analogue_the_value_is_clamped_not_extrapolated():
    record = interpolate_by_depth(ANALOGUES, 6000.0, "gor_sm3_sm3")
    assert record["extrapolated"] is True
    assert record["value"] == 900.0
    assert record["clamped_to"] == "HPHT"
    assert "not extrapolated" in record["note"]


def test_above_the_shallowest_analogue_the_value_is_clamped():
    record = interpolate_by_depth(ANALOGUES, 500.0, "api_degrees")
    assert record["value"] == 35.0 and record["extrapolated"] is True


def test_an_empty_analogue_set_is_refused():
    with pytest.raises(ValueError):
        interpolate_by_depth([], 3000.0, "gor_sm3_sm3")


# -- the basis -------------------------------------------------------------
def test_a_basis_with_no_measurements_is_declared_synthetic():
    basis = build_analogue_fluid_basis(datum_tvdss_m=3590.0, analogues=ANALOGUES,
                                       water_depth_m=381.0, sea_area="north_sea")
    assert basis["confidence"]["level"] == "synthetic"
    assert "synthetic estimate" in basis["confidence"]["statement"]


def test_supplying_every_measurement_makes_the_basis_measured():
    basis = build_analogue_fluid_basis(
        datum_tvdss_m=3590.0, analogues=ANALOGUES, water_depth_m=381.0,
        sea_area="north_sea", measured_temperature_C=129.0,
        measured_pressure_bara=542.0, measured_gor_sm3_sm3=290.0,
        measured_api_degrees=41.0)
    assert basis["confidence"]["level"] == "measured"
    assert basis["open_assumptions"] == 2  # F5 gas analysis, F6 grading


def test_low_base_high_bracket_the_base_case():
    basis = build_analogue_fluid_basis(datum_tvdss_m=2700.0, analogues=ANALOGUES)
    cases = basis["cases"]
    assert cases["low"]["gor_sm3_sm3"] < cases["base"]["gor_sm3_sm3"] < cases["high"]["gor_sm3_sm3"]
    assert cases["low"]["sto_density_kg_m3"] > cases["high"]["sto_density_kg_m3"]


def test_a_measured_gor_narrows_the_spread():
    wide = build_analogue_fluid_basis(datum_tvdss_m=2700.0, analogues=ANALOGUES)
    narrow = build_analogue_fluid_basis(datum_tvdss_m=2700.0, analogues=ANALOGUES,
                                        measured_gor_sm3_sm3=200.0)
    wide_span = wide["cases"]["high"]["gor_sm3_sm3"] - wide["cases"]["low"]["gor_sm3_sm3"]
    narrow_span = narrow["cases"]["high"]["gor_sm3_sm3"] - narrow["cases"]["low"]["gor_sm3_sm3"]
    assert narrow_span < wide_span


def test_the_basis_refuses_to_publish_a_saturation_pressure():
    basis = build_analogue_fluid_basis(datum_tvdss_m=2700.0, analogues=ANALOGUES)
    text = repr(basis).lower()
    assert "saturation_pressure" not in text
    assert "equation of state" in basis["next_step"]


def test_every_assumption_says_what_would_retire_it():
    basis = build_analogue_fluid_basis(datum_tvdss_m=2700.0, analogues=ANALOGUES)
    for entry in basis["assumption_register"]:
        assert entry["retire_with"]
        assert entry["impact"]


def test_a_clamped_trend_adds_its_own_assumption():
    basis = build_analogue_fluid_basis(datum_tvdss_m=9000.0, analogues=ANALOGUES)
    ids = {a["id"] for a in basis["assumption_register"]}
    assert "F7" in ids


def test_a_measured_parameter_marks_its_assumption_retired():
    basis = build_analogue_fluid_basis(datum_tvdss_m=2700.0, analogues=ANALOGUES,
                                       measured_gor_sm3_sm3=200.0)
    entry = next(a for a in basis["assumption_register"] if a["id"] == "F1")
    assert entry["retired"] is True and entry["retired_by"]


# -- reconciliation --------------------------------------------------------
def test_reconciliation_separates_confirmed_from_overturned():
    basis = build_analogue_fluid_basis(datum_tvdss_m=3590.0, analogues=ANALOGUES,
                                       water_depth_m=381.0, sea_area="north_sea")
    result = reconcile_with_measured(
        basis, {"temperature_C": 129.0, "pressure_bara": 542.0})
    confirmed = {e["parameter"] for e in result["confirmed"]}
    overturned = {e["parameter"] for e in result["overturned"]}
    assert "temperature_C" in confirmed        # the gradient read was good
    assert "pressure_bara" in overturned       # hydrostatic was not
    assert result["verdict"] == "analogue_basis_refuted"


def test_an_overturned_parameter_says_to_recompute_downstream():
    basis = build_analogue_fluid_basis(datum_tvdss_m=3590.0, analogues=ANALOGUES)
    result = reconcile_with_measured(basis, {"pressure_bara": 542.0})
    assert "Recompute" in result["overturned"][0]["consequence"]


def test_parameters_with_no_measurement_are_reported_unchecked():
    basis = build_analogue_fluid_basis(datum_tvdss_m=2700.0, analogues=ANALOGUES)
    result = reconcile_with_measured(basis, {"gor_sm3_sm3": 200.0})
    assert "api_degrees" in result["unchecked"]


def test_a_fully_confirmed_basis_supports_the_analogue_method():
    basis = build_analogue_fluid_basis(datum_tvdss_m=2700.0, analogues=ANALOGUES)
    base_gor = basis["cases"]["base"]["gor_sm3_sm3"]
    result = reconcile_with_measured(basis, {"gor_sm3_sm3": base_gor})
    assert result["verdict"] == "analogue_basis_supported"


# -- the GOR definition trap ----------------------------------------------
def test_the_gor_spread_across_definitions_is_reported():
    record = reconcile_gor_definitions({
        "single_stage_flash": 290.1,
        "black_oil_Rs_at_bubble_point": 317.9,
        "separator_train": 259.5,
    }, quoted=290.0)
    assert record["spread"] == pytest.approx(58.4, abs=0.1)
    assert record["closest_definition"] == "single_stage_flash"
    assert "state which definition" in record["consequence"]


def test_each_reported_definition_is_explained():
    record = reconcile_gor_definitions({"separator_train": 259.5})
    assert "production test" in record["definitions"]["separator_train"]


def test_an_unrecognised_definition_is_listed_not_silently_dropped():
    record = reconcile_gor_definitions({"separator_train": 259.5, "made_up": 1.0})
    assert record["unrecognised"] == ["made_up"]


def test_no_recognised_definition_is_refused():
    with pytest.raises(ValueError):
        reconcile_gor_definitions({"made_up": 1.0})


def test_differential_liberation_is_declared_not_comparable():
    from reference_fluid import GOR_DEFINITIONS
    assert "not comparable" in GOR_DEFINITIONS["differential_liberation"]
