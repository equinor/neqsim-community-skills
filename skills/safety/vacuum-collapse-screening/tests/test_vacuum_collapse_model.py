import pytest

from vacuum_collapse_screening import VacuumCollapseModel


def test_vacuum_collapse_model_returns_ok_for_dry_gas_mild_cooldown() -> None:
    result = VacuumCollapseModel().evaluate(
        initial_pressure=10.0,
        initial_temperature=50.0,
        cold_end_temperature=0.0,
        condensable_fraction=0.0,
        external_pressure_rating=0.0,
    )

    assert result.verdict == "no_vacuum"
    assert result.vacuum_present is False
    assert result.exceeds_rating is False
    assert result.collapse_warning == "ok"
    assert result.vacuum_depth_bar == 0.0
    assert result.estimated_final_pressure_bara > 1.01325
    assert result.assumptions


def test_vacuum_collapse_model_flags_steam_condensation_vacuum() -> None:
    result = VacuumCollapseModel().evaluate(
        initial_pressure=1.8,
        initial_temperature=120.0,
        cold_end_temperature=20.0,
        condensable_fraction=0.85,
        external_pressure_rating=0.5,
    )

    assert result.verdict == "vacuum_exceeds_rating"
    assert result.vacuum_present is True
    assert result.exceeds_rating is True
    assert result.collapse_warning == "high"
    assert result.vacuum_depth_bar > 0.5
    assert result.margin_to_rating_bar < 0.0


def test_vacuum_collapse_model_vacuum_within_rating() -> None:
    result = VacuumCollapseModel().evaluate(
        initial_pressure=1.05,
        initial_temperature=80.0,
        cold_end_temperature=20.0,
        condensable_fraction=0.0,
        external_pressure_rating=0.4,
    )

    assert result.verdict == "vacuum_within_rating"
    assert result.vacuum_present is True
    assert result.exceeds_rating is False
    assert result.margin_to_rating_bar > 0.0


def test_vacuum_collapse_model_rejects_non_cooling_case() -> None:
    with pytest.raises(ValueError, match="cold_end_temperature"):
        VacuumCollapseModel().evaluate(
            initial_pressure=1.8,
            initial_temperature=20.0,
            cold_end_temperature=60.0,
        )


def test_vacuum_collapse_model_rejects_invalid_condensable_fraction() -> None:
    with pytest.raises(ValueError, match="condensable_fraction"):
        VacuumCollapseModel().evaluate(
            initial_pressure=1.8,
            initial_temperature=120.0,
            cold_end_temperature=20.0,
            condensable_fraction=1.5,
        )
