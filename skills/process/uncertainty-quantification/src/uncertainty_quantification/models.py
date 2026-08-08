"""Two-stage model evaluation with technical/economic caching.

A Monte Carlo run over a NeqSim flowsheet is dominated by the flowsheet solve.
Most economic parameters (price, discount rate, cost multiplier) do not change
the flowsheet at all, so re-solving for them wastes the entire budget.

:class:`StagedModel` makes that split structural: a *technical* stage that is
expensive and cached on its inputs, and an *economic* stage that is cheap and
re-evaluated freely. A single-stage model is still supported for cases where the
split does not apply.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional, Tuple

#: Rounding applied to technical inputs when forming a cache key.
CACHE_KEY_DECIMALS = 12


class ModelError(RuntimeError):
    """Raised when a model cannot be evaluated as configured."""


def _cache_key(values: Dict[str, float]) -> Tuple[Tuple[str, float], ...]:
    return tuple(
        (name, round(float(value), CACHE_KEY_DECIMALS))
        for name, value in sorted(values.items())
    )


@dataclass
class StagedModel:
    """A model split into a cached expensive stage and a cheap stage.

    ``technical`` receives only the parameters tagged ``kind="technical"`` and
    returns any intermediate object (a production profile, a duty, a NeqSim
    result dictionary). ``economic`` receives that intermediate plus the
    parameters tagged ``kind="economic"`` and returns the scalar output.
    """

    technical: Callable[[Dict[str, float]], Any]
    economic: Callable[[Any, Dict[str, float]], float]
    technical_evaluations: int = field(default=0, init=False)
    economic_evaluations: int = field(default=0, init=False)
    cache_hits: int = field(default=0, init=False)
    _cache: Dict[Tuple[Tuple[str, float], ...], Any] = field(
        default_factory=dict, init=False, repr=False
    )

    def reset(self) -> None:
        """Clear the cache and the counters."""
        self._cache.clear()
        self.technical_evaluations = 0
        self.economic_evaluations = 0
        self.cache_hits = 0

    def intermediate(self, technical_values: Dict[str, float]) -> Any:
        """Evaluate (or reuse) the expensive stage."""
        key = _cache_key(technical_values)
        if key in self._cache:
            self.cache_hits += 1
            return self._cache[key]
        result = self.technical(dict(technical_values))
        self._cache[key] = result
        self.technical_evaluations += 1
        return result

    def __call__(
        self, technical_values: Dict[str, float], economic_values: Dict[str, float]
    ) -> float:
        """Full evaluation: cached technical stage, then the economic stage."""
        intermediate = self.intermediate(technical_values)
        self.economic_evaluations += 1
        return float(self.economic(intermediate, dict(economic_values)))

    def cache_report(self) -> Dict[str, int]:
        """Counters describing how much simulation the split actually saved."""
        return {
            "technical_evaluations": self.technical_evaluations,
            "economic_evaluations": self.economic_evaluations,
            "cache_hits": self.cache_hits,
        }


@dataclass
class SingleStageModel:
    """Wrapper giving a plain ``f(values) -> float`` the staged-model interface."""

    model: Callable[[Dict[str, float]], float]
    technical_evaluations: int = field(default=0, init=False)
    economic_evaluations: int = field(default=0, init=False)
    cache_hits: int = field(default=0, init=False)

    def reset(self) -> None:
        """Clear the counters."""
        self.technical_evaluations = 0
        self.economic_evaluations = 0
        self.cache_hits = 0

    def intermediate(self, technical_values: Dict[str, float]) -> Any:
        """No expensive stage to isolate; the inputs pass straight through."""
        return dict(technical_values)

    def __call__(
        self, technical_values: Dict[str, float], economic_values: Dict[str, float]
    ) -> float:
        """Evaluate the model on the merged parameter set."""
        merged: Dict[str, float] = dict(technical_values)
        merged.update(economic_values)
        self.technical_evaluations += 1
        self.economic_evaluations += 1
        return float(self.model(merged))

    def cache_report(self) -> Dict[str, int]:
        """Counters; ``cache_hits`` is always zero for a single-stage model."""
        return {
            "technical_evaluations": self.technical_evaluations,
            "economic_evaluations": self.economic_evaluations,
            "cache_hits": self.cache_hits,
        }


def build_model(
    model: Optional[Callable[[Dict[str, float]], float]] = None,
    technical: Optional[Callable[[Dict[str, float]], Any]] = None,
    economic: Optional[Callable[[Any, Dict[str, float]], float]] = None,
) -> Any:
    """Return a staged or single-stage model from whichever callables were given."""
    if model is not None and (technical is not None or economic is not None):
        raise ModelError("give either 'model' or the 'technical'/'economic' pair")
    if model is not None:
        return SingleStageModel(model)
    if technical is None or economic is None:
        raise ModelError("a staged model needs both 'technical' and 'economic'")
    return StagedModel(technical, economic)
