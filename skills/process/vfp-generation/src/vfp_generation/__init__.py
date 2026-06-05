"""Public helpers for generating and handling Eclipse VFPPROD lift-curve tables."""
from __future__ import annotations

from .constraints import (
    DEFAULT_THRESHOLDS,
    classify_named,
    classify_value,
    get_thresholds,
)
from .eclipse_vfp import (
    VFPTable,
    enforce_monotonic,
    format_eclipse_vfp,
    load_vfp_dir,
    parse_vfp_file,
    parse_vfp_text,
)

__all__ = [
    "DEFAULT_THRESHOLDS",
    "classify_value",
    "classify_named",
    "get_thresholds",
    "VFPTable",
    "enforce_monotonic",
    "format_eclipse_vfp",
    "parse_vfp_file",
    "parse_vfp_text",
    "load_vfp_dir",
]
