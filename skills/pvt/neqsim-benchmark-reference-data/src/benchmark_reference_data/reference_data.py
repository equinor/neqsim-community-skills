"""Offline anchor points for benchmark validation.

CoolProp is the primary reference generator, but a benchmark must still be
possible on a machine with no optional dependency and no network. These anchor
points are published constants and single states taken directly from the
reference formulations in :mod:`benchmark_reference_data.sources`. They are
deliberately few: critical points, triple points, normal boiling points, and one
liquid density, i.e. values that are quoted identically across the literature.

They are a smoke-test set. A real study should extend the comparison with
CoolProp, lab data, or a published case relevant to the fluid actually modelled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .sources import ReferenceSource, get_source


class AnchorNotFoundError(LookupError):
    """Raised when no anchor point matches the requested fluid/property/state."""


@dataclass(frozen=True)
class ReferencePoint:
    """A single independent reference value with its provenance."""

    fluid: str
    property_name: str
    value: float
    unit: str
    source_key: str
    state: Dict[str, float] = field(default_factory=dict)
    uncertainty_pct: Optional[float] = None
    note: str = ""

    @property
    def source(self) -> ReferenceSource:
        """The registered source this value came from."""
        return get_source(self.source_key)

    @property
    def citation(self) -> str:
        """Full citation string for the report."""
        return self.source.citation

    def effective_uncertainty_pct(self) -> Optional[float]:
        """Point uncertainty, falling back to the source's stated uncertainty."""
        if self.uncertainty_pct is not None:
            return self.uncertainty_pct
        return self.source.property_uncertainty_pct(self.property_name)

    def state_summary(self) -> str:
        """Compact human-readable state description."""
        if not self.state:
            return "-"
        return ", ".join(
            "{}={:g}".format(key, value) for key, value in sorted(self.state.items())
        )


def _point(
    fluid: str,
    property_name: str,
    value: float,
    unit: str,
    source_key: str,
    state: Optional[Dict[str, float]] = None,
    note: str = "",
) -> ReferencePoint:
    return ReferencePoint(
        fluid=fluid,
        property_name=property_name,
        value=value,
        unit=unit,
        source_key=source_key,
        state=dict(state or {}),
        note=note,
    )


ANCHOR_POINTS: Tuple[ReferencePoint, ...] = (
    # Water - IAPWS-95
    _point("water", "critical_temperature", 647.096, "K", "iapws95"),
    _point("water", "critical_pressure", 22.064e6, "Pa", "iapws95"),
    _point("water", "critical_density", 322.0, "kg/m3", "iapws95"),
    _point("water", "triple_point_temperature", 273.16, "K", "iapws95"),
    _point("water", "triple_point_pressure", 611.657, "Pa", "iapws95"),
    _point(
        "water",
        "normal_boiling_point",
        373.1243,
        "K",
        "iapws95",
        {"pressure_Pa": 101325.0},
    ),
    _point(
        "water",
        "density",
        997.047,
        "kg/m3",
        "iapws95",
        {"temperature_K": 298.15, "pressure_Pa": 101325.0},
        note="Saturated liquid-like compressed state at ambient conditions.",
    ),
    # Carbon dioxide - Span & Wagner (1996)
    _point("co2", "critical_temperature", 304.1282, "K", "span_wagner_co2"),
    _point("co2", "critical_pressure", 7.3773e6, "Pa", "span_wagner_co2"),
    _point("co2", "critical_density", 467.6, "kg/m3", "span_wagner_co2"),
    _point("co2", "triple_point_temperature", 216.592, "K", "span_wagner_co2"),
    _point("co2", "triple_point_pressure", 517.95e3, "Pa", "span_wagner_co2"),
    _point(
        "co2",
        "sublimation_temperature",
        194.686,
        "K",
        "span_wagner_co2",
        {"pressure_Pa": 101325.0},
        note="CO2 sublimes at atmospheric pressure; there is no normal boiling point.",
    ),
    # Methane - Setzmann & Wagner (1991)
    _point("methane", "critical_temperature", 190.564, "K", "setzmann_wagner_methane"),
    _point("methane", "critical_pressure", 4.5992e6, "Pa", "setzmann_wagner_methane"),
    _point("methane", "critical_density", 162.66, "kg/m3", "setzmann_wagner_methane"),
    _point(
        "methane",
        "normal_boiling_point",
        111.667,
        "K",
        "setzmann_wagner_methane",
        {"pressure_Pa": 101325.0},
    ),
    # Nitrogen - Span et al. (2000)
    _point("nitrogen", "critical_temperature", 126.192, "K", "span_nitrogen"),
    _point("nitrogen", "critical_pressure", 3.3958e6, "Pa", "span_nitrogen"),
    _point("nitrogen", "critical_density", 313.3, "kg/m3", "span_nitrogen"),
    _point(
        "nitrogen",
        "normal_boiling_point",
        77.355,
        "K",
        "span_nitrogen",
        {"pressure_Pa": 101325.0},
    ),
    # Ethane - Bucker & Wagner (2006)
    _point("ethane", "critical_temperature", 305.322, "K", "bucker_wagner_ethane"),
    _point("ethane", "critical_pressure", 4.8722e6, "Pa", "bucker_wagner_ethane"),
    _point("ethane", "critical_density", 206.18, "kg/m3", "bucker_wagner_ethane"),
    # Propane - Lemmon et al. (2009)
    _point("propane", "critical_temperature", 369.89, "K", "lemmon_propane"),
    _point("propane", "critical_pressure", 4.2512e6, "Pa", "lemmon_propane"),
    _point("propane", "critical_density", 220.48, "kg/m3", "lemmon_propane"),
)


_FLUID_ALIASES: Dict[str, str] = {
    "carbon dioxide": "co2",
    "carbondioxide": "co2",
    "h2o": "water",
    "n2": "nitrogen",
    "c1": "methane",
    "c2": "ethane",
    "c3": "propane",
}


def normalise_fluid(fluid: str) -> str:
    """Map common aliases onto the anchor-table fluid names."""
    key = fluid.strip().lower()
    return _FLUID_ALIASES.get(key, key)


def anchors_for(fluid: str) -> List[ReferencePoint]:
    """All anchor points for a fluid."""
    name = normalise_fluid(fluid)
    return [p for p in ANCHOR_POINTS if p.fluid == name]


def available_fluids() -> List[str]:
    """Fluids covered by the offline anchor table."""
    return sorted({p.fluid for p in ANCHOR_POINTS})


def _state_matches(
    point: ReferencePoint, state: Dict[str, float], rel_tol: float
) -> bool:
    for key, wanted in state.items():
        if key not in point.state:
            return False
        actual = point.state[key]
        scale = max(abs(wanted), 1.0)
        if abs(actual - wanted) > rel_tol * scale:
            return False
    return True


def find_anchor(
    fluid: str,
    property_name: str,
    rel_tol: float = 1.0e-6,
    **state: float,
) -> ReferencePoint:
    """Return the anchor point for a fluid/property, optionally at a given state.

    ``state`` keys use the same names as :attr:`ReferencePoint.state`, for
    example ``temperature_K=298.15, pressure_Pa=101325.0``.
    """
    name = normalise_fluid(fluid)
    candidates = [
        p for p in ANCHOR_POINTS if p.fluid == name and p.property_name == property_name
    ]
    if state:
        candidates = [p for p in candidates if _state_matches(p, state, rel_tol)]
    if not candidates:
        raise AnchorNotFoundError(
            "no anchor point for fluid='{}', property='{}', state={} — "
            "available fluids: {}".format(
                fluid, property_name, state or "any", ", ".join(available_fluids())
            )
        )
    return candidates[0]
