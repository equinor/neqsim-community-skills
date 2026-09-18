import pytest

from psv_orifice_screening import PsvOrificeModel


def test_psv_orifice_model_selects_standard_orifice() -> None:
    result = PsvOrificeModel().evaluate(
        relief_rate=50000.0,
        relieving_pressure=20.0,
        temperature=323.15,
        molecular_weight=19.0,
    )

    assert result.selected_orifice != "none"
    assert result.selected_orifice_area_mm2 >= result.required_area_mm2
    assert result.psv_warning in {"ok", "watch"}
    assert result.assumptions


def test_psv_orifice_model_oversize_needed_for_huge_rate() -> None:
    result = PsvOrificeModel().evaluate(
        relief_rate=5_000_000.0,
        relieving_pressure=5.0,
        temperature=400.0,
        molecular_weight=16.0,
    )

    assert result.selected_orifice == "none"
    assert result.psv_warning == "oversize-needed"


def test_psv_orifice_model_rejects_low_k() -> None:
    with pytest.raises(ValueError, match="specific_heat_ratio"):
        PsvOrificeModel().evaluate(
            relief_rate=50000.0,
            relieving_pressure=20.0,
            temperature=323.15,
            molecular_weight=19.0,
            specific_heat_ratio=1.0,
        )
