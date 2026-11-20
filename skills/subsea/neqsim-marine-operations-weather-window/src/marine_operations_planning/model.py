"""Screening-level weather-window planning for offshore marine operations."""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Sequence
from dataclasses import dataclass

HOURS_PER_YEAR = 8766.0


def _percentile(sorted_values: Sequence[float], fraction: float) -> float:
    """Linear-interpolated percentile of an ascending list; fraction in [0, 1]."""
    if not sorted_values:
        return math.nan
    position = fraction * (len(sorted_values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    weight = position - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


@dataclass(frozen=True)
class MarineOperation:
    """One weather-restricted step of a marine campaign.

    ``forecast_factor`` multiplies the limits (alpha-factor style). It is supplied
    by the caller from the governing standard; this skill does not tabulate it.
    """

    name: str
    duration_h: float
    hs_limit_m: float
    wind_limit_ms: float | None = None
    contingency_fraction: float = 0.0
    forecast_factor: float = 1.0

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("operation name is required")
        if not self.duration_h > 0.0:
            raise ValueError(f"{self.name}: duration_h must be positive")
        if not self.hs_limit_m > 0.0:
            raise ValueError(f"{self.name}: hs_limit_m must be positive")
        if self.wind_limit_ms is not None and not self.wind_limit_ms > 0.0:
            raise ValueError(f"{self.name}: wind_limit_ms must be positive")
        if self.contingency_fraction < 0.0:
            raise ValueError(f"{self.name}: contingency_fraction cannot be negative")
        if not 0.0 < self.forecast_factor <= 1.0:
            raise ValueError(f"{self.name}: forecast_factor must be in (0, 1]")

    @property
    def planned_duration_h(self) -> float:
        """Duration including contingency, which must fit inside the window."""
        return self.duration_h * (1.0 + self.contingency_fraction)

    @property
    def operational_hs_limit_m(self) -> float:
        """Hs limit after the forecast factor."""
        return self.hs_limit_m * self.forecast_factor

    @property
    def operational_wind_limit_ms(self) -> float | None:
        """Wind limit after the forecast factor, or None when unrestricted."""
        if self.wind_limit_ms is None:
            return None
        return self.wind_limit_ms * self.forecast_factor


@dataclass(frozen=True)
class WeatherSeries:
    """Uniformly sampled hindcast: significant wave height and optional wind."""

    step_h: float
    hs_m: tuple[float, ...]
    wind_ms: tuple[float, ...] | None = None
    months: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        if not self.step_h > 0.0:
            raise ValueError("step_h must be positive")
        if len(self.hs_m) < 2:
            raise ValueError("hs_m needs at least two samples")
        for label, series in (("hs_m", self.hs_m), ("wind_ms", self.wind_ms)):
            if series is None:
                continue
            if len(series) != len(self.hs_m):
                raise ValueError(f"{label} length must equal hs_m length")
            if any((not math.isfinite(v)) or v < 0.0 for v in series):
                raise ValueError(f"{label} must be finite and non-negative")
        if self.months is not None:
            if len(self.months) != len(self.hs_m):
                raise ValueError("months length must equal hs_m length")
            if any(m < 1 or m > 12 for m in self.months):
                raise ValueError("months must be 1-12")

    @property
    def duration_years(self) -> float:
        """Length of the hindcast in years."""
        return len(self.hs_m) * self.step_h / HOURS_PER_YEAR


@dataclass(frozen=True)
class VesselOption:
    """Spread option: day rate, mobilisation and sea-keeping scaling of the limits."""

    name: str
    day_rate: float
    mobilisation_days: float = 0.0
    hs_limit_scale: float = 1.0
    wind_limit_scale: float = 1.0

    def __post_init__(self) -> None:
        if self.day_rate < 0.0 or self.mobilisation_days < 0.0:
            raise ValueError(f"{self.name}: cost inputs cannot be negative")
        if not self.hs_limit_scale > 0.0 or not self.wind_limit_scale > 0.0:
            raise ValueError(f"{self.name}: limit scales must be positive")


@dataclass(frozen=True)
class CampaignOutcome:
    """One simulated campaign from a given start sample."""

    start_index: int
    total_h: float
    waiting_h: float
    operation_start_h: tuple[float, ...]


@dataclass(frozen=True)
class CampaignStatistics:
    """Distribution of campaign duration over the hindcast start dates."""

    sample_count: int
    incomplete_count: int
    p10_h: float
    p50_h: float
    p90_h: float
    mean_h: float
    mean_waiting_h: float
    working_h: float
    by_month_p50_h: dict[int, float]
    by_month_p90_h: dict[int, float]
    warnings: tuple[str, ...]
    durations_h: tuple[float, ...]

    def probability_within(self, budget_h: float) -> float:
        """Fraction of started campaigns that finish inside ``budget_h``."""
        total = self.sample_count + self.incomplete_count
        if total == 0:
            return 0.0
        return sum(1 for d in self.durations_h if d <= budget_h) / total


@dataclass(frozen=True)
class VesselRanking:
    """Cost view of one vessel option; cost is in the units of ``day_rate``."""

    vessel: VesselOption
    statistics: CampaignStatistics
    p50_cost: float
    p90_cost: float
    mean_cost: float


class WeatherWindowPlanner:
    """Sequential campaign simulated over every start date in a hindcast.

    Each operation starts at the first sample from which weather stays inside its
    limits for the whole planned duration, otherwise the spread waits on weather.
    """

    def __init__(
        self, weather: WeatherSeries, operations: Sequence[MarineOperation]
    ) -> None:
        if not operations:
            raise ValueError("at least one operation is required")
        self.weather = weather
        self.operations = tuple(operations)
        self._steps: list[int] = []
        self._next: list[list[int]] = []
        for operation in self.operations:
            self._prepare(operation)

    def _prepare(self, operation: MarineOperation) -> None:
        weather = self.weather
        wind_limit = operation.operational_wind_limit_ms
        if wind_limit is not None and weather.wind_ms is None:
            raise ValueError(
                f"{operation.name} has a wind limit but the weather has no wind"
            )
        hs_limit = operation.operational_hs_limit_m
        count = len(weather.hs_m)
        steps = max(1, math.ceil(operation.planned_duration_h / weather.step_h - 1e-9))
        run = 0
        ok_run = [0] * count
        for index in range(count - 1, -1, -1):
            allowed = weather.hs_m[index] <= hs_limit and (
                wind_limit is None or weather.wind_ms[index] <= wind_limit
            )
            run = run + 1 if allowed else 0
            ok_run[index] = run
        following = [-1] * (count + 1)
        for index in range(count - 1, -1, -1):
            following[index] = index if ok_run[index] >= steps else following[index + 1]
        self._steps.append(steps)
        self._next.append(following)

    @property
    def working_h(self) -> float:
        """Planned working time with no waiting, on the hindcast time step."""
        return sum(steps * self.weather.step_h for steps in self._steps)

    def run(self, start_index: int) -> CampaignOutcome | None:
        """Simulate one campaign; None when the hindcast ends before it finishes."""
        step_h = self.weather.step_h
        cursor = start_index
        starts: list[float] = []
        for steps, following in zip(self._steps, self._next):
            begin = following[cursor]
            if begin < 0:
                return None
            starts.append((begin - start_index) * step_h)
            cursor = begin + steps
        total = (cursor - start_index) * step_h
        return CampaignOutcome(
            start_index, total, total - self.working_h, tuple(starts)
        )

    def statistics(self, start_step_h: float = 24.0) -> CampaignStatistics:
        """Duration distribution over start dates spaced ``start_step_h`` apart."""
        weather = self.weather
        stride = max(1, round(start_step_h / weather.step_h))
        outcomes: list[CampaignOutcome] = []
        incomplete = 0
        for start in range(0, len(weather.hs_m), stride):
            outcome = self.run(start)
            if outcome is None:
                incomplete += 1
            else:
                outcomes.append(outcome)
        durations = sorted(o.total_h for o in outcomes)
        by_month: dict[int, list[float]] = {}
        if weather.months is not None:
            for outcome in outcomes:
                month = weather.months[outcome.start_index]
                by_month.setdefault(month, []).append(outcome.total_h)
        warnings: list[str] = []
        if weather.duration_years < 5.0:
            warnings.append(
                "hindcast shorter than 5 years: percentiles are not climatologically robust"
            )
        total = len(outcomes) + incomplete
        if total and incomplete / total > 0.2:
            warnings.append(
                "over 20 % of start dates cannot finish inside the hindcast: "
                "durations are biased low, extend the hindcast"
            )
        if not outcomes:
            warnings.append("no start date completes the campaign")
        return CampaignStatistics(
            sample_count=len(outcomes),
            incomplete_count=incomplete,
            p10_h=_percentile(durations, 0.10),
            p50_h=_percentile(durations, 0.50),
            p90_h=_percentile(durations, 0.90),
            mean_h=sum(durations) / len(durations) if durations else math.nan,
            mean_waiting_h=(
                sum(o.waiting_h for o in outcomes) / len(outcomes)
                if outcomes
                else math.nan
            ),
            working_h=self.working_h,
            by_month_p50_h={
                m: _percentile(sorted(v), 0.50) for m, v in sorted(by_month.items())
            },
            by_month_p90_h={
                m: _percentile(sorted(v), 0.90) for m, v in sorted(by_month.items())
            },
            warnings=tuple(warnings),
            durations_h=tuple(durations),
        )


def rank_vessels(
    weather: WeatherSeries,
    operations: Sequence[MarineOperation],
    vessels: Sequence[VesselOption],
    start_step_h: float = 24.0,
) -> list[VesselRanking]:
    """Rank vessel options by P50 cost including waiting on weather.

    Cost is ``(mobilisation_days + duration_h / 24) * day_rate`` evaluated at the
    P50, P90 and mean campaign duration; the P90 column is the risk view.
    """
    if not vessels:
        raise ValueError("at least one vessel is required")
    rankings: list[VesselRanking] = []
    for vessel in vessels:
        scaled = [
            dataclasses.replace(
                op,
                hs_limit_m=op.hs_limit_m * vessel.hs_limit_scale,
                wind_limit_ms=(
                    None
                    if op.wind_limit_ms is None
                    else op.wind_limit_ms * vessel.wind_limit_scale
                ),
            )
            for op in operations
        ]
        stats = WeatherWindowPlanner(weather, scaled).statistics(start_step_h)

        def cost(hours: float, vessel: VesselOption = vessel) -> float:
            return (vessel.mobilisation_days + hours / 24.0) * vessel.day_rate

        rankings.append(
            VesselRanking(
                vessel, stats, cost(stats.p50_h), cost(stats.p90_h), cost(stats.mean_h)
            )
        )
    rankings.sort(key=lambda r: (math.isnan(r.p50_cost), r.p50_cost))
    return rankings
