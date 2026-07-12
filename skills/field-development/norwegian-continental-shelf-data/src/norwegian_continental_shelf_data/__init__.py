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
from .dataset import (
    AnnualProduction,
    NcsDataset,
    NcsField,
    load_dataset,
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
    "DownloadTarget",
    "NORSKPETROLEUM_QUICK_DOWNLOADS",
    "SODIR_FACTPAGES",
    "refresh_instructions",
    "sodir_download_plan",
]
