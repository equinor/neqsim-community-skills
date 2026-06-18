import pytest

from safety_function_coverage_screening import SafetyFunctionCoverageModel


def test_coverage_model_ok_when_all_present() -> None:
    result = SafetyFunctionCoverageModel().evaluate(
        component_type="separator",
        provided_functions=["PSH", "PSL", "PSV", "LSH", "LSL"],
    )

    assert result.coverage_warning == "ok"
    assert result.missing_functions == ()
    assert result.coverage_ratio == pytest.approx(1.0)
    assert result.assumptions


def test_coverage_model_reports_gap() -> None:
    result = SafetyFunctionCoverageModel().evaluate(
        component_type="separator",
        provided_functions=["PSH", "PSV"],
    )

    assert result.coverage_warning == "gap"
    assert "LSH" in result.missing_functions
    assert result.coverage_ratio < 1.0


def test_coverage_model_normalizes_type_and_codes() -> None:
    result = SafetyFunctionCoverageModel().evaluate(
        component_type="Pressure-Vessel",
        provided_functions=["psh", " psl ", "PSV", "LSH"],
    )

    assert result.component_type == "pressure_vessel"
    assert result.coverage_warning == "ok"


def test_coverage_model_rejects_unknown_type() -> None:
    with pytest.raises(ValueError, match="component_type"):
        SafetyFunctionCoverageModel().evaluate(
            component_type="reactor",
            provided_functions=["PSH"],
        )
