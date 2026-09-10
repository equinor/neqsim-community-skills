"""Tests for the fire-water and deluge coverage screening model."""

from __future__ import annotations

import math

import pytest

from firewater_deluge_design import FireWaterCoverageModel


@pytest.fixture()
def model() -> FireWaterCoverageModel:
    return FireWaterCoverageModel()


def test_area_demand_follows_application_rate(model: FireWaterCoverageModel) -> None:
    r = model.demand(protected_area_m2=510.0, area_rate_lpm_per_m2=10.0, duration_min=30.0)
    assert r.area_demand_lpm == pytest.approx(5100.0)
    assert r.total_demand_m3_per_h == pytest.approx(306.0)
    assert r.water_volume_m3 == pytest.approx(153.0)


def test_wellhead_rate_is_double_the_process_area_rate() -> None:
    assert (
        FireWaterCoverageModel.NORSOK_WELLHEAD_LPM_M2
        == 2.0 * FireWaterCoverageModel.NORSOK_PROCESS_AREA_LPM_M2
    )


def test_horizontal_vessel_surface_is_shell_plus_ends() -> None:
    s = FireWaterCoverageModel.horizontal_vessel_surface_m2(0.72, 6.606)
    expected = math.pi * 0.72 * 6.606 + 2.0 * math.pi * 0.72**2 / 4.0
    assert s == pytest.approx(expected)


def test_selective_protection_is_a_small_fraction_of_blanket_coverage(
    model: FireWaterCoverageModel,
) -> None:
    surface = FireWaterCoverageModel.horizontal_vessel_surface_m2(0.72, 6.606)
    r = model.demand(
        protected_area_m2=510.0,
        area_rate_lpm_per_m2=10.0,
        objects=(("HA-13-0001", surface, 10.0),),
    )
    assert r.object_to_area_ratio < 0.10


def test_foam_concentrate_scales_with_water_volume(model: FireWaterCoverageModel) -> None:
    r = model.demand(
        protected_area_m2=100.0,
        area_rate_lpm_per_m2=10.0,
        duration_min=30.0,
        foam_concentrate_percent=3.0,
    )
    assert r.water_volume_m3 == pytest.approx(30.0)
    assert r.foam_concentrate_m3 == pytest.approx(0.9)


def test_simultaneous_factor_multiplies_demand(model: FireWaterCoverageModel) -> None:
    r = model.demand(
        protected_area_m2=200.0, area_rate_lpm_per_m2=10.0, simultaneous_area_factor=2.0
    )
    assert r.total_demand_lpm == pytest.approx(4000.0)


def test_nozzle_count_is_the_larger_of_flow_and_coverage(model: FireWaterCoverageModel) -> None:
    r = model.deluge_layout(
        protected_area_m2=510.0,
        required_density_lpm_per_m2=10.0,
        nozzle_k_lpm_per_sqrt_bar=42.9,
        nozzle_min_pressure_barg=3.5,
        max_spacing_m=3.0,
        operating_pressure_barg=5.0,
    )
    assert r.flow_per_nozzle_lpm == pytest.approx(42.9 * math.sqrt(5.0))
    assert r.nozzle_count == max(r.nozzle_count_from_flow, r.nozzle_count_from_coverage)
    assert r.governing_criterion == "coverage"
    assert r.density_met
    assert r.pressure_adequate
    assert 2.0 < r.grid_spacing_m < 3.1


def test_flow_governs_for_a_low_capacity_nozzle(model: FireWaterCoverageModel) -> None:
    r = model.deluge_layout(
        protected_area_m2=510.0,
        required_density_lpm_per_m2=10.0,
        nozzle_k_lpm_per_sqrt_bar=18.0,
        nozzle_min_pressure_barg=1.4,
        max_spacing_m=3.0,
        operating_pressure_barg=2.0,
    )
    assert r.governing_criterion == "flow"
    assert r.nozzle_count_from_flow > r.nozzle_count_from_coverage


def test_pressure_below_the_nozzle_minimum_is_flagged(model: FireWaterCoverageModel) -> None:
    r = model.deluge_layout(
        protected_area_m2=100.0,
        required_density_lpm_per_m2=10.0,
        nozzle_k_lpm_per_sqrt_bar=42.9,
        nozzle_min_pressure_barg=3.5,
        max_spacing_m=3.0,
        operating_pressure_barg=2.0,
    )
    assert not r.pressure_adequate


def test_monitors_fail_the_density_over_a_large_deck(model: FireWaterCoverageModel) -> None:
    r = model.monitor_screening(
        target_area_m2=510.0,
        required_density_lpm_per_m2=10.0,
        monitor_count=2,
        monitor_flow_lpm=2400.0,
    )
    assert r.total_flow_lpm == pytest.approx(4800.0)
    assert not r.meets_density_still_air
    assert r.verdict == "not_suitable_density"


def test_wind_drift_turns_a_passing_monitor_concept_marginal(
    model: FireWaterCoverageModel,
) -> None:
    r = model.monitor_screening(
        target_area_m2=510.0,
        required_density_lpm_per_m2=10.0,
        monitor_count=4,
        monitor_flow_lpm=4000.0,
        wind_speed_m_s=15.0,
        fall_height_m=12.0,
        characteristic_dimension_m=25.5,
    )
    assert r.meets_density_still_air
    assert not r.meets_density_in_wind
    assert r.drift_displacement_m == pytest.approx(12.0 * 15.0 / 8.0)
    assert r.verdict == "marginal_wind_limited"


def test_shadowing_disqualifies_a_monitor_even_when_the_density_passes(
    model: FireWaterCoverageModel,
) -> None:
    r = model.monitor_screening(
        target_area_m2=100.0,
        required_density_lpm_per_m2=10.0,
        monitor_count=4,
        monitor_flow_lpm=4000.0,
        line_of_sight_obstructed=True,
    )
    assert r.meets_density_still_air
    assert r.verdict == "not_suitable_shadowing"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"protected_area_m2": -1.0, "area_rate_lpm_per_m2": 10.0},
        {"protected_area_m2": 100.0, "area_rate_lpm_per_m2": 10.0, "duration_min": 0.0},
        {"protected_area_m2": 100.0, "area_rate_lpm_per_m2": 10.0, "simultaneous_area_factor": 0.5},
    ],
)
def test_invalid_demand_inputs_raise(model: FireWaterCoverageModel, kwargs: dict) -> None:
    with pytest.raises(ValueError):
        model.demand(**kwargs)


def test_every_result_carries_assumptions(model: FireWaterCoverageModel) -> None:
    d = model.demand(protected_area_m2=100.0, area_rate_lpm_per_m2=10.0)
    layout = model.deluge_layout(
        protected_area_m2=100.0,
        required_density_lpm_per_m2=10.0,
        nozzle_k_lpm_per_sqrt_bar=42.9,
        nozzle_min_pressure_barg=3.5,
        max_spacing_m=3.0,
        operating_pressure_barg=5.0,
    )
    mon = model.monitor_screening(
        target_area_m2=100.0,
        required_density_lpm_per_m2=10.0,
        monitor_count=1,
        monitor_flow_lpm=2400.0,
    )
    for result in (d, layout, mon):
        assert result.assumptions
