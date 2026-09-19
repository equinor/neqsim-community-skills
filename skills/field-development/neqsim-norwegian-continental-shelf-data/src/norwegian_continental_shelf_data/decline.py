"""Arps decline-curve fitting and production forecasting (screening).

Deterministic, dependency-free decline-curve analysis for a produced-rate time
series. Fits an Arps decline model (exponential, hyperbolic, or harmonic) to the
declining part of a production series and projects a forward rate profile,
remaining volume, and estimated ultimate recovery (EUR) to an economic-limit
rate.

This is a transparent screening method to orient a study; it is not a reservoir
simulator or a material-balance model. Quantitative production forecasting must
use the validated NeqSim ``SimpleReservoir`` / ``runReservoir`` workflows, and a
qualified human review is required before any decision.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class ArpsFit:
    """A fitted Arps decline model for a produced-rate series."""

    model: str  # "exponential", "hyperbolic", or "harmonic"
    b_exponent: float
    initial_rate: float  # qi at the decline start (same unit as input rate)
    decline_rate_per_year: float  # nominal initial decline Di (1/year)
    r_squared: float
    n_points: int
    peak_time: float
    note: str = ""


def fit_arps_decline(
    series: Sequence[Tuple[float, float]],
    *,
    from_peak: bool = True,
) -> ArpsFit:
    """Fit an Arps decline model to a ``(time, rate)`` production series.

    ``series`` is an iterable of ``(time, rate)`` pairs (for example year and
    annual production). The best of the exponential and hyperbolic/harmonic
    fits (by sum of squared error in rate space) is returned. When ``from_peak``
    is true the fit uses the series from its peak rate onward (decline only).

    Rates must be positive on the fitted window. Raises ``ValueError`` for an
    insufficient or non-declining series.
    """
    points = [(float(t), float(q)) for t, q in series]
    if len(points) < 3:
        raise ValueError("At least three (time, rate) points are required.")
    points.sort(key=lambda p: p[0])

    if from_peak:
        peak_index = max(range(len(points)), key=lambda i: points[i][1])
        window = points[peak_index:]
    else:
        window = points
    if len(window) < 3:
        raise ValueError(
            "At least three points from the peak are required to fit a decline."
        )
    if any(q <= 0.0 for _, q in window):
        raise ValueError("All rates on the fitted window must be positive.")

    t0 = window[0][0]
    peak_rate = window[0][1]
    ts = [t - t0 for t, _ in window]
    qs = [q for _, q in window]

    exp_fit = _fit_exponential(ts, qs, t0)
    hyp_fit = _fit_hyperbolic(ts, qs, t0)

    candidates = [f for f in (exp_fit, hyp_fit) if f is not None]
    if not candidates:
        raise ValueError(
            "Could not fit a declining Arps model; the series may be flat or rising."
        )
    # Choose the model with the higher R-squared in rate space.
    best = max(candidates, key=lambda f: f[1])
    fit, r2 = best
    fit_with_r2 = ArpsFit(
        model=fit.model,
        b_exponent=fit.b_exponent,
        initial_rate=round(peak_rate, 6),
        decline_rate_per_year=round(fit.decline_rate_per_year, 6),
        r_squared=round(r2, 4),
        n_points=len(window),
        peak_time=round(t0, 4),
        note=fit.note,
    )
    return fit_with_r2


def _linear_regression(xs: Sequence[float], ys: Sequence[float]) -> Tuple[float, float, float]:
    """Ordinary least squares. Returns (slope, intercept, r_squared)."""
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    sxx = sum((x - mean_x) ** 2 for x in xs)
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    if sxx == 0.0:
        return 0.0, mean_y, 0.0
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0.0 else 0.0
    return slope, intercept, r2


def _rate_space_r2(ts: Sequence[float], qs: Sequence[float], predict) -> float:
    mean_q = sum(qs) / len(qs)
    ss_tot = sum((q - mean_q) ** 2 for q in qs)
    ss_res = sum((q - predict(t)) ** 2 for t, q in zip(ts, qs))
    if ss_tot <= 0.0:
        return 0.0
    return 1.0 - ss_res / ss_tot


def _fit_exponential(ts, qs, t0) -> Optional[Tuple[ArpsFit, float]]:
    # ln(q) = ln(qi) - D t
    ln_q = [math.log(q) for q in qs]
    slope, intercept, _ = _linear_regression(ts, ln_q)
    decline = -slope
    if decline <= 0.0:
        return None
    qi = math.exp(intercept)

    def predict(t: float) -> float:
        return qi * math.exp(-decline * t)

    r2 = _rate_space_r2(ts, qs, predict)
    fit = ArpsFit(
        model="exponential",
        b_exponent=0.0,
        initial_rate=qi,
        decline_rate_per_year=decline,
        r_squared=r2,
        n_points=len(ts),
        peak_time=t0,
    )
    return fit, r2


def _fit_hyperbolic(ts, qs, t0) -> Optional[Tuple[ArpsFit, float]]:
    # For a fixed b in (0, 1]: q^(-b) = qi^(-b) (1 + b Di t) is linear in t.
    best: Optional[Tuple[ArpsFit, float]] = None
    b = 0.1
    while b <= 1.0 + 1e-9:
        ys = [q ** (-b) for q in qs]
        slope, intercept, _ = _linear_regression(ts, ys)
        if intercept > 0.0 and slope > 0.0:
            qi = intercept ** (-1.0 / b)
            di = slope / (intercept * b)
            if di > 0.0:

                def predict(t: float, _qi=qi, _di=di, _b=b) -> float:
                    return _qi / ((1.0 + _b * _di * t) ** (1.0 / _b))

                r2 = _rate_space_r2(ts, qs, predict)
                model = "harmonic" if abs(b - 1.0) < 1e-9 else "hyperbolic"
                fit = ArpsFit(
                    model=model,
                    b_exponent=round(b, 3),
                    initial_rate=qi,
                    decline_rate_per_year=di,
                    r_squared=r2,
                    n_points=len(ts),
                    peak_time=t0,
                )
                if best is None or r2 > best[1]:
                    best = (fit, r2)
        b += 0.05
    return best


def _predict_rate(fit: ArpsFit, t_since_peak: float) -> float:
    """Predicted rate at ``t_since_peak`` years after the decline start."""
    qi = fit.initial_rate
    di = fit.decline_rate_per_year
    b = fit.b_exponent
    if b <= 0.0:
        return qi * math.exp(-di * t_since_peak)
    return qi / ((1.0 + b * di * t_since_peak) ** (1.0 / b))


@dataclass(frozen=True)
class ProductionForecast:
    """A forward production profile and volumes from an Arps fit."""

    model: str
    economic_limit_rate: float
    years_to_limit: Optional[float]
    profile: List[Tuple[float, float]]  # (time, rate) from the forecast start
    remaining_volume: float
    cumulative_to_date: Optional[float]
    estimated_ultimate_recovery: Optional[float]
    assumptions: List[str] = field(default_factory=list)


def forecast_production(
    fit: ArpsFit,
    *,
    economic_limit_rate: float,
    start_time: Optional[float] = None,
    max_years: float = 50.0,
    timestep_years: float = 1.0,
    cumulative_to_date: Optional[float] = None,
) -> ProductionForecast:
    """Project a forward rate profile and volumes from an Arps ``fit``.

    Rates are stepped forward from ``start_time`` (default: the fit peak time)
    until the rate falls to ``economic_limit_rate`` or ``max_years`` is reached.
    The remaining volume is the trapezoidal integral of the forecast rate over
    time; when ``cumulative_to_date`` (produced so far, same volume basis as
    rate*time) is supplied, an EUR is returned. Screening only.
    """
    _require_positive("economic_limit_rate", economic_limit_rate)
    _require_positive("max_years", max_years)
    _require_positive("timestep_years", timestep_years)

    origin = fit.peak_time if start_time is None else float(start_time)
    t_offset = origin - fit.peak_time
    profile: List[Tuple[float, float]] = []
    remaining = 0.0
    years_to_limit: Optional[float] = None

    steps = int(math.ceil(max_years / timestep_years))
    prev_rate = _predict_rate(fit, t_offset)
    profile.append((round(origin, 4), round(prev_rate, 6)))
    for i in range(1, steps + 1):
        tau = t_offset + i * timestep_years
        rate = _predict_rate(fit, tau)
        # Trapezoidal volume over the step.
        remaining += 0.5 * (prev_rate + rate) * timestep_years
        profile.append((round(origin + i * timestep_years, 4), round(rate, 6)))
        if rate <= economic_limit_rate:
            years_to_limit = round(i * timestep_years, 4)
            break
        prev_rate = rate

    eur: Optional[float] = None
    if cumulative_to_date is not None:
        _require_non_negative("cumulative_to_date", cumulative_to_date)
        eur = round(cumulative_to_date + remaining, 6)

    assumptions = [
        "Forecast uses a fitted Arps decline; screening only, not a reservoir model.",
        "Remaining volume is the trapezoidal integral of the forecast rate.",
    ]
    return ProductionForecast(
        model=fit.model,
        economic_limit_rate=round(economic_limit_rate, 6),
        years_to_limit=years_to_limit,
        profile=profile,
        remaining_volume=round(remaining, 6),
        cumulative_to_date=None if cumulative_to_date is None else round(cumulative_to_date, 6),
        estimated_ultimate_recovery=eur,
        assumptions=assumptions,
    )


def _require_positive(name: str, value: float) -> None:
    if value is None or value <= 0.0:
        raise ValueError(f"{name} must be a positive number, got {value!r}.")


def _require_non_negative(name: str, value: float) -> None:
    if value is None or value < 0.0:
        raise ValueError(f"{name} must be a non-negative number, got {value!r}.")
