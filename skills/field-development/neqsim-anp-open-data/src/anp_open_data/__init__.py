"""Helpers for reading Brazilian ANP open data safely.

The module makes no assumption about column names. Callers pass a mapping from
their file's header to the fields they need, so a change in a dataset is a
visible error instead of a silent wrong number.
"""

from .tools import (
    OIL_M3_TO_BBL,
    check_crs,
    gas_volume,
    haversine_km,
    load_table,
    monthly_to_daily,
    oil_volume,
)

__all__ = [
    "OIL_M3_TO_BBL",
    "check_crs",
    "gas_volume",
    "haversine_km",
    "load_table",
    "monthly_to_daily",
    "oil_volume",
]
