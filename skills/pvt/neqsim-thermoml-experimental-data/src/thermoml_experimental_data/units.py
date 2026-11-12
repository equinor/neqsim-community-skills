"""Unit helpers for ThermoML names such as ``"Mass density, kg/m3"``."""

from __future__ import annotations

from typing import Optional, Tuple

_PRESSURE_TO_BARA = {"pa": 1.0e-5, "kpa": 1.0e-2, "mpa": 10.0, "bar": 1.0, "atm": 1.01325}


def split_name_unit(label: str) -> Tuple[str, str]:
    """Split ``"Temperature, K"`` into ``("Temperature", "K")``; the unit is ``""`` when absent."""
    text = (label or "").strip()
    if ", " in text:
        name, unit = text.rsplit(", ", 1)
        return name.strip(), unit.strip()
    return text, ""


def pressure_to_bara(value: float, unit: str) -> Optional[float]:
    """Convert a pressure to bara, or return ``None`` for an unknown unit."""
    factor = _PRESSURE_TO_BARA.get(unit.strip().lower())
    return None if factor is None else value * factor
