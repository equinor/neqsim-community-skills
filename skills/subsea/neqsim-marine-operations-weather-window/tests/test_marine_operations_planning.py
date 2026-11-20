import pytest
from marine_operations_planning import (
    MarineOperation,
    VesselOption,
    WeatherSeries,
    WeatherWindowPlanner,
    rank_vessels,
)


def calm_series(count=400, step_h=1.0, **kwargs):
    return WeatherSeries(step_h=step_h, hs_m=tuple([1.0] * count), **kwargs)


def test_calm_weather_gives_working_time_only():
    operations = [
        MarineOperation("lay", 10.0, 2.5),
        MarineOperation("connect", 6.0, 2.0, contingency_fraction=0.5),
    ]
    stats = WeatherWindowPlanner(calm_series(), operations).statistics(start_step_h=24)

    assert stats.working_h == pytest.approx(19.0)
    assert stats.p50_h == pytest.approx(19.0)
    assert stats.mean_waiting_h == pytest.approx(0.0)


def test_operation_waits_for_window_long_enough():
    hs = [1.0] * 5 + [4.0] * 3 + [1.0] * 4 + [1.0] * 200
    planner = WeatherWindowPlanner(
        WeatherSeries(1.0, tuple(hs)), [MarineOperation("lift", 6.0, 2.0)]
    )
    outcome = planner.run(0)

    # 5 h of calm is too short for a 6 h operation, so it waits until sample 8
    assert outcome.operation_start_h == (8.0,)
    assert outcome.total_h == pytest.approx(14.0)
    assert outcome.waiting_h == pytest.approx(8.0)


def test_forecast_factor_tightens_limit():
    hs = tuple([1.8] * 100)
    loose = WeatherWindowPlanner(
        WeatherSeries(1.0, hs), [MarineOperation("a", 4.0, 2.0)]
    ).statistics()
    tight = WeatherWindowPlanner(
        WeatherSeries(1.0, hs), [MarineOperation("a", 4.0, 2.0, forecast_factor=0.8)]
    ).statistics()

    assert loose.sample_count > 0
    assert tight.sample_count == 0
    assert any("no start date" in w for w in tight.warnings)


def test_wind_limit_requires_wind_series():
    with pytest.raises(ValueError, match="no wind"):
        WeatherWindowPlanner(
            calm_series(), [MarineOperation("a", 4.0, 2.0, wind_limit_ms=12.0)]
        )


def test_wind_limit_blocks_start():
    wind = tuple([20.0] * 10 + [5.0] * 100)
    planner = WeatherWindowPlanner(
        calm_series(110, wind_ms=wind),
        [MarineOperation("a", 4.0, 2.0, wind_limit_ms=12.0)],
    )

    assert planner.run(0).operation_start_h == (10.0,)


def test_incomplete_starts_near_end_are_counted_and_flagged():
    stats = WeatherWindowPlanner(
        calm_series(30), [MarineOperation("a", 20.0, 2.0)]
    ).statistics(start_step_h=1)

    assert stats.incomplete_count > 0
    assert any("hindcast" in w for w in stats.warnings)
    assert stats.probability_within(20.0) < 1.0


def test_monthly_breakdown_uses_start_month():
    count = 2000
    months = tuple(1 if i < 1000 else 7 for i in range(count))
    hs = tuple(3.0 if i < 1000 else 1.0 for i in range(count))
    stats = WeatherWindowPlanner(
        WeatherSeries(1.0, hs, months=months), [MarineOperation("a", 5.0, 2.0)]
    ).statistics(start_step_h=6)

    assert stats.by_month_p50_h[7] == pytest.approx(5.0)
    assert stats.by_month_p50_h[1] > stats.by_month_p50_h[7]


def test_better_seakeeping_vessel_wins_when_weather_marginal():
    hs = tuple(2.4 if (i // 12) % 2 == 0 else 1.0 for i in range(3000))
    operations = [MarineOperation("install", 10.0, 2.0)]
    vessels = [
        VesselOption("small", day_rate=1.0),
        VesselOption("large", day_rate=1.2, hs_limit_scale=1.5),
    ]
    ranking = rank_vessels(WeatherSeries(1.0, hs), operations, vessels)

    assert ranking[0].vessel.name == "large"
    assert ranking[0].statistics.mean_waiting_h < ranking[1].statistics.mean_waiting_h
    assert ranking[1].p90_cost >= ranking[1].p50_cost


@pytest.mark.parametrize(
    "kwargs",
    [
        {"duration_h": 0.0, "hs_limit_m": 2.0},
        {"duration_h": 1.0, "hs_limit_m": -1.0},
        {"duration_h": 1.0, "hs_limit_m": 2.0, "forecast_factor": 1.2},
    ],
)
def test_invalid_operation_is_rejected(kwargs):
    with pytest.raises(ValueError):
        MarineOperation("bad", **kwargs)


def test_mismatched_series_lengths_are_rejected():
    with pytest.raises(ValueError):
        WeatherSeries(1.0, (1.0, 1.0, 1.0), wind_ms=(5.0, 5.0))
