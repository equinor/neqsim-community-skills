import pytest

from step_out_screening import StepOutScreeningModel


def test_within_guidelines_is_ok() -> None:
    result = StepOutScreeningModel(max_step_out_km=50.0).evaluate(
        step_out_km=20.0,
        arrival_pressure_bara=110.0,
        min_arrival_pressure_bara=90.0,
        hydrate_margin_c=5.0,
    )

    assert result.step_out_warning == "ok"
    assert result.pressure_warning == "ok"
    assert result.hydrate_warning == "ok"
    assert result.overall_warning == "ok"


def test_step_out_high_drives_overall() -> None:
    result = StepOutScreeningModel(max_step_out_km=50.0).evaluate(
        step_out_km=55.0,
        arrival_pressure_bara=110.0,
        min_arrival_pressure_bara=90.0,
    )

    assert result.step_out_warning == "high"
    assert result.overall_warning == "high"


def test_negative_pressure_margin_is_high() -> None:
    result = StepOutScreeningModel().evaluate(
        step_out_km=10.0,
        arrival_pressure_bara=85.0,
        min_arrival_pressure_bara=90.0,
    )

    assert result.arrival_pressure_margin_bar == pytest.approx(-5.0)
    assert result.pressure_warning == "high"
    assert result.overall_warning == "high"


def test_small_pressure_margin_is_watch() -> None:
    result = StepOutScreeningModel().evaluate(
        step_out_km=10.0,
        arrival_pressure_bara=95.0,
        min_arrival_pressure_bara=90.0,
    )

    # 5 bar margin < 10% of 90 bar -> watch.
    assert result.pressure_warning == "watch"


def test_hydrate_not_assessed_when_omitted() -> None:
    result = StepOutScreeningModel().evaluate(
        step_out_km=10.0,
        arrival_pressure_bara=110.0,
        min_arrival_pressure_bara=90.0,
    )

    assert result.hydrate_warning == "not_assessed"
    assert result.overall_warning == "ok"


def test_negative_hydrate_margin_is_high() -> None:
    result = StepOutScreeningModel().evaluate(
        step_out_km=10.0,
        arrival_pressure_bara=110.0,
        min_arrival_pressure_bara=90.0,
        hydrate_margin_c=-1.0,
    )

    assert result.hydrate_warning == "high"
    assert result.overall_warning == "high"


def test_rejects_non_positive_step_out() -> None:
    with pytest.raises(ValueError, match="step_out_km must be positive"):
        StepOutScreeningModel().evaluate(
            step_out_km=0.0,
            arrival_pressure_bara=110.0,
            min_arrival_pressure_bara=90.0,
        )
