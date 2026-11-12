"""NIST/TRC ThermoML Archive client, parser and model comparison (keyless, no login)."""

from __future__ import annotations

from .client import (
    ThermomlClient,
    ThermomlUnavailable,
    default_fetch,
    thermoml_url,
    validate_doi,
)
from .compare import ComparisonSummary, PointResult, compare_points
from .parser import Compound, DataPoint, Dataset, ThermomlReport, parse_thermoml
from .units import pressure_to_bara, split_name_unit

__all__ = [
    "ComparisonSummary",
    "Compound",
    "DataPoint",
    "Dataset",
    "PointResult",
    "ThermomlClient",
    "ThermomlReport",
    "ThermomlUnavailable",
    "compare_points",
    "default_fetch",
    "parse_thermoml",
    "pressure_to_bara",
    "split_name_unit",
    "thermoml_url",
    "validate_doi",
]
