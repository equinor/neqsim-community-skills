"""Depth-unit conversion and canonical curve mnemonics for well logs."""

from __future__ import annotations

import re

_DEPTH_UNITS_TO_M = {
    "m": 1.0,
    "meter": 1.0,
    "meters": 1.0,
    "metre": 1.0,
    "metres": 1.0,
    "cm": 0.01,
    "mm": 0.001,
    "dm": 0.1,
    "km": 1000.0,
    "ft": 0.3048,
    "f": 0.3048,
    "feet": 0.3048,
    "foot": 0.3048,
    "usft": 1200.0 / 3937.0,
    "in": 0.0254,
    "inch": 0.0254,
}

# Scaled units such as "0.1 in" (common in Schlumberger DLIS) or "0.5 ms".
_SCALED_UNIT = re.compile(r"^\s*([0-9]*\.?[0-9]+)\s*\*?\s*([a-zA-Z]+)\s*$")


def depth_factor_to_m(unit: str) -> float | None:
    """Return the factor that converts a depth in ``unit`` to metres.

    Scaled units such as ``"0.1 in"`` are understood. Returns ``None`` for
    non-depth or unknown units (for example time indices in ``ms``), so callers
    never convert silently.
    """
    if unit is None:
        return None
    text = str(unit).strip()
    if not text:
        return None
    key = text.lower()
    if key in _DEPTH_UNITS_TO_M:
        return _DEPTH_UNITS_TO_M[key]
    scaled = _SCALED_UNIT.match(text)
    if scaled:
        base = _DEPTH_UNITS_TO_M.get(scaled.group(2).lower())
        if base is not None:
            return float(scaled.group(1)) * base
    return None


# Canonical mnemonic -> (aliases, unit hints). Aliases are matched exactly on
# the upper-case file mnemonic; vendor-specific suffixes are handled by prefix rules.
_ALIASES = {
    "DEPT": ("DEPT", "DEPTH", "MD", "TDEP", "DEP", "INDEX"),
    "GR": (
        "GR",
        "GRC",
        "SGR",
        "CGR",
        "GR_EDTC",
        "HSGR",
        "HCGR",
        "ECGR",
        "GRD",
        "GAM",
        "GAMMA",
    ),
    "RHOB": ("RHOB", "RHOZ", "DEN", "DENS", "ZDEN", "RHO8", "HROM", "BDCFM"),
    "NPHI": ("NPHI", "TNPH", "NPOR", "CNC", "NPHI_LS", "APLC", "NEU", "CN", "HTNP"),
    "DT": ("DT", "DTC", "DTCO", "AC", "DT4P", "DTP", "SONIC"),
    "DTS": ("DTS", "DTSM", "DT4S", "DTSH", "DT2"),
    "RDEP": (
        "RDEP",
        "RD",
        "RT",
        "LLD",
        "ILD",
        "RLA5",
        "AT90",
        "AHT90",
        "RILD",
        "HDRS",
        "M2R9",
        "RES_DEEP",
    ),
    "RMED": (
        "RMED",
        "RM",
        "LLS",
        "ILM",
        "RLA3",
        "AT60",
        "AHT60",
        "HMRS",
        "M2R6",
        "RES_MED",
    ),
    "RSHAL": (
        "RSHAL",
        "RS",
        "MSFL",
        "RXO",
        "RXOZ",
        "SFL",
        "RLA1",
        "AT10",
        "AHT10",
        "RES_SHAL",
    ),
    "CALI": (
        "CALI",
        "CAL",
        "HCAL",
        "C1",
        "C2",
        "CALS",
        "CALX",
        "CALY",
        "HDAR",
        "LCAL",
        "BS_CALI",
    ),
    "BS": ("BS", "BIT", "BITSIZE"),
    "SP": ("SP", "SPBR", "SSP"),
    "PEF": ("PEF", "PEFZ", "PE", "PEF8", "HPEF"),
    "DRHO": ("DRHO", "DCOR", "ZCOR", "HDRA", "DRH"),
    "TEMP": ("TEMP", "MTEM", "BHT", "HTEM", "TEMPERATURE"),
    "ROP": ("ROP", "ROPA", "ROP5"),
    "TVD": ("TVD", "TVDSS", "TVDRKB"),
    "WOB": ("WOB", "WOBA", "SWOB"),
}

_ALIAS_LOOKUP = {
    alias: canonical for canonical, aliases in _ALIASES.items() for alias in aliases
}

# Unit + description fallback when the mnemonic is unknown. A unit alone is never
# enough: mud density shares g/cm3 with bulk density, spectral GR components share gAPI.
_DESCRIPTION_RULES = (
    ("RHOB", ("g/cm3", "g/cc", "gm/cc", "g/c3", "kg/m3", "k/m3"), ("bulk density",)),
    ("GR", ("gapi", "api"), ("gamma ray", "gamma-ray")),
    (
        "DT",
        ("us/ft", "us/m"),
        ("compressional", "sonic slowness", "delta-t compressional"),
    ),
    ("DTS", ("us/ft", "us/m"), ("shear",)),
    ("RDEP", ("ohmm", "ohm.m", "ohm-m"), ("deep",)),
    ("RMED", ("ohmm", "ohm.m", "ohm-m"), ("medium", "intermediate")),
    ("RSHAL", ("ohmm", "ohm.m", "ohm-m"), ("shallow", "flushed", "micro")),
    ("CALI", ("in", "inch", "mm", "cm"), ("caliper",)),
    ("PEF", ("b/e",), ("photoelectric",)),
)


def canonical_mnemonic(name: str, unit: str = "", long_name: str = "") -> str | None:
    """Return a canonical mnemonic for a curve, or ``None`` when it cannot be classified.

    Matching order: exact alias, alias with a trailing run/pass suffix stripped
    (``GR_1``, ``RHOB.2``), then unit and description together (for example
    ``g/cm3`` with "bulk density"). A unit alone never classifies a curve,
    because mud density, spectral gamma components and several resistivity
    and sonic curves share units with the curves they are not.
    """
    key = (name or "").strip().upper()
    if key in _ALIAS_LOOKUP:
        return _ALIAS_LOOKUP[key]
    stripped = re.sub(r"[_.\-:]\w{1,3}$", "", key)
    if stripped in _ALIAS_LOOKUP:
        return _ALIAS_LOOKUP[stripped]
    unit_key = (unit or "").strip().lower()
    text = (long_name or "").lower()
    if not text:
        return None
    if "mud" in text or "spectral" in text or "spectroscopy" in text:
        return None
    for canonical, units, phrases in _DESCRIPTION_RULES:
        if unit_key in units and any(phrase in text for phrase in phrases):
            return canonical
    return None
