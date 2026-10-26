"""Sodir open data: catalog and read-only client for the Norwegian Offshore Directorate services."""

from .catalog import describe, field_names, get, items, resolve_id, search
from .client import ReadRecord, SodirOpenData, sql_quote, to_date
from .downloads import ATTRIBUTION, BULK_DATASETS, LICENCE, bulk_download_url, factpages_table_url
from .guides import USE_CASES, use_case

__all__ = [
    "ATTRIBUTION", "BULK_DATASETS", "LICENCE", "ReadRecord", "SodirOpenData", "USE_CASES", "bulk_download_url",
    "describe", "factpages_table_url", "field_names", "get", "items", "resolve_id", "search", "sql_quote",
    "to_date", "use_case",
]
