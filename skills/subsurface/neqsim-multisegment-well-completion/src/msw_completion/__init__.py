"""Multi-segment well completion (AICD, ICD, valve, density-switched) with completor and OPM device equations."""

from .case import build_case, validate_design
from .devices import (Aicd, DensityValve, PhaseProperties, Sicd, Valve, calibrate_strength, device_from_dict,
                      pressure_drop_bar, rate_for_pressure_drop, single_phase_drops)
from .msw import RegularGrid, add_plain_msw, split_schedule
from .runner import CompletorUnavailable, read_device_layer, run_completor
from .screening import Zone, compare_at_same_oil, well_inflow
from .workflow import run_completion_workflow

__all__ = [
    "Aicd", "CompletorUnavailable", "DensityValve", "PhaseProperties", "RegularGrid", "Sicd", "Valve", "Zone",
    "add_plain_msw", "build_case", "calibrate_strength", "compare_at_same_oil", "device_from_dict",
    "pressure_drop_bar", "rate_for_pressure_drop", "read_device_layer", "run_completion_workflow", "run_completor",
    "single_phase_drops", "split_schedule", "validate_design", "well_inflow",
]
