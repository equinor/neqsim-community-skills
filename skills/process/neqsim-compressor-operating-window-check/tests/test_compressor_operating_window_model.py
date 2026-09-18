import pytest

from compressor_operating_window import CompressorOperatingWindowModel


def test_operating_window_returns_ok_inside_window() -> None:
    result = CompressorOperatingWindowModel().evaluate(
        operating_flow=1300.0,
        surge_flow=1000.0,
        stonewall_flow=2000.0,
    )

    assert result.operating_window_warning == "ok"
    assert result.surge_margin_fraction == pytest.approx(0.30, abs=1e-3)
    assert result.stonewall_margin_fraction == pytest.approx(0.35, abs=1e-3)
    assert result.limiting_margin_fraction == pytest.approx(0.30, abs=1e-3)
    assert result.assumptions


def test_operating_window_flags_watch_near_surge() -> None:
    result = CompressorOperatingWindowModel().evaluate(
        operating_flow=1050.0,
        surge_flow=1000.0,
        stonewall_flow=2000.0,
    )

    assert result.operating_window_warning == "watch"
    assert result.surge_margin_fraction == pytest.approx(0.05, abs=1e-3)


def test_operating_window_flags_high_below_surge() -> None:
    result = CompressorOperatingWindowModel().evaluate(
        operating_flow=900.0,
        surge_flow=1000.0,
        stonewall_flow=2000.0,
    )

    assert result.operating_window_warning == "high"
    assert result.surge_margin_fraction < 0.0


def test_operating_window_rejects_inverted_limits() -> None:
    with pytest.raises(ValueError, match="stonewall_flow"):
        CompressorOperatingWindowModel().evaluate(
            operating_flow=1300.0,
            surge_flow=2000.0,
            stonewall_flow=1500.0,
        )
