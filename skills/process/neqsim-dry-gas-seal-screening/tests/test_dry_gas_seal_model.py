import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dry_gas_seal_screening import DryGasSealModel


def test_ok_condensation_margin():
    model = DryGasSealModel()
    result = model.evaluate(
        seal_leakage_rate_nl_per_min=280.0,
        seal_cavity_temperature_c=44.0,
        hydrocarbon_dew_point_c=30.0,
        seal_count=2,
        supply_margin=1.25,
    )
    assert result.condensation_warning == "ok"
    assert result.total_seal_gas_supply_nl_per_min == pytest.approx(700.0)
    assert result.condensation_margin_c == pytest.approx(14.0)


def test_watch_condensation_margin():
    model = DryGasSealModel()
    result = model.evaluate(
        seal_leakage_rate_nl_per_min=200.0,
        seal_cavity_temperature_c=44.0,
        hydrocarbon_dew_point_c=38.0,
    )
    assert result.condensation_warning == "watch"


def test_high_condensation_margin():
    model = DryGasSealModel()
    result = model.evaluate(
        seal_leakage_rate_nl_per_min=200.0,
        seal_cavity_temperature_c=44.0,
        hydrocarbon_dew_point_c=43.0,
    )
    assert result.condensation_warning == "high"


def test_separation_gas_scales_with_seal_count():
    model = DryGasSealModel()
    result = model.evaluate(
        seal_leakage_rate_nl_per_min=200.0,
        seal_cavity_temperature_c=44.0,
        hydrocarbon_dew_point_c=30.0,
        seal_count=3,
        separation_gas_rate_nl_per_min=100.0,
    )
    assert result.separation_gas_supply_nl_per_min == pytest.approx(300.0)


def test_invalid_leakage_rate():
    model = DryGasSealModel()
    with pytest.raises(ValueError, match="seal_leakage_rate_nl_per_min"):
        model.evaluate(
            seal_leakage_rate_nl_per_min=-1.0,
            seal_cavity_temperature_c=44.0,
            hydrocarbon_dew_point_c=30.0,
        )


def test_invalid_threshold_ordering():
    with pytest.raises(ValueError, match="high_margin_c"):
        DryGasSealModel(watch_margin_c=3.0, high_margin_c=8.0)
