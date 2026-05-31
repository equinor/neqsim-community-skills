import pytest

from fluid_quality_check import FluidQualityChecker


def test_checker_accepts_clean_public_composition() -> None:
    result = FluidQualityChecker(required_components=("methane", "ethane")).check(
        {"methane": 0.9, "ethane": 0.1}
    )

    assert result.is_usable is True
    assert result.total_within_tolerance is True
    assert result.warnings == ()


def test_checker_flags_water_co2_and_h2s() -> None:
    result = FluidQualityChecker(required_components=("methane",)).check(
        {"methane": 0.9, "CO2": 0.05, "H2S": 0.01, "water": 0.04}
    )

    assert result.is_usable is True
    assert result.flagged_components == {"water": 0.04, "CO2": 0.05, "H2S": 0.01}
    assert any("CO2 present" in warning for warning in result.warnings)


def test_checker_reports_negative_and_missing_components() -> None:
    result = FluidQualityChecker(required_components=("methane", "ethane")).check(
        {"methane": 1.02, "propane": -0.02}
    )

    assert result.is_usable is False
    assert result.negative_components == ("propane",)
    assert result.missing_components == ("ethane",)


def test_checker_rejects_empty_composition() -> None:
    with pytest.raises(ValueError, match="composition"):
        FluidQualityChecker().check({})