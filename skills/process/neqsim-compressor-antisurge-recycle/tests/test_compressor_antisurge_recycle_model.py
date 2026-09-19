import pytest

from compressor_antisurge_recycle import AntiSurgeRecycleModel


def test_far_from_surge_returns_ok_with_minimal_recycle() -> None:
    result = AntiSurgeRecycleModel().plan(
        inlet_flow=7000.0,
        surge_flow=5000.0,
        chart_provided=True,
    )

    assert result.recycle_warning == "ok"
    assert result.in_surge is False
    assert result.surge_margin_fraction == pytest.approx(0.40, abs=1e-3)
    assert result.recommended_recycle_flow < 1.0
    assert result.assumptions


def test_in_surge_recommends_recycle_step() -> None:
    result = AntiSurgeRecycleModel().plan(
        inlet_flow=4200.0,
        surge_flow=5000.0,
        chart_provided=True,
        current_recycle=0.0,
    )

    assert result.in_surge is True
    assert result.recycle_warning == "surge"
    # raw step 0.5*(5000-4200)=400, capped at 0.25*5000=1250 -> 400
    assert result.recommended_recycle_flow == pytest.approx(400.0, abs=1e-3)
    assert result.total_suction_flow == pytest.approx(4600.0, abs=1e-3)


def test_recycle_step_is_capped_per_iteration() -> None:
    result = AntiSurgeRecycleModel().plan(
        inlet_flow=1000.0,
        surge_flow=5000.0,
        chart_provided=True,
        current_recycle=0.0,
    )

    # raw step 0.5*(5000-1000)=2000, capped at 0.25*5000=1250
    assert result.recommended_recycle_flow == pytest.approx(1250.0, abs=1e-3)


def test_within_margin_band_warns_recycle() -> None:
    result = AntiSurgeRecycleModel().plan(
        inlet_flow=5500.0,
        surge_flow=5000.0,
        chart_provided=True,
    )

    # Above surge flow but inside the far-from-surge band (<= 1.2 * surge).
    assert result.in_surge is False
    assert result.recycle_warning == "recycle"
    assert result.surge_margin_fraction == pytest.approx(0.10, abs=1e-3)


def test_missing_chart_requires_generation() -> None:
    result = AntiSurgeRecycleModel().plan(
        inlet_flow=4200.0,
        surge_flow=5000.0,
        chart_provided=False,
    )

    assert result.needs_chart_generation is True


def test_rejects_non_positive_flow() -> None:
    with pytest.raises(ValueError, match="inlet_flow"):
        AntiSurgeRecycleModel().plan(inlet_flow=0.0, surge_flow=5000.0)


def test_rejects_negative_recycle() -> None:
    with pytest.raises(ValueError, match="current_recycle"):
        AntiSurgeRecycleModel().plan(
            inlet_flow=4200.0,
            surge_flow=5000.0,
            current_recycle=-1.0,
        )
