"""Input distributions for uncertainty quantification.

Every distribution exposes an inverse CDF (``ppf``) so sampling is separated from
the sampler: the sampler produces points in the unit hypercube and each marginal
maps its own coordinate. That separation is what lets a plain pseudo-random run,
a Latin-hypercube run, a Halton run, and an optional SALib Saltelli run all use
the same parameter definitions.

Only the standard library is used. ``statistics.NormalDist`` supplies the normal
inverse CDF.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Any, Dict, Optional

_NORMAL = statistics.NormalDist()

#: Quantiles used to report an unbounded distribution's range in the report table.
REPORT_LOW_QUANTILE = 0.10
REPORT_HIGH_QUANTILE = 0.90


class DistributionError(ValueError):
    """Raised when a distribution is defined with inconsistent parameters."""


def _check_unit_interval(u: float) -> float:
    if not 0.0 <= u <= 1.0:
        raise DistributionError("quantile must be in [0, 1], got {!r}".format(u))
    # Keep unbounded distributions finite at the ends of the unit hypercube.
    return min(max(u, 1.0e-12), 1.0 - 1.0e-12)


@dataclass(frozen=True)
class Distribution:
    """Base class: a named, united marginal with an inverse CDF."""

    name: str
    unit: str = ""
    kind: str = "technical"

    @property
    def distribution_type(self) -> str:
        """Label used in the report's input-parameter table."""
        return type(self).__name__.lower()

    def ppf(self, u: float) -> float:
        """Inverse cumulative distribution function."""
        raise NotImplementedError

    def base(self) -> float:
        """Central/base value used for the tornado and the deterministic case."""
        return self.ppf(0.5)

    def report_low(self) -> float:
        """Low value shown in the report table."""
        return self.ppf(REPORT_LOW_QUANTILE)

    def report_high(self) -> float:
        """High value shown in the report table."""
        return self.ppf(REPORT_HIGH_QUANTILE)

    def to_dict(self) -> Dict[str, Any]:
        """Row for the ``uncertainty.input_parameters`` table."""
        return {
            "name": self.name,
            "unit": self.unit,
            "low": self.report_low(),
            "base": self.base(),
            "high": self.report_high(),
            "distribution": self.distribution_type,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class Deterministic(Distribution):
    """A parameter held fixed; kept in the set so it appears in the basis table."""

    value: float = 0.0

    def ppf(self, u: float) -> float:
        _check_unit_interval(u)
        return self.value

    def base(self) -> float:
        return self.value


@dataclass(frozen=True)
class Uniform(Distribution):
    """Uniform on ``[low, high]``."""

    low: float = 0.0
    high: float = 1.0

    def __post_init__(self) -> None:
        if self.high < self.low:
            raise DistributionError(
                "{}: high ({}) must be >= low ({})".format(self.name, self.high, self.low)
            )

    def ppf(self, u: float) -> float:
        u = _check_unit_interval(u)
        return self.low + u * (self.high - self.low)

    def report_low(self) -> float:
        return self.low

    def report_high(self) -> float:
        return self.high


@dataclass(frozen=True)
class Triangular(Distribution):
    """Triangular on ``[low, high]`` with mode ``base_value``.

    The natural fit for the low/base/high estimates an engineering study
    actually produces.
    """

    low: float = 0.0
    base_value: float = 0.5
    high: float = 1.0

    def __post_init__(self) -> None:
        if not self.low <= self.base_value <= self.high:
            raise DistributionError(
                "{}: require low <= base <= high, got {}, {}, {}".format(
                    self.name, self.low, self.base_value, self.high
                )
            )
        if self.high == self.low:
            raise DistributionError("{}: low and high must differ".format(self.name))

    def ppf(self, u: float) -> float:
        u = _check_unit_interval(u)
        span = self.high - self.low
        split = (self.base_value - self.low) / span
        if u < split:
            return self.low + math.sqrt(u * span * (self.base_value - self.low))
        return self.high - math.sqrt((1.0 - u) * span * (self.high - self.base_value))

    def base(self) -> float:
        return self.base_value

    def report_low(self) -> float:
        return self.low

    def report_high(self) -> float:
        return self.high


@dataclass(frozen=True)
class Normal(Distribution):
    """Normal with mean ``mu`` and standard deviation ``sigma``."""

    mu: float = 0.0
    sigma: float = 1.0

    def __post_init__(self) -> None:
        if self.sigma <= 0.0:
            raise DistributionError("{}: sigma must be > 0".format(self.name))

    def ppf(self, u: float) -> float:
        u = _check_unit_interval(u)
        return self.mu + self.sigma * _NORMAL.inv_cdf(u)

    def base(self) -> float:
        return self.mu


@dataclass(frozen=True)
class LogNormal(Distribution):
    """Log-normal: ``ln(x)`` is normal with mean ``mu_log`` and sd ``sigma_log``.

    Use :meth:`from_p10_p90` when the study states a low/high estimate rather
    than log-space moments.
    """

    mu_log: float = 0.0
    sigma_log: float = 1.0

    def __post_init__(self) -> None:
        if self.sigma_log <= 0.0:
            raise DistributionError("{}: sigma_log must be > 0".format(self.name))

    def ppf(self, u: float) -> float:
        u = _check_unit_interval(u)
        return math.exp(self.mu_log + self.sigma_log * _NORMAL.inv_cdf(u))

    def base(self) -> float:
        return math.exp(self.mu_log)

    @classmethod
    def from_p10_p90(
        cls, name: str, p10: float, p90: float, unit: str = "", kind: str = "technical"
    ) -> "LogNormal":
        """Fit a log-normal to a stated 10th and 90th percentile."""
        if p10 <= 0.0 or p90 <= 0.0:
            raise DistributionError("{}: log-normal requires positive quantiles".format(name))
        if p90 <= p10:
            raise DistributionError("{}: p90 must exceed p10".format(name))
        z = _NORMAL.inv_cdf(0.9)
        sigma_log = (math.log(p90) - math.log(p10)) / (2.0 * z)
        mu_log = 0.5 * (math.log(p90) + math.log(p10))
        return cls(name=name, unit=unit, kind=kind, mu_log=mu_log, sigma_log=sigma_log)


_SPEC_BUILDERS = {
    "deterministic": lambda s: Deterministic(
        name=s["name"],
        unit=s.get("unit", ""),
        kind=s.get("kind", "technical"),
        value=float(s.get("value", s.get("base"))),
    ),
    "uniform": lambda s: Uniform(
        name=s["name"],
        unit=s.get("unit", ""),
        kind=s.get("kind", "technical"),
        low=float(s["low"]),
        high=float(s["high"]),
    ),
    "triangular": lambda s: Triangular(
        name=s["name"],
        unit=s.get("unit", ""),
        kind=s.get("kind", "technical"),
        low=float(s["low"]),
        base_value=float(s["base"]),
        high=float(s["high"]),
    ),
    "normal": lambda s: Normal(
        name=s["name"],
        unit=s.get("unit", ""),
        kind=s.get("kind", "technical"),
        mu=float(s.get("mu", s.get("base"))),
        sigma=float(s["sigma"]),
    ),
    "lognormal": lambda s: LogNormal.from_p10_p90(
        s["name"], float(s["low"]), float(s["high"]), s.get("unit", ""), s.get("kind", "technical")
    )
    if "low" in s
    else LogNormal(
        name=s["name"],
        unit=s.get("unit", ""),
        kind=s.get("kind", "technical"),
        mu_log=float(s["mu_log"]),
        sigma_log=float(s["sigma_log"]),
    ),
}


def from_spec(spec: Dict[str, Any]) -> Distribution:
    """Build a distribution from a JSON/YAML-style specification dictionary.

    ``spec`` needs ``name`` and ``distribution``; the remaining keys depend on
    the type, for example
    ``{"name": "GIP", "distribution": "triangular", "low": 0.65, "base": 1.0,
    "high": 1.45, "unit": "GSm3"}``.
    """
    kind_name = str(spec.get("distribution", "triangular")).strip().lower()
    builder: Optional[Any] = _SPEC_BUILDERS.get(kind_name)
    if builder is None:
        raise DistributionError(
            "unknown distribution '{}' — supported: {}".format(
                kind_name, ", ".join(sorted(_SPEC_BUILDERS))
            )
        )
    return builder(spec)
