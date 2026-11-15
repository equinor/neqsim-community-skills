"""Read DLIS, LIS and LAS well logs into a format-neutral model with provenance.

DLIS and LIS are decoded with equinor/dlisio; LAS 1.2/2.0 with a built-in parser.
"""

from .analysis import depth_window_contrast, resample, zone_statistics
from .evidence import SCHEMA, scan_folder, to_evidence, write_evidence, write_frame_csv
from .model import LogCurve, LogFrame, WellLog
from .readers import DEFAULT_NULL_VALUES, detect_format, read_well_log
from .units import canonical_mnemonic, depth_factor_to_m

__all__ = [
    "DEFAULT_NULL_VALUES",
    "SCHEMA",
    "LogCurve",
    "LogFrame",
    "WellLog",
    "canonical_mnemonic",
    "depth_factor_to_m",
    "depth_window_contrast",
    "detect_format",
    "read_well_log",
    "resample",
    "scan_folder",
    "to_evidence",
    "write_evidence",
    "write_frame_csv",
    "zone_statistics",
]
