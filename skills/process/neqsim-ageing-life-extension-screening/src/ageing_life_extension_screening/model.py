"""Educational ageing-trend and remaining-life screening for repairable systems.

Public methods only: the Laplace centroid trend test, the Crow-AMSAA / NHPP
power-law intensity model, and a projection of expected failures to a target
year, plus a simple maintain-versus-replace economic crossover.

The distinction this module exists to enforce: a fleet of repairable items that
is repaired-not-replaced is a *stochastic point process*, not a lifetime
distribution. Fitting a Weibull to the inter-arrival times of a repairable
system and calling the shape parameter an "ageing" indicator is a standard
error; the correct screening statistic is the trend in the rate of occurrence
of failures (ROCOF).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import exp, isfinite, log, sqrt
from typing import Sequence, Tuple

_DAYS_PER_YEAR = 365.25


@dataclass(frozen=True)
class AgeingScreeningResult:
    """Outcome of an ageing / remaining-life screening."""

    n_failures: int
    observation_years: float
    mean_rate_per_year: float
    laplace_u: float
    laplace_verdict: str
    crow_amsaa_beta: float
    crow_amsaa_lambda: float
    beta_confidence_low: float
    beta_confidence_high: float
    rate_now_per_year: float
    rate_at_target_per_year: float
    rate_ratio_target_over_now: float
    expected_failures_to_target: float
    expected_failures_if_no_ageing: float
    excess_failures_from_ageing: float
    ageing_verdict: str
    life_extension_verdict: str
    replacement_crossover_year: float | None
    assumptions: Tuple[str, ...] = field(default_factory=tuple)


class AgeingLifeExtensionModel:
    """Screening-level ageing and life-extension assessment for a repairable population.

    Inputs are the calendar times (in years from an agreed origin) at which
    corrective failures occurred on a population that is repaired and returned
    to service. Outputs are a trend verdict, a fitted power-law intensity, a
    projection of the failure load to a target end-of-life year, and a
    maintain-versus-replace economic crossover.

    All thresholds are configurable and default to values that are common in
    open reliability-engineering practice, not to any operator's internal
    criteria.
    """

    def __init__(
        self,
        *,
        laplace_significance: float = 1.96,
        beta_watch: float = 1.2,
        beta_significant: float = 1.5,
        rate_ratio_watch: float = 1.5,
        rate_ratio_significant: float = 2.0,
    ) -> None:
        if laplace_significance <= 0.0:
            raise ValueError("laplace_significance must be positive")
        if not 1.0 <= beta_watch < beta_significant:
            raise ValueError("require 1.0 <= beta_watch < beta_significant")
        if not 1.0 <= rate_ratio_watch < rate_ratio_significant:
            raise ValueError("require 1.0 <= rate_ratio_watch < rate_ratio_significant")
        self.laplace_significance = laplace_significance
        self.beta_watch = beta_watch
        self.beta_significant = beta_significant
        self.rate_ratio_watch = rate_ratio_watch
        self.rate_ratio_significant = rate_ratio_significant

    # ------------------------------------------------------------------ public

    def evaluate(
        self,
        *,
        failure_times_years: Sequence[float],
        observation_years: float,
        target_year_offset: float,
        population_size: int = 1,
        replacement_cost: float = 0.0,
        corrective_cost_per_failure: float = 0.0,
        annual_cost_of_ownership: float = 0.0,
        discount_rate: float = 0.0,
    ) -> AgeingScreeningResult:
        """Screen a repairable population for ageing and project it to a target year.

        Parameters
        ----------
        failure_times_years:
            Times of corrective failures measured in years from the start of the
            observation window. Must lie in ``(0, observation_years]``.
        observation_years:
            Length of the observation window in years (time-truncated data).
        target_year_offset:
            Years from the END of the observation window to the required
            end-of-life. For "must work until 2037" observed to 2026, this is 11.
        population_size:
            Number of items in the population, used only to normalise the rate.
        replacement_cost, corrective_cost_per_failure, annual_cost_of_ownership:
            Optional economics in any single consistent currency unit. When
            ``replacement_cost`` is zero no crossover is computed.
        discount_rate:
            Annual discount rate as a fraction for the crossover comparison.
        """
        times = self._clean_times(failure_times_years, observation_years)
        self._require_positive("observation_years", observation_years)
        self._require_non_negative("target_year_offset", target_year_offset)
        self._require_positive_int("population_size", population_size)
        for name, value in (
            ("replacement_cost", replacement_cost),
            ("corrective_cost_per_failure", corrective_cost_per_failure),
            ("annual_cost_of_ownership", annual_cost_of_ownership),
            ("discount_rate", discount_rate),
        ):
            self._require_non_negative(name, value)

        n = len(times)
        mean_rate = n / observation_years

        laplace_u = self.laplace_statistic(times, observation_years)
        laplace_verdict = self._laplace_verdict(laplace_u, n)

        beta, lam = self.crow_amsaa_fit(times, observation_years)
        beta_low, beta_high = self._beta_confidence(beta, n)

        target_time = observation_years + target_year_offset
        rate_now = self._power_law_intensity(lam, beta, observation_years)
        rate_target = self._power_law_intensity(lam, beta, target_time)
        rate_ratio = rate_target / rate_now if rate_now > 0.0 else 1.0

        expected_to_target = max(
            0.0, lam * (target_time**beta) - lam * (observation_years**beta)
        )
        expected_no_ageing = mean_rate * target_year_offset
        excess = expected_to_target - expected_no_ageing

        ageing_verdict = self._ageing_verdict(laplace_verdict, beta_low, rate_ratio)
        crossover = self._replacement_crossover(
            lam=lam,
            beta=beta,
            observation_years=observation_years,
            target_year_offset=target_year_offset,
            replacement_cost=replacement_cost,
            corrective_cost_per_failure=corrective_cost_per_failure,
            annual_cost_of_ownership=annual_cost_of_ownership,
            discount_rate=discount_rate,
        )
        life_verdict = self._life_extension_verdict(ageing_verdict, crossover, target_year_offset)

        return AgeingScreeningResult(
            n_failures=n,
            observation_years=observation_years,
            mean_rate_per_year=mean_rate / population_size,
            laplace_u=laplace_u,
            laplace_verdict=laplace_verdict,
            crow_amsaa_beta=beta,
            crow_amsaa_lambda=lam,
            beta_confidence_low=beta_low,
            beta_confidence_high=beta_high,
            rate_now_per_year=rate_now / population_size,
            rate_at_target_per_year=rate_target / population_size,
            rate_ratio_target_over_now=rate_ratio,
            expected_failures_to_target=expected_to_target,
            expected_failures_if_no_ageing=expected_no_ageing,
            excess_failures_from_ageing=excess,
            ageing_verdict=ageing_verdict,
            life_extension_verdict=life_verdict,
            replacement_crossover_year=crossover,
            assumptions=self._assumptions(n, population_size),
        )

    # ------------------------------------------------------------- statistics

    @staticmethod
    def laplace_statistic(times: Sequence[float], observation_years: float) -> float:
        """Laplace centroid trend statistic for a time-truncated point process.

        ``U > 0`` indicates failures clustered late in the window (deteriorating,
        ageing); ``U < 0`` indicates clustering early (improving); ``U`` near
        zero is consistent with a homogeneous Poisson process. ``U`` is
        approximately standard normal under the no-trend null hypothesis.
        """
        n = len(times)
        if n < 2 or observation_years <= 0.0:
            return 0.0
        centroid = sum(times) / n
        return (centroid - observation_years / 2.0) / (
            observation_years / sqrt(12.0 * n)
        )

    @staticmethod
    def crow_amsaa_fit(
        times: Sequence[float], observation_years: float
    ) -> Tuple[float, float]:
        """Maximum-likelihood power-law (Crow-AMSAA / NHPP) fit, time-truncated.

        Returns ``(beta, lambda)`` for the mean cumulative function
        ``N(t) = lambda * t ** beta``. ``beta > 1`` means the rate of occurrence
        of failures is increasing (ageing / wear-out at system level);
        ``beta < 1`` means it is decreasing (reliability growth).
        """
        n = len(times)
        if n < 2 or observation_years <= 0.0:
            return 1.0, (n / observation_years if observation_years > 0.0 else 0.0)
        denom = sum(log(observation_years / t) for t in times if t > 0.0)
        if denom <= 0.0:
            return 1.0, n / observation_years
        beta = n / denom
        lam = n / (observation_years**beta)
        if not (isfinite(beta) and isfinite(lam)):
            return 1.0, n / observation_years
        return beta, lam

    @staticmethod
    def _power_law_intensity(lam: float, beta: float, t: float) -> float:
        if t <= 0.0:
            return 0.0
        return lam * beta * (t ** (beta - 1.0))

    def _beta_confidence(self, beta: float, n: int) -> Tuple[float, float]:
        """Approximate two-sided interval on beta from the MLE standard error.

        The MLE of ``beta`` has asymptotic standard error ``beta / sqrt(n)``.
        """
        if n < 2:
            return beta, beta
        se = beta / sqrt(n)
        half = self.laplace_significance * se
        return max(0.0, beta - half), beta + half

    # ---------------------------------------------------------------- verdicts

    def _laplace_verdict(self, u: float, n: int) -> str:
        if n < 4:
            return "insufficient-data"
        if u > self.laplace_significance:
            return "deteriorating"
        if u < -self.laplace_significance:
            return "improving"
        return "no-significant-trend"

    def _ageing_verdict(self, laplace_verdict: str, beta_low: float, rate_ratio: float) -> str:
        if laplace_verdict == "insufficient-data":
            return "insufficient-data"
        significant = (
            laplace_verdict == "deteriorating"
            and beta_low > 1.0
            and (beta_low >= self.beta_significant or rate_ratio >= self.rate_ratio_significant)
        )
        if significant:
            return "significant-ageing"
        watch = laplace_verdict == "deteriorating" or beta_low > 1.0 or (
            rate_ratio >= self.rate_ratio_watch
        )
        if watch:
            return "ageing-suspected"
        if laplace_verdict == "improving":
            return "improving"
        return "no-ageing-detected"

    def _life_extension_verdict(
        self, ageing_verdict: str, crossover: float | None, target_year_offset: float
    ) -> str:
        if ageing_verdict == "insufficient-data":
            return "insufficient-data-for-decision"
        economics_favour_replacement = (
            crossover is not None and 0.0 < crossover <= target_year_offset
        )
        if ageing_verdict == "significant-ageing" and economics_favour_replacement:
            return "replace"
        if ageing_verdict == "significant-ageing":
            return "extend-with-measures"
        if economics_favour_replacement:
            return "extend-with-measures"
        if ageing_verdict == "ageing-suspected":
            return "extend-with-measures"
        return "extend"

    # --------------------------------------------------------------- economics

    def _replacement_crossover(
        self,
        *,
        lam: float,
        beta: float,
        observation_years: float,
        target_year_offset: float,
        replacement_cost: float,
        corrective_cost_per_failure: float,
        annual_cost_of_ownership: float,
        discount_rate: float,
    ) -> float | None:
        """First year in which cumulative discounted keep-cost exceeds replacement cost."""
        if replacement_cost <= 0.0:
            return None
        if corrective_cost_per_failure <= 0.0 and annual_cost_of_ownership <= 0.0:
            return None
        horizon = max(1, int(round(max(target_year_offset, 1.0))) + 20)
        cumulative = 0.0
        for year in range(1, horizon + 1):
            t0 = observation_years + year - 1
            t1 = observation_years + year
            failures = max(0.0, lam * (t1**beta) - lam * (t0**beta))
            cost = failures * corrective_cost_per_failure + annual_cost_of_ownership
            cumulative += cost / ((1.0 + discount_rate) ** year)
            if cumulative >= replacement_cost:
                return float(year)
        return None

    # ---------------------------------------------------------------- plumbing

    @staticmethod
    def _clean_times(times: Sequence[float], observation_years: float) -> Tuple[float, ...]:
        cleaned = []
        for t in times:
            value = float(t)
            if not isfinite(value):
                raise ValueError("failure_times_years must be finite")
            if value <= 0.0 or value > observation_years:
                raise ValueError(
                    "failure_times_years must lie in (0, observation_years]; "
                    f"got {value} with observation_years={observation_years}"
                )
            cleaned.append(value)
        return tuple(sorted(cleaned))

    @staticmethod
    def _require_positive(name: str, value: float) -> None:
        if not isfinite(value) or value <= 0.0:
            raise ValueError(f"{name} must be a positive finite number")

    @staticmethod
    def _require_non_negative(name: str, value: float) -> None:
        if not isfinite(value) or value < 0.0:
            raise ValueError(f"{name} must be a non-negative finite number")

    @staticmethod
    def _require_positive_int(name: str, value: int) -> None:
        if int(value) != value or value < 1:
            raise ValueError(f"{name} must be an integer >= 1")

    @staticmethod
    def _assumptions(n: int, population_size: int) -> Tuple[str, ...]:
        return (
            "Failures are treated as a non-homogeneous Poisson process (repair "
            "returns the item to the condition just before failure).",
            "The power-law (Crow-AMSAA) intensity is fitted by maximum likelihood "
            "on time-truncated data.",
            "The Laplace statistic is compared against a standard-normal critical "
            "value; it is only meaningful for a stationary reporting regime.",
            "Reporting-practice changes, migration artefacts and campaign-driven "
            "notification bursts are NOT corrected for and must be screened out "
            "of the input series before use.",
            f"Rates are normalised over a population of {population_size} item(s) "
            f"from {n} recorded failure(s).",
            "Screening only; not a substitute for a qualified life-extension "
            "assessment or a structural/technical condition survey.",
        )


def days_to_years(days: float) -> float:
    """Convert a duration in days to years using 365.25 days per year."""
    return days / _DAYS_PER_YEAR


__all__ = [
    "AgeingLifeExtensionModel",
    "AgeingScreeningResult",
    "days_to_years",
]
