"""Control-authority (valve saturation) screening from a controller output history.

Public, educational detection of the loss-of-control-authority failure mode: a
final control element driven onto its stop, after which the loop can no longer
reject a disturbance and ordinary unchanged variability passes straight through
to the controlled variable.

The signature is deliberately counter-intuitive and easy to misdiagnose: the
process gets worse while the disturbance is unchanged, so the investigation goes
looking for a new external cause that does not exist.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite, nan, sqrt
from typing import Sequence


@dataclass(frozen=True)
class RegimeStatistics:
    """Behaviour of the controlled variable within one controller regime."""

    sample_count: int
    fraction_of_period: float
    controlled_variable_mean: float
    controlled_variable_std: float
    disturbance_gain: float
    disturbance_r_squared: float


@dataclass(frozen=True)
class ControlAuthorityResult:
    sample_count: int
    saturation_fraction: float
    upper_saturation_fraction: float
    lower_saturation_fraction: float
    modulating_fraction: float
    saturated: RegimeStatistics
    modulating: RegimeStatistics
    variance_ratio: float
    gain_ratio: float
    off_set_point_fraction: float
    max_rate_per_hour: float
    margin_to_limit: float
    time_to_limit_h: float
    authority_status: str
    warnings: tuple[str, ...]
    assumptions: tuple[str, ...]
    neqsim_available: bool


@dataclass(frozen=True)
class PeriodObservation:
    """One comparable period, e.g. the same summer month in successive years."""

    label: str
    saturation_fraction: float
    disturbance_std: float | None = None


@dataclass(frozen=True)
class AuthorityTrendResult:
    periods: tuple[PeriodObservation, ...]
    saturation_change: float
    saturation_relative_change: float
    disturbance_change: float
    disturbance_relative_change: float
    verdict: str
    narrative: str
    warnings: tuple[str, ...]


class ControlAuthorityModel:
    """Educational screening for loss of control authority in a regulatory loop.

    Needs only two tags that are almost always historised, a controller output
    and its process value, so it is cheap enough to run as a default check in
    any operational or root-cause workflow.
    """

    def __init__(
        self,
        *,
        marginal_saturation_fraction: float = 0.25,
        lost_saturation_fraction: float = 0.50,
        saturation_trend_threshold: float = 0.15,
        disturbance_trend_threshold: float = 0.25,
    ) -> None:
        if not 0.0 < marginal_saturation_fraction < lost_saturation_fraction < 1.0:
            raise ValueError(
                "require 0 < marginal_saturation_fraction < "
                "lost_saturation_fraction < 1"
            )
        self._require_positive("saturation_trend_threshold", saturation_trend_threshold)
        self._require_positive("disturbance_trend_threshold", disturbance_trend_threshold)
        self.marginal_saturation_fraction = marginal_saturation_fraction
        self.lost_saturation_fraction = lost_saturation_fraction
        self.saturation_trend_threshold = saturation_trend_threshold
        self.disturbance_trend_threshold = disturbance_trend_threshold

    # ------------------------------------------------------------------
    # Single-period screening
    # ------------------------------------------------------------------
    def evaluate(
        self,
        *,
        controller_output: Sequence[float],
        controlled_variable: Sequence[float],
        output_min: float = 0.0,
        output_max: float = 100.0,
        saturation_band: float = 1.0,
        sample_interval_h: float = 1.0,
        set_point: float | None = None,
        set_point_tolerance: float = 0.0,
        disturbance: Sequence[float] | None = None,
        limit_value: float | None = None,
    ) -> ControlAuthorityResult:
        """Screen one period of controller output against its controlled variable."""
        output = self._as_series("controller_output", controller_output, minimum=2)
        process_value = self._as_series(
            "controlled_variable", controlled_variable, minimum=2
        )
        if len(output) != len(process_value):
            raise ValueError(
                "controller_output and controlled_variable must have equal length"
            )
        disturbance_series: list[float] | None = None
        if disturbance is not None:
            disturbance_series = self._as_series("disturbance", disturbance, minimum=2)
            if len(disturbance_series) != len(output):
                raise ValueError("disturbance must have the same length as controller_output")
        if output_max <= output_min:
            raise ValueError("output_max must exceed output_min")
        self._require_non_negative("saturation_band", saturation_band)
        if saturation_band >= 0.5 * (output_max - output_min):
            raise ValueError("saturation_band must be under half the output span")
        self._require_positive("sample_interval_h", sample_interval_h)
        self._require_non_negative("set_point_tolerance", set_point_tolerance)

        warnings: list[str] = []
        count = len(output)
        upper = output_max - saturation_band
        lower = output_min + saturation_band

        upper_hits = [i for i, value in enumerate(output) if value >= upper]
        lower_hits = [i for i, value in enumerate(output) if value <= lower]
        saturated_index = sorted(set(upper_hits) | set(lower_hits))
        modulating_index = [i for i in range(count) if i not in set(saturated_index)]

        # Bottoming out costs the same authority as topping out, so both stops count.
        upper_fraction = len(upper_hits) / count
        lower_fraction = len(lower_hits) / count
        saturation_fraction = len(saturated_index) / count
        modulating_fraction = len(modulating_index) / count

        saturated = self._regime_statistics(
            saturated_index, count, process_value, disturbance_series
        )
        modulating = self._regime_statistics(
            modulating_index, count, process_value, disturbance_series
        )

        variance_ratio = self._ratio(
            saturated.controlled_variable_std**2, modulating.controlled_variable_std**2
        )
        gain_ratio = self._ratio(
            abs(saturated.disturbance_gain), abs(modulating.disturbance_gain)
        )

        off_set_point_fraction = nan
        if set_point is not None:
            self._require_finite("set_point", set_point)
            outside = sum(
                1 for value in process_value if abs(value - set_point) > set_point_tolerance
            )
            off_set_point_fraction = outside / count

        rates = [
            abs(process_value[i + 1] - process_value[i]) / sample_interval_h
            for i in range(count - 1)
        ]
        max_rate_per_hour = max(rates) if rates else 0.0

        margin_to_limit = nan
        time_to_limit_h = nan
        if limit_value is not None:
            self._require_finite("limit_value", limit_value)
            margin_to_limit = abs(limit_value - process_value[-1])
            if max_rate_per_hour > 0.0:
                time_to_limit_h = margin_to_limit / max_rate_per_hour
            else:
                warnings.append(
                    "the controlled variable does not move over the period; no "
                    "time-to-limit can be projected"
                )

        status = self._authority_status(saturation_fraction)
        if status != "authority-retained":
            warnings.append(
                "controller output is on a stop for {:.0%} of the period; the loop "
                "cannot reject a disturbance while saturated".format(saturation_fraction)
            )
        if isfinite(variance_ratio) and variance_ratio > 1.0 and saturated.sample_count >= 2:
            warnings.append(
                "controlled-variable variance is {:.1f}x higher while saturated; "
                "disturbance rejection has been lost, not gained".format(variance_ratio)
            )
        if isfinite(saturated.disturbance_gain) and abs(saturated.disturbance_gain) >= 0.8:
            warnings.append(
                "disturbance-to-process gain is {:.2f} while saturated, at or above "
                "unity scale; the disturbance is passing through undamped".format(
                    saturated.disturbance_gain
                )
            )
        if modulating.sample_count < 2:
            warnings.append(
                "fewer than two modulating samples; the saturated regime cannot be "
                "compared against a controlling baseline in this period"
            )

        return ControlAuthorityResult(
            sample_count=count,
            saturation_fraction=round(saturation_fraction, 4),
            upper_saturation_fraction=round(upper_fraction, 4),
            lower_saturation_fraction=round(lower_fraction, 4),
            modulating_fraction=round(modulating_fraction, 4),
            saturated=saturated,
            modulating=modulating,
            variance_ratio=self._round(variance_ratio, 4),
            gain_ratio=self._round(gain_ratio, 4),
            off_set_point_fraction=self._round(off_set_point_fraction, 4),
            max_rate_per_hour=round(max_rate_per_hour, 6),
            margin_to_limit=self._round(margin_to_limit, 6),
            time_to_limit_h=self._round(time_to_limit_h, 4),
            authority_status=status,
            warnings=tuple(warnings),
            assumptions=(
                "Public, educational screening of a controller output history only.",
                "A sample is saturated when the output sits within the band of a stop.",
                "Both stops count; bottoming out removes authority as surely as "
                "topping out.",
                "Regime statistics assume the samples are evenly spaced in time.",
                "Time to limit uses the largest observed rate, not a forecast.",
                "A saturated loop explains lost rejection; it does not identify what "
                "consumed the authority.",
                "Move to a validated loop review and qualified human judgement.",
            ),
            neqsim_available=find_spec("neqsim") is not None,
        )

    # ------------------------------------------------------------------
    # Multi-period trend: "the process got worse" vs "the loop stopped controlling"
    # ------------------------------------------------------------------
    def compare_periods(
        self, periods: Sequence[PeriodObservation]
    ) -> AuthorityTrendResult:
        """Separate a growing disturbance from a loop that has run out of authority."""
        ordered = tuple(periods)
        if len(ordered) < 2:
            raise ValueError("at least two comparable periods are required")
        for period in ordered:
            if not isinstance(period, PeriodObservation):
                raise ValueError("periods must be PeriodObservation instances")
            if not 0.0 <= period.saturation_fraction <= 1.0:
                raise ValueError(
                    f"saturation_fraction of period '{period.label}' must be in [0, 1]"
                )
            if period.disturbance_std is not None:
                self._require_non_negative(
                    f"disturbance_std of period '{period.label}'", period.disturbance_std
                )

        warnings: list[str] = []
        saturation_change = ordered[-1].saturation_fraction - ordered[0].saturation_fraction
        saturation_relative = self._relative_change(
            ordered[0].saturation_fraction, ordered[-1].saturation_fraction
        )

        have_disturbance = all(period.disturbance_std is not None for period in ordered)
        if have_disturbance:
            disturbance_change = ordered[-1].disturbance_std - ordered[0].disturbance_std
            disturbance_relative = self._relative_change(
                ordered[0].disturbance_std, ordered[-1].disturbance_std
            )
        else:
            disturbance_change = nan
            disturbance_relative = nan
            warnings.append(
                "no disturbance measure supplied for every period; a growing "
                "disturbance cannot be ruled out from saturation alone"
            )

        saturation_rising = saturation_change >= self.saturation_trend_threshold
        disturbance_rising = (
            have_disturbance and disturbance_relative >= self.disturbance_trend_threshold
        )
        disturbance_flat = (
            have_disturbance and abs(disturbance_relative) < self.disturbance_trend_threshold
        )

        if not have_disturbance:
            verdict = "control-authority-loss" if saturation_rising else "indeterminate"
        elif saturation_rising and disturbance_flat:
            verdict = "control-authority-loss"
        elif saturation_rising and disturbance_rising:
            verdict = "both"
        elif disturbance_rising:
            verdict = "disturbance-growth"
        else:
            verdict = "no-significant-trend"

        narrative = self._narrative(
            verdict, ordered, saturation_change, disturbance_relative, have_disturbance
        )
        if verdict == "control-authority-loss":
            warnings.append(
                "the disturbance is flat while saturation grows; an investigation "
                "into the source of the disturbance is looking in the wrong place"
            )

        return AuthorityTrendResult(
            periods=ordered,
            saturation_change=round(saturation_change, 4),
            saturation_relative_change=self._round(saturation_relative, 4),
            disturbance_change=self._round(disturbance_change, 6),
            disturbance_relative_change=self._round(disturbance_relative, 4),
            verdict=verdict,
            narrative=narrative,
            warnings=tuple(warnings),
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _authority_status(self, saturation_fraction: float) -> str:
        if saturation_fraction >= self.lost_saturation_fraction:
            return "authority-lost"
        if saturation_fraction >= self.marginal_saturation_fraction:
            return "authority-marginal"
        return "authority-retained"

    @classmethod
    def _regime_statistics(
        cls,
        index: Sequence[int],
        total: int,
        process_value: Sequence[float],
        disturbance: Sequence[float] | None,
    ) -> RegimeStatistics:
        values = [process_value[i] for i in index]
        mean = sum(values) / len(values) if values else nan
        std = cls._sample_std(values)
        gain, r_squared = nan, nan
        if disturbance is not None and len(index) >= 3:
            gain, r_squared = cls._linear_fit(
                [disturbance[i] for i in index], values
            )
        return RegimeStatistics(
            sample_count=len(index),
            fraction_of_period=round(len(index) / total, 4),
            controlled_variable_mean=cls._round(mean, 6),
            controlled_variable_std=cls._round(std, 6),
            disturbance_gain=cls._round(gain, 6),
            disturbance_r_squared=cls._round(r_squared, 6),
        )

    @staticmethod
    def _sample_std(values: Sequence[float]) -> float:
        if len(values) < 2:
            return nan
        mean = sum(values) / len(values)
        variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
        return sqrt(variance)

    @staticmethod
    def _linear_fit(x: Sequence[float], y: Sequence[float]) -> tuple[float, float]:
        n = len(x)
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        sxx = sum((value - mean_x) ** 2 for value in x)
        syy = sum((value - mean_y) ** 2 for value in y)
        if sxx <= 0.0:
            return nan, nan
        sxy = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        slope = sxy / sxx
        r_squared = (sxy * sxy) / (sxx * syy) if syy > 0.0 else nan
        return slope, r_squared

    @staticmethod
    def _ratio(numerator: float, denominator: float) -> float:
        if not isfinite(numerator) or not isfinite(denominator) or denominator <= 0.0:
            return nan
        return numerator / denominator

    @staticmethod
    def _relative_change(first: float, last: float) -> float:
        if first > 0.0:
            return (last - first) / first
        if last == first:
            return 0.0
        return float("inf") if last > first else float("-inf")

    @staticmethod
    def _narrative(
        verdict: str,
        periods: Sequence[PeriodObservation],
        saturation_change: float,
        disturbance_relative: float,
        have_disturbance: bool,
    ) -> str:
        span = f"{periods[0].label} to {periods[-1].label}"
        saturation = "saturation {} from {:.0%} to {:.0%}".format(
            "rose" if saturation_change >= 0.0 else "fell",
            periods[0].saturation_fraction,
            periods[-1].saturation_fraction,
        )
        if not have_disturbance:
            return f"Over {span}, {saturation}; no disturbance measure was supplied."
        disturbance = "the disturbance changed by {:+.0%}".format(disturbance_relative)
        if verdict == "control-authority-loss":
            return (
                f"Over {span}, {saturation} while {disturbance}. The loop lost "
                "authority; the disturbance did not grow."
            )
        if verdict == "disturbance-growth":
            return (
                f"Over {span}, {disturbance} while {saturation}. The disturbance "
                "grew; the loop still has authority."
            )
        if verdict == "both":
            return (
                f"Over {span}, {saturation} and {disturbance}. Both effects are "
                "present and must be separated before acting."
            )
        return f"Over {span}, {saturation} and {disturbance}. No material trend."

    @staticmethod
    def _round(value: float, digits: int) -> float:
        return value if not isfinite(value) else round(value, digits)

    @classmethod
    def _as_series(cls, name: str, values: Sequence[float], *, minimum: int) -> list[float]:
        series = [float(value) for value in values]
        if len(series) < minimum:
            raise ValueError(f"{name} must contain at least {minimum} samples")
        for value in series:
            cls._require_finite(name, value)
        return series

    @staticmethod
    def _require_finite(name: str, value: float) -> None:
        if not isfinite(value):
            raise ValueError(f"{name} must be finite")

    @classmethod
    def _require_positive(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value <= 0.0:
            raise ValueError(f"{name} must be positive")

    @classmethod
    def _require_non_negative(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value < 0.0:
            raise ValueError(f"{name} must not be negative")
