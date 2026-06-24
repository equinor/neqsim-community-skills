import pytest

from reservoir_depletion_screening import ReservoirDepletionModel


def _base(**overrides):
    kwargs = dict(
        fluid_type="gas",
        initial_pressure_bara=300.0,
        abandonment_pressure_bara=80.0,
        recoverable_volume_sm3=20.0e9,
        offtake_rate_sm3_per_day=8.0e6,
        years=15,
    )
    kwargs.update(overrides)
    return ReservoirDepletionModel().evaluate(**kwargs)


def test_pressure_declines_monotonically() -> None:
    result = _base()
    pressures = [step.pressure_bara for step in result.steps]
    assert pressures == sorted(pressures, reverse=True)
    assert result.final_pressure_bara < result.initial_pressure_bara


def test_recovery_factor_increases_and_is_bounded() -> None:
    result = _base()
    rfs = [step.recovery_factor for step in result.steps]
    assert rfs == sorted(rfs)
    assert all(0.0 <= rf <= 1.0 for rf in rfs)


def test_depletion_flags_high_when_abandoned() -> None:
    # High offtake depletes the reservoir within the horizon.
    result = _base(offtake_rate_sm3_per_day=6.0e6, years=20)
    assert result.years_to_abandonment is not None
    assert result.depletion_warning == "high"
    last = result.steps[-1]
    assert last.depleted is True
    assert last.hydrocarbon_rate_sm3_per_day == 0.0


def test_water_cut_rises_linearly() -> None:
    result = _base(initial_water_cut_fraction=0.1, water_cut_rise_per_year=0.05)
    first = result.steps[0]
    later = result.steps[5]
    assert later.water_cut_fraction > first.water_cut_fraction
    assert all(0.0 <= s.water_cut_fraction <= 1.0 for s in result.steps)


def test_water_rate_zero_when_no_water_cut() -> None:
    result = _base(initial_water_cut_fraction=0.0, water_cut_rise_per_year=0.0)
    assert all(s.water_rate_sm3_per_day == 0.0 for s in result.steps)


def test_abandonment_must_be_below_initial() -> None:
    with pytest.raises(ValueError):
        _base(abandonment_pressure_bara=300.0)


def test_invalid_fluid_type_raises() -> None:
    with pytest.raises(ValueError):
        _base(fluid_type="condensate")


def test_negative_offtake_raises() -> None:
    with pytest.raises(ValueError):
        _base(offtake_rate_sm3_per_day=-1.0)


def test_oil_fluid_type_runs() -> None:
    result = _base(fluid_type="oil", recoverable_volume_sm3=5.0e8,
                   offtake_rate_sm3_per_day=2.0e4)
    assert result.fluid_type == "oil"
    assert len(result.steps) == 15
