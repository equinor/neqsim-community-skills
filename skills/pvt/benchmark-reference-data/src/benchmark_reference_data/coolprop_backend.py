"""Optional CoolProp backend for generating reference points.

CoolProp is *not* a hard dependency. Without it the skill still runs on the
offline anchor table in :mod:`benchmark_reference_data.reference_data`; with it,
a benchmark can be built at any state the reference formulation covers.

Install with::

    python -m pip install CoolProp
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence

from .reference_data import ReferencePoint, normalise_fluid

INSTALL_HINT = "install the optional backend with: python -m pip install CoolProp"

#: Skill property name -> (CoolProp output key, SI unit).
PROPERTY_MAP: Dict[str, tuple] = {
    "density": ("D", "kg/m3"),
    "molar_density": ("Dmolar", "mol/m3"),
    "enthalpy": ("Hmass", "J/kg"),
    "entropy": ("Smass", "J/kg/K"),
    "internal_energy": ("Umass", "J/kg"),
    "cp": ("Cpmass", "J/kg/K"),
    "cv": ("Cvmass", "J/kg/K"),
    "speed_of_sound": ("A", "m/s"),
    "viscosity": ("V", "Pa.s"),
    "thermal_conductivity": ("L", "W/m/K"),
    "compressibility_factor": ("Z", "-"),
    "molar_mass": ("M", "kg/mol"),
    "critical_temperature": ("Tcrit", "K"),
    "critical_pressure": ("Pcrit", "Pa"),
    "acentric_factor": ("acentric", "-"),
}

#: Skill fluid name -> CoolProp fluid name.
FLUID_MAP: Dict[str, str] = {
    "water": "Water",
    "co2": "CarbonDioxide",
    "methane": "Methane",
    "ethane": "Ethane",
    "propane": "Propane",
    "nitrogen": "Nitrogen",
    "oxygen": "Oxygen",
    "hydrogen": "Hydrogen",
    "n-butane": "n-Butane",
    "i-butane": "IsoButane",
    "hydrogen sulfide": "HydrogenSulfide",
    "h2s": "HydrogenSulfide",
}


class CoolPropUnavailableError(RuntimeError):
    """Raised when a CoolProp-backed reference is requested without CoolProp."""


class UnsupportedPropertyError(KeyError):
    """Raised when a property has no CoolProp mapping in this skill."""


def _import_coolprop():
    try:
        from CoolProp import CoolProp as _cp  # type: ignore
    except ImportError:
        return None
    return _cp


def is_available() -> bool:
    """True when CoolProp can be imported."""
    return _import_coolprop() is not None


def coolprop_version() -> Optional[str]:
    """CoolProp version string, or None when unavailable."""
    module = _import_coolprop()
    if module is None:
        return None
    try:
        return str(module.get_global_param_string("version"))
    except Exception:  # pragma: no cover - defensive, CoolProp API drift
        return "unknown"


def coolprop_fluid_name(fluid: str) -> str:
    """Map a skill fluid name onto a CoolProp fluid name."""
    key = normalise_fluid(fluid)
    return FLUID_MAP.get(key, fluid)


def supported_properties() -> List[str]:
    """Properties this skill knows how to request from CoolProp."""
    return sorted(PROPERTY_MAP)


def _require_backend():
    module = _import_coolprop()
    if module is None:
        raise CoolPropUnavailableError(
            "CoolProp is not installed — {}. Use the offline anchor table in "
            "benchmark_reference_data.reference_data instead.".format(INSTALL_HINT)
        )
    return module


def reference_point(
    fluid: str,
    property_name: str,
    temperature_K: float,
    pressure_Pa: float,
    backend: str = "HEOS",
    note: str = "",
) -> ReferencePoint:
    """Evaluate one property at (T, P) and wrap it as a :class:`ReferencePoint`."""
    module = _require_backend()
    if property_name not in PROPERTY_MAP:
        raise UnsupportedPropertyError(
            "property '{}' has no CoolProp mapping — supported: {}".format(
                property_name, ", ".join(supported_properties())
            )
        )
    output_key, unit = PROPERTY_MAP[property_name]
    fluid_id = "{}::{}".format(backend, coolprop_fluid_name(fluid))
    value = float(
        module.PropsSI(output_key, "T", temperature_K, "P", pressure_Pa, fluid_id)
    )
    return ReferencePoint(
        fluid=normalise_fluid(fluid),
        property_name=property_name,
        value=value,
        unit=unit,
        source_key="coolprop_heos",
        state={"temperature_K": temperature_K, "pressure_Pa": pressure_Pa},
        note=note or "CoolProp {} backend {}".format(backend, coolprop_version() or ""),
    )


def reference_grid(
    fluid: str,
    property_name: str,
    temperatures_K: Sequence[float],
    pressures_Pa: Sequence[float],
    backend: str = "HEOS",
) -> List[ReferencePoint]:
    """Evaluate a property over the full (T x P) grid.

    Use this to build the three-or-more benchmark points a task report requires.
    """
    points: List[ReferencePoint] = []
    for temperature in temperatures_K:
        for pressure in pressures_Pa:
            points.append(
                reference_point(
                    fluid, property_name, temperature, pressure, backend=backend
                )
            )
    return points


def reference_states(
    fluid: str,
    property_name: str,
    states: Iterable[Dict[str, float]],
    backend: str = "HEOS",
) -> List[ReferencePoint]:
    """Evaluate a property at an explicit list of ``{temperature_K, pressure_Pa}``."""
    return [
        reference_point(
            fluid,
            property_name,
            float(state["temperature_K"]),
            float(state["pressure_Pa"]),
            backend=backend,
        )
        for state in states
    ]
