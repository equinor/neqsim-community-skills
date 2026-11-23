"""Tunable settings for vector-PDF P&ID extraction.

Defaults suit CAD-exported P&IDs where process piping is drawn with heavier strokes
than symbols, signal lines and annotation. Every value can be overridden per drawing
style; nothing here is specific to one operator or CAD system.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Equipment type letters after the system number (NORSOK Z-DP-002 style tags such as 20VA001,
# 20-PA-001, 23KA001). Values are (kind, DEXPI component class).
DEFAULT_EQUIPMENT_CODES: dict[str, tuple[str, str]] = {
    "VA": ("separator", "Separator"),
    "VD": ("separator", "Separator"),
    "VG": ("separator", "Scrubber"),
    "VE": ("vessel", "PressureVessel"),
    "VZ": ("vessel", "PressureVessel"),
    "TA": ("tank", "StorageTank"),
    "PA": ("pump", "CentrifugalPump"),
    "PB": ("pump", "ReciprocatingPump"),
    "KA": ("compressor", "CentrifugalCompressor"),
    "KB": ("compressor", "ReciprocatingCompressor"),
    "HA": ("heat_exchanger", "ShellAndTubeHeatExchanger"),
    "HB": ("heat_exchanger", "PlateHeatExchanger"),
    "HC": ("heat_exchanger", "AirCooledHeatExchanger"),
    "HG": ("heater", "ElectricHeater"),
    "CD": ("filter", "Filter"),
}

# Words in an off-page connector label that mark a branch without flow in normal operation.
DEFAULT_UTILITY_KEYWORDS: tuple[str, ...] = (
    "DRAIN", "FLARE", "VENT", "SAMPL", "ANTIFOAM", "PILOT", "BLANKET", "PURGE", "CHEMICAL",
    "METHANOL", "BIOCIDE", "INHIBITOR", "EMULSION BREAKER", "DEMULSIFIER", "SCAVENGER", "DEFOAMER", "JET WATER", "NITROGEN", "INSTRUMENT AIR", "UTILITY",
)

# Line-number fluid codes that are utility or no-flow services (overridable per project).
DEFAULT_UTILITY_FLUID_CODES: tuple[str, ...] = ("VF", "DC", "DO", "CH")

# Fluid-code prefixes of utility services (NORSOK Z-DP-002: C* chemicals).
DEFAULT_UTILITY_FLUID_PREFIXES: tuple[str, ...] = ("C",)

# Instrument function letters that denote an actuated valve, mapped to a DEXPI valve class.
DEFAULT_VALVE_FUNCTIONS: dict[str, str] = {
    "XV": "BallValve", "ESV": "BallValve", "SDV": "BallValve", "HV": "BallValve",
    "BDV": "BallValve", "PV": "GlobeValve", "LV": "GlobeValve", "FV": "GlobeValve",
    "TV": "GlobeValve", "PCV": "GlobeValve", "LCV": "GlobeValve", "FCV": "GlobeValve",
}


@dataclass
class ExtractionConfig:
    """Geometry tolerances, stroke-width classes and tag patterns.

    Lengths are in PDF points (1/72 inch).
    """

    process_min_width: float = 0.9
    endpoint_tol: float = 1.6
    gap_max: float = 30.0
    gap_lateral_tol: float = 1.0
    equipment_min_size: tuple[float, float] = (40.0, 25.0)
    boundary_margin: float = 3.0
    nozzle_reach: float = 20.0
    outline_width_tol: float = 0.05
    corner_gap: float = 0.0
    nozzle_label_radius: float = 45.0
    valve_tag_radius: float = 70.0
    lock_text_radius: float = 22.0
    connector_window: float = 70.0
    equipment_tag_regex: str = r"^(?P<sys>\d{2})-?(?P<code>[A-Z]{2})-?(?P<num>\d{3,4}[A-Z]?)$"
    drawing_ref_regex: str = r"^[A-Z0-9]{2,6}(?:-[A-Z0-9]{1,6}){3,6}$"
    line_number_regex: str = r"(?P<size>\d{3,4})(?P<fluid>[A-Z]{2})-(?P<cls>[A-Z]{2}\d{2,3}[A-Z]?)"
    nozzle_regex: str = r"^N\d{1,2}[A-Z]?$"
    instrument_letters_regex: str = r"^[A-Z]{2,4}$"
    instrument_number_regex: str = r"^\d{3,4}[A-Z]?$"
    equipment_codes: dict[str, tuple[str, str]] = field(default_factory=lambda: dict(DEFAULT_EQUIPMENT_CODES))
    utility_keywords: tuple[str, ...] = DEFAULT_UTILITY_KEYWORDS
    utility_fluid_codes: tuple[str, ...] = DEFAULT_UTILITY_FLUID_CODES
    utility_fluid_prefixes: tuple[str, ...] = DEFAULT_UTILITY_FLUID_PREFIXES
    valve_functions: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_VALVE_FUNCTIONS))
