import math

import pytest

from surf_cooldown_screening import SurfCooldownModel


def test_no_touch_time_matches_lumped_analytic_solution() -> None:
    model = SurfCooldownModel(hydrate_margin=3.0)
    result = model.evaluate(
        initial_temperature=65.0,
        seabed_temperature=4.0,
        hydrate_equilibrium_temperature=20.0,
        time_constant_hours=10.0,
    )

    # target = 23 C; t = -tau * ln((23-4)/(65-4))
    expected = -10.0 * math.log((23.0 - 4.0) / (65.0 - 4.0))
    assert result.no_touch_time_hours == pytest.approx(expected, abs=1e-2)
    assert result.target_temperature_c == pytest.approx(23.0, abs=1e-6)
    # ~11.66 h falls in the absolute marginal band (6-12 h) with no required time.
    assert result.verdict == SurfCooldownModel.VERDICT_MARGINAL
    assert result.assumptions


def test_required_no_touch_time_drives_critical_verdict() -> None:
    model = SurfCooldownModel(hydrate_margin=3.0, required_no_touch_time=100.0)
    result = model.evaluate(
        initial_temperature=65.0,
        seabed_temperature=4.0,
        hydrate_equilibrium_temperature=20.0,
        time_constant_hours=10.0,
    )

    assert result.verdict == SurfCooldownModel.VERDICT_CRITICAL


def test_no_hydrate_risk_when_hydrate_temperature_below_seabed() -> None:
    model = SurfCooldownModel()
    result = model.evaluate(
        initial_temperature=65.0,
        seabed_temperature=4.0,
        hydrate_equilibrium_temperature=2.0,
        time_constant_hours=10.0,
    )

    assert result.verdict == SurfCooldownModel.VERDICT_NO_HYDRATE_RISK
    assert result.no_touch_time_hours == float("inf")


def test_no_hydrate_risk_when_hydrate_temperature_missing() -> None:
    model = SurfCooldownModel()
    result = model.evaluate(
        initial_temperature=65.0,
        seabed_temperature=4.0,
        hydrate_equilibrium_temperature=None,
        time_constant_hours=10.0,
    )

    assert result.verdict == SurfCooldownModel.VERDICT_NO_HYDRATE_RISK


def test_already_in_hydrate_region_gives_zero_no_touch_time() -> None:
    model = SurfCooldownModel(hydrate_margin=3.0, required_no_touch_time=8.0)
    result = model.evaluate(
        initial_temperature=21.0,
        seabed_temperature=4.0,
        hydrate_equilibrium_temperature=20.0,
        time_constant_hours=10.0,
    )

    assert result.no_touch_time_hours == 0.0
    assert result.verdict == SurfCooldownModel.VERDICT_CRITICAL


def test_time_constant_from_lumped_mass_is_positive() -> None:
    tau = SurfCooldownModel.time_constant_from_lumped_mass(
        fluid_density=180.0,
        specific_heat=2600.0,
        internal_diameter=0.254,
        overall_u_value=2.5,
    )

    assert tau > 0.0


def test_rejects_non_positive_time_constant() -> None:
    with pytest.raises(ValueError, match="time_constant_hours"):
        SurfCooldownModel().evaluate(
            initial_temperature=65.0,
            seabed_temperature=4.0,
            hydrate_equilibrium_temperature=20.0,
            time_constant_hours=0.0,
        )
