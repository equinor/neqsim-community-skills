"""Screening estimate of mercury in the gas of a reservoir, prospect or discovery."""

from .estimate import (
    SCHEMA,
    distance_km,
    estimate_prospect,
    exceedance,
    find_analogues,
    nice_range,
    nice_value,
)
from .formatting import fmt
from .limits import MercuryLimitUnavailable, mercury_limits
from .model import (
    ShrinkageModel,
    cross_validate,
    group_statistics,
    interval_coverage,
    load_registry,
    lognormal_quantiles,
    save_registry,
)
from .report import build_sections, write_report
from .stratigraphy import (
    FORMATION_TABLE,
    SOURCE_CLASS,
    classify_formation,
    formation_key,
    source_class_of_epoch,
)

__version__ = "0.1.0"

__all__ = [
    "FORMATION_TABLE",
    "SCHEMA",
    "SOURCE_CLASS",
    "MercuryLimitUnavailable",
    "ShrinkageModel",
    "build_sections",
    "classify_formation",
    "cross_validate",
    "distance_km",
    "estimate_prospect",
    "exceedance",
    "find_analogues",
    "fmt",
    "formation_key",
    "group_statistics",
    "interval_coverage",
    "load_registry",
    "lognormal_quantiles",
    "mercury_limits",
    "nice_range",
    "nice_value",
    "save_registry",
    "source_class_of_epoch",
    "write_report",
]
