"""NCS value-chain optimisation: forecast every field and discovery, route the
whole Norwegian Continental Shelf through its pipelines and plants to market
under capacity limits, and hand the result to NeqSim economics and process models."""

from .opportunities import (
    bottlenecks,
    curtailment,
    production_uplift,
    stranded_discoveries,
    tiein_ranking,
    ullage_timeline,
)
from .optimizer import NcsValueChainOptimizer
from .scenario import (
    DEFAULT_SCENARIO,
    make_scenario,
    validate_scenario,
)
from .scenario import (
    SCHEMA as SCENARIO_SCHEMA,
)
from .supply import build_supply, discovery_profile, forecast_series, total_supply

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_SCENARIO",
    "SCENARIO_SCHEMA",
    "NcsValueChainOptimizer",
    "__version__",
    "bottlenecks",
    "build_supply",
    "curtailment",
    "discovery_profile",
    "forecast_series",
    "make_scenario",
    "production_uplift",
    "stranded_discoveries",
    "tiein_ranking",
    "total_supply",
    "ullage_timeline",
    "validate_scenario",
]
