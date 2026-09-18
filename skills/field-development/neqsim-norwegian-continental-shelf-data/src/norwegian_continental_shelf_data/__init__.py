"""Public Norwegian Continental Shelf (NCS) reference data and analysis.

Educational, offline, source-attributed snapshot of headline NCS facts from
norskpetroleum.no and the Norwegian Offshore Directorate FactPages, with query
and screening-analysis helpers for production and resource studies.
"""

from .analysis import (
    ProductionShare,
    ProductionTrend,
    ResourceRemaining,
    aggregate_field_counts,
    fields_started_by_decade,
    production_share,
    production_trend,
    rank_fields_by_remaining,
    remaining_reserves_by_area,
    resource_remaining,
)
from .carbon import (
    CARBON_COST_BASIS_SOURCE_URL,
    CO2_SOURCE_SPLIT_2024,
    GAS_CO2_FACTOR_KG_PER_SM3,
    POWER_FROM_SHORE_FIELDS,
    AbatementScreening,
    CarbonCost,
    CarbonCostBasis,
    abatement_screening,
    annual_carbon_cost,
    carbon_cost_basis,
    combustion_co2_tonnes,
    emission_source_split,
)
from .dataset import (
    AnnualProduction,
    NcsDataset,
    NcsField,
    load_dataset,
)
from .decline import (
    ArpsFit,
    ProductionForecast,
    fit_arps_decline,
    forecast_production,
)
from .sources import (
    DownloadTarget,
    NORSKPETROLEUM_QUICK_DOWNLOADS,
    SODIR_FACTPAGES,
    refresh_instructions,
    sodir_download_plan,
)

__all__ = [
    "AnnualProduction",
    "NcsDataset",
    "NcsField",
    "load_dataset",
    "ArpsFit",
    "ProductionForecast",
    "fit_arps_decline",
    "forecast_production",
    "ProductionShare",
    "ProductionTrend",
    "ResourceRemaining",
    "aggregate_field_counts",
    "fields_started_by_decade",
    "production_share",
    "production_trend",
    "rank_fields_by_remaining",
    "remaining_reserves_by_area",
    "resource_remaining",
    "CARBON_COST_BASIS_SOURCE_URL",
    "CO2_SOURCE_SPLIT_2024",
    "GAS_CO2_FACTOR_KG_PER_SM3",
    "POWER_FROM_SHORE_FIELDS",
    "AbatementScreening",
    "CarbonCost",
    "CarbonCostBasis",
    "abatement_screening",
    "annual_carbon_cost",
    "carbon_cost_basis",
    "combustion_co2_tonnes",
    "emission_source_split",
    "DownloadTarget",
    "NORSKPETROLEUM_QUICK_DOWNLOADS",
    "SODIR_FACTPAGES",
    "refresh_instructions",
    "sodir_download_plan",
]
