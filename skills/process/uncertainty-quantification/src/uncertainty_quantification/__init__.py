"""Uncertainty quantification for NeqSim tasks.

Public entry points:

* :mod:`~uncertainty_quantification.distributions` - marginals with inverse CDFs.
* :mod:`~uncertainty_quantification.sampling` - unit-hypercube samplers
  (pseudo-random, Latin hypercube, Halton).
* :mod:`~uncertainty_quantification.models` - technical/economic staging with
  caching of the expensive stage.
* :mod:`~uncertainty_quantification.study` - the Monte Carlo run and tornado.
* :mod:`~uncertainty_quantification.summary_stats` - percentiles and convergence.
* :mod:`~uncertainty_quantification.backends` - optional SALib and chaospy.
* :mod:`~uncertainty_quantification.report` - the ``uncertainty`` block for
  ``results.json``.
"""

from __future__ import annotations

from .distributions import (
    Deterministic,
    Distribution,
    DistributionError,
    LogNormal,
    Normal,
    Triangular,
    Uniform,
    from_spec,
)
from .models import ModelError, SingleStageModel, StagedModel, build_model
from .report import MAX_MEDIAN_DRIFT_PCT, UncertaintyReport
from .sampling import (
    DEFAULT_SAMPLER,
    SamplingError,
    available_samplers,
    generate_unit_samples,
    halton,
    latin_hypercube,
    random_samples,
)
from .study import (
    ECONOMIC,
    TECHNICAL,
    StudyError,
    StudyResult,
    TornadoEntry,
    UncertaintyStudy,
)
from .summary_stats import (
    MINIMUM_SAMPLES_SIMULATION,
    MINIMUM_SAMPLES_SURROGATE,
    SampleSummary,
    StatisticsError,
    mean_standard_error,
    percentile,
    probability_below,
    split_half_drift_pct,
    summarise,
)

__all__ = [
    "DEFAULT_SAMPLER",
    "ECONOMIC",
    "MAX_MEDIAN_DRIFT_PCT",
    "MINIMUM_SAMPLES_SIMULATION",
    "MINIMUM_SAMPLES_SURROGATE",
    "TECHNICAL",
    "Deterministic",
    "Distribution",
    "DistributionError",
    "LogNormal",
    "ModelError",
    "Normal",
    "SampleSummary",
    "SamplingError",
    "SingleStageModel",
    "StagedModel",
    "StatisticsError",
    "StudyError",
    "StudyResult",
    "TornadoEntry",
    "Triangular",
    "UncertaintyReport",
    "UncertaintyStudy",
    "Uniform",
    "available_samplers",
    "build_model",
    "from_spec",
    "generate_unit_samples",
    "halton",
    "latin_hypercube",
    "mean_standard_error",
    "percentile",
    "probability_below",
    "random_samples",
    "split_half_drift_pct",
    "summarise",
]

__version__ = "0.1.0"
