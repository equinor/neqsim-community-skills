"""Screening estimate of H2S in the gas of a reservoir, prospect or discovery (mineral buffer plus calibration)."""

from .buffer import (
    MG_PER_NM3_PER_PPM,
    SOUR_SERVICE_KPA,
    H2SBufferUnavailable,
    buffered_h2s,
    correlation_buffer,
    haaland_ppm,
)
from .estimate import estimate_prospect, exceedance, find_analogues, nice_value, ordinal
from .formatting import fmt
from .model import (
    calibrate,
    class_of,
    load_registry,
    lognormal_quantiles,
    save_registry,
)
from .report import build_sections, pct, write_report
from .setting import (
    CARBONATE,
    CONTINENTAL,
    MARINE,
    UNKNOWN,
    classify_setting,
    formation_key,
)

__all__ = [
    "CARBONATE",
    "CONTINENTAL",
    "MARINE",
    "MG_PER_NM3_PER_PPM",
    "SOUR_SERVICE_KPA",
    "UNKNOWN",
    "H2SBufferUnavailable",
    "buffered_h2s",
    "build_sections",
    "calibrate",
    "class_of",
    "classify_setting",
    "correlation_buffer",
    "estimate_prospect",
    "exceedance",
    "find_analogues",
    "fmt",
    "formation_key",
    "haaland_ppm",
    "load_registry",
    "lognormal_quantiles",
    "nice_value",
    "ordinal",
    "pct",
    "save_registry",
    "write_report",
]
