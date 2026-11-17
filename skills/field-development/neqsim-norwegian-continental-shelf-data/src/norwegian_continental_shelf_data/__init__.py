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
    NORSKPETROLEUM_QUICK_DOWNLOADS,
    SODIR_FACTPAGES,
    DownloadTarget,
    refresh_instructions,
    sodir_download_plan,
)

__all__ = [
    "CARBON_COST_BASIS_SOURCE_URL",
    "CO2_SOURCE_SPLIT_2024",
    "GAS_CO2_FACTOR_KG_PER_SM3",
    "NORSKPETROLEUM_QUICK_DOWNLOADS",
    "POWER_FROM_SHORE_FIELDS",
    "SODIR_FACTPAGES",
    "AbatementScreening",
    "AnnualProduction",
    "ArpsFit",
    "CarbonCost",
    "CarbonCostBasis",
    "DownloadTarget",
    "NcsDataset",
    "NcsField",
    "ProductionForecast",
    "ProductionShare",
    "ProductionTrend",
    "ResourceRemaining",
    "abatement_screening",
    "aggregate_field_counts",
    "annual_carbon_cost",
    "carbon_cost_basis",
    "combustion_co2_tonnes",
    "emission_source_split",
    "fields_started_by_decade",
    "fit_arps_decline",
    "forecast_production",
    "load_dataset",
    "production_share",
    "production_trend",
    "rank_fields_by_remaining",
    "refresh_instructions",
    "remaining_reserves_by_area",
    "resource_remaining",
    "sodir_download_plan",
]
