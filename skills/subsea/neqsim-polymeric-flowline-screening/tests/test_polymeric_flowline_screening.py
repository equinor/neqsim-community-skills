import math

import pytest
from polymeric_flowline_screening import (
    DesignBasis,
    OperatingCase,
    Permeant,
    PolymerGrade,
    PolymerPipe,
    allowable_hoop_pressure_bar,
    collapse_pressure_bar,
    interpolate,
    permeability_at,
    permeation_rate,
    screen,
    thermal_performance,
)

# Illustrative numbers for tests only; not material data.
GRADE = PolymerGrade(
    name="test-polymer",
    max_temperature_c=90.0,
    long_term_strength_mpa=((20.0, 12.0), (80.0, 6.0)),
    modulus_mpa=((20.0, 800.0), (80.0, 400.0)),
    conductivity_w_mk=0.4,
)


def pipe(**kwargs):
    defaults = {
        "outer_diameter_m": 0.2,
        "wall_m": 0.02,
        "length_m": 5000.0,
        "polymer": GRADE,
    }
    defaults.update(kwargs)
    return PolymerPipe(**defaults)


def rated_pipe(**kwargs):
    """Reinforced-pipe style: capacity from a vendor rating table."""
    return pipe(pressure_rating_bar=((20.0, 300.0), (80.0, 200.0)), **kwargs)


def case(**kwargs):
    defaults = {
        "internal_pressure_bar": 100.0,
        "temperature_c": 50.0,
        "ambient_c": 5.0,
        "mass_flow_kg_s": 5.0,
        "fluid_cp_j_kgk": 2500.0,
        "water_depth_m": 50.0,
    }
    defaults.update(kwargs)
    return OperatingCase(**defaults)


BASIS = DesignBasis(hoop_design_factor=0.5, collapse_safety_factor=2.0)


def test_interpolate_flags_extrapolation():
    assert interpolate(((0.0, 0.0), (10.0, 100.0)), 5.0) == (50.0, False)
    assert interpolate(((0.0, 0.0), (10.0, 100.0)), 20.0) == (100.0, True)


def test_hoop_pressure_matches_thin_wall_relation():
    p, extrapolated, source = allowable_hoop_pressure_bar(pipe(), 20.0, 0.5)
    expected = 2.0 * 12.0 * 0.5 * 0.02 / 0.18 * 10.0
    assert p == pytest.approx(expected)
    assert not extrapolated and "hoop" in source


def test_vendor_rating_table_overrides_formula():
    rated = pipe(pressure_rating_bar=((20.0, 250.0), (80.0, 150.0)))
    p, _, source = allowable_hoop_pressure_bar(rated, 50.0, 0.5)
    assert p == pytest.approx(200.0)
    assert "vendor" in source


def test_collapse_scales_with_cube_of_wall():
    thin = collapse_pressure_bar(pipe(wall_m=0.01), 20.0)[0]
    thick = collapse_pressure_bar(pipe(wall_m=0.02), 20.0)[0]
    # (t/Dm)^3 with Dm = D - t, so the exact ratio is not 8
    ratio = (0.02 / 0.18) ** 3 / (0.01 / 0.19) ** 3
    assert thick / thin == pytest.approx(ratio)


def test_permeation_scales_with_pressure_and_temperature():
    gas = Permeant("CO2", 10.0, 1e-14, 20.0, 30.0)
    low = permeation_rate(pipe(), gas, 20.0).rate_nm3_per_day_per_km
    high_p = permeation_rate(
        pipe(), Permeant("CO2", 20.0, 1e-14, 20.0, 30.0), 20.0
    ).rate_nm3_per_day_per_km
    assert high_p == pytest.approx(2.0 * low)
    assert permeability_at(gas, 60.0) > permeability_at(gas, 20.0)
    assert permeability_at(gas, 20.0) == pytest.approx(1e-14)


def test_thermal_polymer_retains_heat_better_than_steel():
    result = thermal_performance(pipe(), case())
    assert result.outlet_temperature_c > result.steel_outlet_temperature_c
    assert 5.0 < result.outlet_temperature_c < 50.0
    flow = 5.0 * 2500.0
    assert result.heat_loss_kw == pytest.approx(
        flow * (50.0 - result.outlet_temperature_c) / 1000.0
    )


def test_screen_passes_with_complete_data():
    result = screen(
        rated_pipe(),
        case(
            internal_pressure_bar=60.0,
            mass_flow_kg_s=40.0,
            installed_bend_radius_m=10.0,
            minimum_arrival_temperature_c=10.0,
            annulus_vent_capacity_nm3_d_km=1000.0,
        ),
        DesignBasis(0.5, 2.0, allowable_bending_strain=0.02),
        [Permeant("CO2", 5.0, 1e-15, 20.0, 30.0)],
    )
    assert result.overall == "pass"
    assert result.checks["bend_radius"].value == pytest.approx(0.2 / (2 * 0.02))
    assert result.data_gaps == ()


def test_overpressure_and_deep_water_fail():
    result = screen(
        pipe(wall_m=0.005),
        case(internal_pressure_bar=200.0, water_depth_m=2500.0),
        BASIS,
    )
    assert result.checks["hoop_pressure"].status == "fail"
    assert result.checks["collapse"].status == "fail"
    assert result.overall == "fail"


def test_missing_inputs_are_reported_as_data_gaps_not_passes():
    result = screen(rated_pipe(), case(), BASIS)
    assert result.overall == "incomplete"
    for name in ("bend_radius", "permeation", "arrival_temperature"):
        assert result.checks[name].status == "data_gap"
    assert any("permeation" in gap for gap in result.data_gaps)


def test_temperature_above_polymer_limit_fails():
    result = screen(rated_pipe(), case(temperature_c=95.0), BASIS)
    assert result.checks["temperature"].status == "fail"


def test_invalid_geometry_is_rejected():
    with pytest.raises(ValueError):
        pipe(wall_m=0.2)
    with pytest.raises(ValueError):
        DesignBasis(hoop_design_factor=1.5, collapse_safety_factor=2.0)
    assert math.isfinite(thermal_performance(pipe(), case()).resistance_k_m_per_w)
