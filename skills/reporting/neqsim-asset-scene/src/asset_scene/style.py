"""Colour conventions: state colours and value colouring shared by every renderer."""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from typing import Any

RGBA = tuple[float, float, float, float]

STATE_COLORS: dict[str, RGBA] = {
    "existing": (0.62, 0.64, 0.67, 1.0),
    "proposed": (0.05, 0.45, 0.85, 1.0),
    "modified": (0.95, 0.55, 0.10, 1.0),
    "removed": (0.85, 0.20, 0.20, 0.35),
}

STATE_LABELS = {
    "existing": "Existing",
    "proposed": "Proposed",
    "modified": "Modified",
    "removed": "Removed",
}

# Existing objects get a slightly different grey per group so topside, subsea
# and wells stay readable while all "existing" items remain neutral.
GROUP_TINT: dict[str, tuple[float, float, float]] = {
    "facility": (0.62, 0.64, 0.67),
    "subsea": (0.50, 0.55, 0.58),
    "well": (0.45, 0.38, 0.30),
    "reservoir": (0.70, 0.62, 0.45),
    "structure": (0.75, 0.75, 0.72),
}

NO_VALUE_COLOR: RGBA = (0.85, 0.85, 0.85, 0.6)

# Traffic light for utilisation-type quantities (fraction of a limit).
UTILISATION_STOPS: list[tuple[float, tuple[float, float, float]]] = [
    (0.0, (0.10, 0.60, 0.30)),
    (0.8, (0.95, 0.80, 0.15)),
    (1.0, (0.90, 0.25, 0.15)),
]

# Perceptual sequential ramp (viridis-like) for any other quantity.
SEQUENTIAL_STOPS: list[tuple[float, tuple[float, float, float]]] = [
    (0.0, (0.27, 0.00, 0.33)),
    (0.25, (0.23, 0.32, 0.55)),
    (0.5, (0.13, 0.57, 0.55)),
    (0.75, (0.37, 0.79, 0.38)),
    (1.0, (0.99, 0.91, 0.14)),
]


def _ramp(
    stops: Sequence[tuple[float, tuple[float, float, float]]], t: float
) -> tuple[float, float, float]:
    if t <= stops[0][0]:
        return stops[0][1]
    for (t0, c0), (t1, c1) in itertools.pairwise(stops):
        if t <= t1:
            f = (t - t0) / (t1 - t0) if t1 > t0 else 0.0
            return tuple(c0[i] + f * (c1[i] - c0[i]) for i in range(3))  # type: ignore[return-value]
    return stops[-1][1]


def state_color(obj: dict[str, Any]) -> RGBA:
    """Colour by state; existing objects use the group tint."""
    state = obj.get("state", "existing")
    if state == "existing":
        tint = GROUP_TINT.get(obj.get("group", "facility"), GROUP_TINT["facility"])
        return (tint[0], tint[1], tint[2], 1.0)
    return STATE_COLORS.get(state, STATE_COLORS["existing"])


def object_value(obj: dict[str, Any], channel: str, key: str) -> float | None:
    """Numeric value of ``obj[channel][key]`` (accepts a bare number or ``{"value": ...}``)."""
    entry = obj.get(channel, {}).get(key)
    if isinstance(entry, dict):
        entry = entry.get("value")
    try:
        val = float(entry)
    except (TypeError, ValueError):
        return None
    return val if math.isfinite(val) else None


class ColorBy:
    """Colour objects by a numeric value in ``results`` or ``live``.

    ``mode='utilisation'`` uses a green-amber-red ramp with 0.8 and 1.0 breakpoints
    (fraction of a limit); ``mode='sequential'`` spans ``vmin``..``vmax``.
    """

    def __init__(
        self,
        channel: str,
        key: str,
        mode: str = "sequential",
        vmin: float | None = None,
        vmax: float | None = None,
        unit: str = "",
        label: str | None = None,
    ) -> None:
        if channel not in ("results", "live", "attributes"):
            raise ValueError("channel must be results, live or attributes")
        if mode not in ("sequential", "utilisation"):
            raise ValueError("mode must be sequential or utilisation")
        self.channel = channel
        self.key = key
        self.mode = mode
        self.vmin = vmin
        self.vmax = vmax
        self.unit = unit
        self.label = label or key

    def fit(self, objects: Sequence[dict[str, Any]]) -> ColorBy:
        """Set the range from the data when not given."""
        vals = [
            v
            for v in (object_value(o, self.channel, self.key) for o in objects)
            if v is not None
        ]
        if self.mode == "utilisation":
            self.vmin = 0.0 if self.vmin is None else self.vmin
            self.vmax = 1.2 if self.vmax is None else self.vmax
        elif vals:
            self.vmin = min(vals) if self.vmin is None else self.vmin
            self.vmax = max(vals) if self.vmax is None else self.vmax
        return self

    def color(self, obj: dict[str, Any]) -> RGBA:
        """Colour for an object (``NO_VALUE_COLOR`` when missing)."""
        val = object_value(obj, self.channel, self.key)
        if val is None:
            return NO_VALUE_COLOR
        if self.mode == "utilisation":
            rgb = _ramp(UTILISATION_STOPS, val)
        else:
            lo = self.vmin if self.vmin is not None else val
            hi = self.vmax if self.vmax is not None else val
            t = 0.5 if hi == lo else (val - lo) / (hi - lo)
            rgb = _ramp(SEQUENTIAL_STOPS, max(0.0, min(1.0, t)))
        alpha = STATE_COLORS["removed"][3] if obj.get("state") == "removed" else 1.0
        return (rgb[0], rgb[1], rgb[2], alpha)

    def legend_stops(self, n: int = 5) -> list[tuple[float, RGBA]]:
        """Values and colours for a legend bar."""
        lo = self.vmin if self.vmin is not None else 0.0
        hi = self.vmax if self.vmax is not None else 1.0
        out = []
        for i in range(n):
            v = lo + (hi - lo) * i / (n - 1)
            probe = {self.channel: {self.key: v}, "state": "existing"}
            out.append((v, self.color(probe)))
        return out

    def describe(self) -> str:
        """Caption text."""
        unit = f" [{self.unit}]" if self.unit else ""
        src = {
            "results": "NeqSim result",
            "live": "live value",
            "attributes": "attribute",
        }[self.channel]
        return f"coloured by {src} '{self.label}'{unit}; light grey = no value"


def object_color(obj: dict[str, Any], color_by: ColorBy | None = None) -> RGBA:
    """Final colour for an object."""
    return color_by.color(obj) if color_by else state_color(obj)


def hex_color(rgba: RGBA) -> str:
    """``#rrggbb`` string."""
    return "#{:02x}{:02x}{:02x}".format(
        *tuple(round(max(0.0, min(1.0, c)) * 255) for c in rgba[:3])
    )
