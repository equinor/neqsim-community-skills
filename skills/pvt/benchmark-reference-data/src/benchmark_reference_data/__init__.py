"""Benchmark reference data for NeqSim task validation.

Public entry points:

* :mod:`~benchmark_reference_data.sources` - registry of independent reference
  sources with authority tier, validated range, and stated uncertainty.
* :mod:`~benchmark_reference_data.reference_data` - offline anchor points that
  work with no optional dependency and no network.
* :mod:`~benchmark_reference_data.coolprop_backend` - optional CoolProp bridge
  for reference values at arbitrary states.
* :mod:`~benchmark_reference_data.comparison` - model-vs-reference comparison
  with independence and resolution checks.
* :mod:`~benchmark_reference_data.report` - the ``benchmark_validation`` block
  for ``results.json`` and a markdown table for the report.
"""

from __future__ import annotations

from .comparison import (
    DEFAULT_TOLERANCE_PCT,
    STATUS_FAIL,
    STATUS_INFO,
    STATUS_PASS,
    STATUS_WARN,
    BenchmarkCase,
    BenchmarkResult,
    compare,
    compare_many,
    default_tolerance_pct,
)
from .reference_data import (
    ANCHOR_POINTS,
    AnchorNotFoundError,
    ReferencePoint,
    anchors_for,
    available_fluids,
    find_anchor,
    normalise_fluid,
)
from .report import MINIMUM_POINTS, BenchmarkReport
from .sources import (
    TIER_ORDER,
    ApplicabilityRange,
    ReferenceSource,
    UnknownSourceError,
    get_source,
    list_sources,
    register_source,
    sources_for,
)

__all__ = [
    "ANCHOR_POINTS",
    "DEFAULT_TOLERANCE_PCT",
    "MINIMUM_POINTS",
    "STATUS_FAIL",
    "STATUS_INFO",
    "STATUS_PASS",
    "STATUS_WARN",
    "TIER_ORDER",
    "AnchorNotFoundError",
    "ApplicabilityRange",
    "BenchmarkCase",
    "BenchmarkReport",
    "BenchmarkResult",
    "ReferencePoint",
    "ReferenceSource",
    "UnknownSourceError",
    "anchors_for",
    "available_fluids",
    "compare",
    "compare_many",
    "default_tolerance_pct",
    "find_anchor",
    "get_source",
    "list_sources",
    "normalise_fluid",
    "register_source",
    "sources_for",
]

__version__ = "0.1.0"
