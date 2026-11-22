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
from .neqsim_registry import predict_with_fallback, register_in_neqsim

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
    "predict_with_fallback",
    "register_in_neqsim",
    "validate",
]
