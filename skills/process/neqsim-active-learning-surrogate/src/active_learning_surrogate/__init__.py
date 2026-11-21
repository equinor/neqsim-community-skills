"""Active-learning Gaussian-process surrogates of NeqSim simulations."""

from .gp import GaussianProcess, GPError
from .learner import (
    ActiveLearner,
    IterationRecord,
    LearningResult,
    Parameter,
    Surrogate,
    SurrogateError,
    ValidationReport,
    latin_hypercube,
    validate,
)

__all__ = [
    "ActiveLearner",
    "GPError",
    "GaussianProcess",
    "IterationRecord",
    "LearningResult",
    "Parameter",
    "Surrogate",
    "SurrogateError",
    "ValidationReport",
    "latin_hypercube",
    "validate",
]
