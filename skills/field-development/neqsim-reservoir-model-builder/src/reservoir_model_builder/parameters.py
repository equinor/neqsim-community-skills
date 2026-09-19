"""Parameter records, provenance ranking, and public default/analogue tables.

Every number that ends up in a reservoir model is wrapped in a :class:`Parameter`
so that the model can always answer "where did this come from?". Defaults in this
module are generic, publicly documented screening values; they are never a
substitute for field-specific data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Iterable, Mapping

#: Provenance labels ordered from weakest to strongest evidence.
PROVENANCE_RANK: Mapping[str, int] = {
    "default": 0,
    "analogue": 1,
    "derived": 2,
    "public-reported": 2,
    "interpreted": 3,
    "measured": 4,
}

#: Provenance labels that count as real field data rather than a placeholder.
DATA_BACKED_PROVENANCE = ("public-reported", "interpreted", "measured")


@dataclass(frozen=True)
class Parameter:
    """A single reservoir-model input with its unit, provenance and range."""

    name: str
    value: float
    unit: str
    provenance: str
    reference: str = ""
    low: float | None = None
    high: float | None = None
    basis: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.provenance not in PROVENANCE_RANK:
            raise ValueError(
                f"unknown provenance '{self.provenance}' for {self.name}; "
                f"expected one of {sorted(PROVENANCE_RANK)}"
            )
        if not isfinite(self.value):
            raise ValueError(f"value for {self.name} must be finite")

    @property
    def rank(self) -> int:
        return PROVENANCE_RANK[self.provenance]

    @property
    def is_data_backed(self) -> bool:
        return self.provenance in DATA_BACKED_PROVENANCE

    @property
    def uncertainty_pct(self) -> float | None:
        """Half-width of the low/high range as a percentage of the value."""
        if self.low is None or self.high is None or self.value == 0.0:
            return None
        return round(100.0 * (self.high - self.low) / (2.0 * abs(self.value)), 1)

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "unit": self.unit,
            "provenance": self.provenance,
            "reference": self.reference,
            "low": self.low,
            "high": self.high,
            "uncertainty_pct": self.uncertainty_pct,
            "basis": list(self.basis),
        }


def derived(
    name: str,
    value: float,
    unit: str,
    basis: Iterable[Parameter],
    reference: str = "",
    low: float | None = None,
    high: float | None = None,
) -> Parameter:
    """Build a derived parameter that records which parameters produced it."""
    parents = tuple(parameter.name for parameter in basis)
    return Parameter(
        name=name,
        value=value,
        unit=unit,
        provenance="derived",
        reference=reference,
        low=low,
        high=high,
        basis=parents,
    )


# ---------------------------------------------------------------------------
# Public screening defaults
# ---------------------------------------------------------------------------

#: Normal (hydrostatic) pore-pressure gradient, bar per metre of true vertical depth.
HYDROSTATIC_GRADIENT_BAR_PER_M = 0.1050

#: Atmospheric pressure used as the standard-condition reference, bara.
STANDARD_PRESSURE_BARA = 1.01325

#: Standard temperature used for Sm3 (15 degC), kelvin.
STANDARD_TEMPERATURE_K = 288.15

#: Typical seabed temperature by sea area, degC.
SEABED_TEMPERATURE_C: Mapping[str, float] = {
    "north_sea": 6.0,
    "norwegian_sea": 4.0,
    "barents_sea": 4.0,
    "generic": 6.0,
}

#: Typical geothermal gradient by sea area, degC per km below seabed.
GEOTHERMAL_GRADIENT_C_PER_KM: Mapping[str, float] = {
    "north_sea": 37.0,
    "norwegian_sea": 38.0,
    "barents_sea": 33.0,
    "generic": 35.0,
}

#: Screening recovery factor (low, base, high) keyed by (fluid type, drive mechanism).
RECOVERY_FACTOR: Mapping[tuple[str, str], tuple[float, float, float]] = {
    ("gas", "depletion"): (0.60, 0.75, 0.90),
    ("gas", "water_drive"): (0.45, 0.60, 0.75),
    ("gas_condensate", "depletion"): (0.55, 0.70, 0.85),
    ("gas_condensate", "water_drive"): (0.40, 0.55, 0.70),
    ("oil", "solution_gas_drive"): (0.05, 0.18, 0.30),
    ("oil", "gas_cap_drive"): (0.15, 0.28, 0.40),
    ("oil", "water_drive"): (0.25, 0.38, 0.55),
    ("oil", "water_injection"): (0.30, 0.45, 0.60),
    ("oil", "gas_injection"): (0.25, 0.40, 0.55),
}

#: Aquifer pore volume expressed as a multiple of the hydrocarbon pore volume.
AQUIFER_VOLUME_MULTIPLE: Mapping[str, float] = {
    "none": 0.0,
    "weak": 3.0,
    "moderate": 12.0,
    "strong": 40.0,
}

#: Generic rock and fluid defaults used only when nothing better is supplied.
GENERIC_DEFAULTS: Mapping[str, tuple[float, float, float, str]] = {
    # name: (low, base, high, unit)
    "porosity": (0.15, 0.22, 0.30, "-"),
    "water_saturation": (0.15, 0.25, 0.40, "-"),
    "net_to_gross": (0.55, 0.75, 0.95, "-"),
    "gas_compressibility_factor": (0.85, 0.90, 0.98, "-"),
    "oil_formation_volume_factor": (1.10, 1.25, 1.50, "rm3/Sm3"),
    "water_formation_volume_factor": (1.00, 1.03, 1.06, "rm3/Sm3"),
    "oil_viscosity_cP": (0.3, 1.0, 5.0, "cP"),
    "gas_viscosity_cP": (0.014, 0.020, 0.030, "cP"),
    "rock_compressibility_1_per_bar": (2.0e-5, 4.5e-5, 9.0e-5, "1/bar"),
    "water_compressibility_1_per_bar": (3.5e-5, 4.4e-5, 5.5e-5, "1/bar"),
    "oil_compressibility_1_per_bar": (7.0e-5, 1.45e-4, 3.0e-4, "1/bar"),
    "drainage_radius_m": (300.0, 500.0, 1200.0, "m"),
    "wellbore_radius_m": (0.078, 0.108, 0.156, "m"),
    "skin_factor": (-3.0, 0.0, 5.0, "-"),
    "drawdown_fraction": (0.08, 0.15, 0.30, "-"),
}

#: Weight of each parameter in the completeness score and the refinement ranking.
#: Higher weight means the model result is more sensitive to that parameter.
PARAMETER_WEIGHTS: Mapping[str, float] = {
    "area_km2": 1.0,
    "net_pay_m": 1.0,
    "porosity": 1.0,
    "water_saturation": 1.0,
    "recovery_factor": 1.0,
    "net_to_gross": 0.8,
    "oil_formation_volume_factor": 0.8,
    "gas_compressibility_factor": 0.8,
    "fluid_composition": 0.7,
    "permeability_mD": 0.6,
    "productivity_index_Sm3_per_day_bar": 0.6,
    "aquifer_volume_multiple": 0.6,
    "initial_pressure_bara": 0.5,
    "reservoir_temperature_C": 0.3,
    "rock_compressibility_1_per_bar": 0.2,
}

#: How each parameter is normally obtained; used to write the refinement plan.
ACQUISITION_ROUTE: Mapping[str, str] = {
    "area_km2": "seismic interpretation / structural map and fluid contacts",
    "net_pay_m": "well logs (gamma ray, resistivity, density-neutron) and contacts",
    "porosity": "core plugs and calibrated density/neutron logs",
    "water_saturation": "resistivity logs with an Archie/Waxman-Smits calibration, core Sw",
    "net_to_gross": "log-derived net-reservoir cut-off applied over the gross interval",
    "recovery_factor": "reservoir simulation or analogue field performance",
    "oil_formation_volume_factor": "PVT report (differential liberation plus separator test)",
    "gas_compressibility_factor": "PVT report (constant composition expansion) or EOS model",
    "fluid_composition": "bottom-hole or recombined separator sample compositional analysis",
    "permeability_mD": "core plugs, well test (build-up) or log-derived permeability",
    "productivity_index_Sm3_per_day_bar": "well test (DST) or production-log derived inflow",
    "aquifer_volume_multiple": "regional aquifer mapping and pressure-history material balance",
    "initial_pressure_bara": "RFT/MDT pressure survey or DST initial pressure",
    "reservoir_temperature_C": "bottom-hole temperature survey corrected for circulation",
    "rock_compressibility_1_per_bar": "special core analysis (pore-volume compressibility)",
}


def default_parameter(name: str, reference: str = "") -> Parameter:
    """Return the generic screening default for ``name``."""
    if name not in GENERIC_DEFAULTS:
        raise KeyError(f"no generic default is defined for '{name}'")
    low, base, high, unit = GENERIC_DEFAULTS[name]
    return Parameter(
        name=name,
        value=base,
        unit=unit,
        provenance="default",
        reference=reference or "generic public screening default",
        low=low,
        high=high,
    )
