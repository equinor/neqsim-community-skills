"""The Monte Carlo study: sample, evaluate, summarise, rank.

``UncertaintyStudy`` ties the distributions, the sampler and the model together
and produces the numbers the task report needs. It is deliberately small: it
does not own plotting, and it does not decide what the output means.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from .distributions import Distribution
from .models import build_model
from .sampling import DEFAULT_SAMPLER, generate_unit_samples
from .summary_stats import (
    MINIMUM_SAMPLES_SIMULATION,
    SampleSummary,
    summarise,
)

TECHNICAL = "technical"
ECONOMIC = "economic"


class StudyError(RuntimeError):
    """Raised when a study is configured or run incorrectly."""


@dataclass(frozen=True)
class TornadoEntry:
    """One row of the tornado: the output swing caused by one parameter."""

    parameter: str
    unit: str
    input_low: float
    input_high: float
    output_low: float
    output_high: float
    swing: float

    def to_row(self, prefix: str = "output") -> Dict[str, Any]:
        """Report-table row; ``prefix`` names the output, e.g. ``"npv"``."""
        return {
            "parameter": (
                "{} ({:g}-{:g} {})".format(
                    self.parameter, self.input_low, self.input_high, self.unit
                ).strip()
                if self.unit
                else "{} ({:g}-{:g})".format(
                    self.parameter, self.input_low, self.input_high
                )
            ),
            "{}_low".format(prefix): self.output_low,
            "{}_high".format(prefix): self.output_high,
            "swing": self.swing,
        }


@dataclass(frozen=True)
class StudyResult:
    """Outcome of a Monte Carlo run."""

    outputs: List[float]
    samples: List[Dict[str, float]]
    summary: SampleSummary
    sampling_method: str
    seed: Optional[int]
    cache_report: Dict[str, int]
    failures: int = 0

    @property
    def count(self) -> int:
        """Number of successful evaluations."""
        return len(self.outputs)


@dataclass
class UncertaintyStudy:
    """A Monte Carlo uncertainty study over a set of uncertain parameters."""

    parameters: Sequence[Distribution]
    output_name: str = "output"
    output_unit: str = ""
    sampling_method: str = DEFAULT_SAMPLER
    seed: Optional[int] = 42
    model: Optional[Callable[[Dict[str, float]], float]] = None
    technical: Optional[Callable[[Dict[str, float]], Any]] = None
    economic: Optional[Callable[[Any, Dict[str, float]], float]] = None
    simulation_engine: str = ""
    _model: Any = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if not self.parameters:
            raise StudyError("a study needs at least one parameter")
        names = [p.name for p in self.parameters]
        duplicates = {n for n in names if names.count(n) > 1}
        if duplicates:
            raise StudyError("duplicate parameter names: {}".format(", ".join(sorted(duplicates))))
        self._model = build_model(self.model, self.technical, self.economic)

    @property
    def technical_parameters(self) -> List[Distribution]:
        """Parameters that drive the expensive stage."""
        return [p for p in self.parameters if p.kind != ECONOMIC]

    @property
    def economic_parameters(self) -> List[Distribution]:
        """Parameters that only enter the cheap stage."""
        return [p for p in self.parameters if p.kind == ECONOMIC]

    def base_values(self) -> Dict[str, float]:
        """Base (deterministic) value of every parameter."""
        return {p.name: p.base() for p in self.parameters}

    def _split(self, values: Dict[str, float]) -> Any:
        technical = {p.name: values[p.name] for p in self.technical_parameters}
        economic = {p.name: values[p.name] for p in self.economic_parameters}
        return technical, economic

    def evaluate(self, values: Dict[str, float]) -> float:
        """Evaluate the model at one explicit parameter set."""
        missing = [p.name for p in self.parameters if p.name not in values]
        if missing:
            raise StudyError("missing parameter values: {}".format(", ".join(missing)))
        technical, economic = self._split(values)
        return self._model(technical, economic)

    def run(self, n: int, skip_failures: bool = False) -> StudyResult:
        """Sample ``n`` points, evaluate the model, and summarise the output.

        With ``skip_failures`` a raising evaluation is recorded and dropped
        instead of aborting the run — a single non-converged flowsheet then
        costs one sample, not the whole study.
        """
        if n <= 0:
            raise StudyError("n must be positive, got {}".format(n))
        self._model.reset()
        unit_points = generate_unit_samples(
            n, len(self.parameters), self.sampling_method, self.seed
        )
        samples: List[Dict[str, float]] = []
        outputs: List[float] = []
        failures = 0
        for point in unit_points:
            values = {
                parameter.name: parameter.ppf(coordinate)
                for parameter, coordinate in zip(self.parameters, point)
            }
            try:
                outputs.append(self.evaluate(values))
            except Exception:
                if not skip_failures:
                    raise
                failures += 1
                continue
            samples.append(values)
        if not outputs:
            raise StudyError("every evaluation failed; no output to summarise")
        return StudyResult(
            outputs=outputs,
            samples=samples,
            summary=summarise(outputs),
            sampling_method=self.sampling_method,
            seed=self.seed,
            cache_report=self._model.cache_report(),
            failures=failures,
        )

    def tornado(
        self, low_quantile: float = 0.10, high_quantile: float = 0.90
    ) -> List[TornadoEntry]:
        """One-at-a-time sensitivity, ranked by output swing.

        Each parameter is moved to its low and high quantile with the others at
        base. Economic parameters reuse the cached technical stage, so a tornado
        over a NeqSim model costs roughly one solve plus one per technical
        parameter pair, not one per row.
        """
        base = self.base_values()
        entries: List[TornadoEntry] = []
        for parameter in self.parameters:
            low_input = parameter.ppf(low_quantile)
            high_input = parameter.ppf(high_quantile)
            if low_input == high_input:
                continue
            low_case = dict(base)
            low_case[parameter.name] = low_input
            high_case = dict(base)
            high_case[parameter.name] = high_input
            low_output = self.evaluate(low_case)
            high_output = self.evaluate(high_case)
            entries.append(
                TornadoEntry(
                    parameter=parameter.name,
                    unit=parameter.unit,
                    input_low=low_input,
                    input_high=high_input,
                    output_low=low_output,
                    output_high=high_output,
                    swing=abs(high_output - low_output),
                )
            )
        entries.sort(key=lambda e: e.swing, reverse=True)
        return entries

    def minimum_samples(self) -> int:
        """Sample count this study should not go below."""
        return MINIMUM_SAMPLES_SIMULATION
