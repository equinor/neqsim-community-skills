"""Number formatting for report text: significant figures without exponent notation."""

from __future__ import annotations

import math
from typing import Any


def fmt(value: Any, digits: int = 2) -> str:
    """Format a number with a given count of significant figures and no exponent.

    Args:
        value: Number or ``None``.
        digits: Significant figures.

    Returns:
        Text such as ``"0.36"``, ``"8.8"``, ``"220"`` or ``"380 000"``; ``"-"`` for a missing value.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "-"
    v = float(value)
    if v == 0.0:
        return "0"
    exp = math.floor(math.log10(abs(v)))
    rounded = round(v, digits - 1 - exp)
    if abs(rounded) >= 1000.0:
        return f"{rounded:,.0f}".replace(",", " ")
    if abs(rounded) < 1.0e-4:
        return f"{v:.{max(digits - 1, 0)}e}"
    return f"{rounded:.{max(digits - 1 - exp, 0)}f}"
