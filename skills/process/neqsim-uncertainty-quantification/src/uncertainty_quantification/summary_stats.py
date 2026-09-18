"""Summary statistics for a Monte Carlo output sample.

**Percentile convention.** ``p10`` here is the 10th percentile, i.e. the *low*
estimate, so ``p10 <= p50 <= p90`` always holds. This is the convention the
NeqSim task gate enforces. It is the opposite of the petroleum resource
convention, where P10 is the *high* (optimistic) volume estimate. When a study
reports resources, state which convention the table uses; this module never
silently flips them.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Sequence

#: Monte Carlo runs that call a full simulation per sample.
MINIMUM_SAMPLES_SIMULATION = 200

#: Monte Carlo runs on a cheap correlation or surrogate.
MINIMUM_SAMPLES_SURROGATE = 1000


class StatisticsError(ValueError):
    """Raised when a statistic is requested from an unusable sample."""


def percentile(values: Sequence[float], fraction: float) -> float:
    """Linear-interpolation percentile, matching ``numpy.percentile`` defaults.

    ``fraction`` is in ``[0, 1]``, so the 10th percentile is ``0.10``.
    """
    if not values:
        raise StatisticsError("percentile of an empty sample is undefined")
    if not 0.0 <= fraction <= 1.0:
        raise StatisticsError("fraction must be in [0, 1], got {!r}".format(fraction))
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = fraction * (len(ordered) - 1)
    lower = int(math.floor(position))
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def probability_below(values: Sequence[float], threshold: float = 0.0) -> float:
    """Fraction of samples strictly below ``threshold``, in percent."""
    if not values:
        raise StatisticsError("probability of an empty sample is undefined")
    below = sum(1 for v in values if v < threshold)
    return 100.0 * below / len(values)


def mean_standard_error(values: Sequence[float]) -> float:
    """Standard error of the mean — the Monte Carlo error on the reported mean."""
    if len(values) < 2:
        raise StatisticsError("standard error needs at least two samples")
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance / len(values))


def split_half_drift_pct(values: Sequence[float], fraction: float = 0.5) -> float:
    """Drift of a percentile between the first and second half of the run.

    Expressed as a percentage of the **P10-P90 spread**, not of the percentile's
    own magnitude: an output whose median sits near zero would otherwise report
    an enormous relative drift for a perfectly converged run.
    """
    if len(values) < 4:
        raise StatisticsError("convergence check needs at least four samples")
    midpoint = len(values) // 2
    first = percentile(values[:midpoint], fraction)
    second = percentile(values[midpoint:], fraction)
    spread = percentile(values, 0.90) - percentile(values, 0.10)
    scale = spread if spread > 0.0 else max(abs(first), abs(second))
    if scale == 0.0:
        return 0.0
    return 100.0 * abs(second - first) / scale


@dataclass(frozen=True)
class SampleSummary:
    """Percentiles and moments of one output sample."""

    count: int
    mean: float
    std: float
    minimum: float
    maximum: float
    p10: float
    p50: float
    p90: float
    standard_error: float
    drift_pct: float
    prob_negative_pct: float

    def to_dict(self) -> Dict[str, float]:
        """Flat dictionary merged into the ``uncertainty`` report block."""
        return {
            "n_simulations": self.count,
            "mean": self.mean,
            "std": self.std,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "p10": self.p10,
            "p50": self.p50,
            "p90": self.p90,
            "standard_error_of_mean": self.standard_error,
            "median_drift_pct_of_spread": self.drift_pct,
            "prob_negative_pct": self.prob_negative_pct,
        }


def summarise(values: Sequence[float], threshold: float = 0.0) -> SampleSummary:
    """Summarise an output sample."""
    data: List[float] = [float(v) for v in values]
    if not data:
        raise StatisticsError("cannot summarise an empty sample")
    count = len(data)
    mean = sum(data) / count
    if count > 1:
        variance = sum((v - mean) ** 2 for v in data) / (count - 1)
        std = math.sqrt(variance)
        standard_error = math.sqrt(variance / count)
    else:
        std = 0.0
        standard_error = 0.0
    drift = split_half_drift_pct(data) if count >= 4 else 0.0
    return SampleSummary(
        count=count,
        mean=mean,
        std=std,
        minimum=min(data),
        maximum=max(data),
        p10=percentile(data, 0.10),
        p50=percentile(data, 0.50),
        p90=percentile(data, 0.90),
        standard_error=standard_error,
        drift_pct=drift,
        prob_negative_pct=probability_below(data, threshold),
    )
