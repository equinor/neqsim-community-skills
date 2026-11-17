"""Reservoir-condition phase densities and viscosities from NeqSim (optional; needs the neqsim package).

Oil and gas come from a flash of the hydrocarbon fluid (``components`` or an E300 file). Water comes from a separate
pure-water CPA flash at the same conditions, because cubic equations without a volume correction underpredict
liquid water density by around 20 %. Brine is denser than pure water; pass ``water`` values to use a brine.
"""

from __future__ import annotations

from typing import Dict, Optional

from .devices import PhaseProperties


def _hydrocarbon_fluid(
    jneqsim,
    components: Optional[Dict[str, float]],
    e300: Optional[str],
    temperature_c: float,
    pressure_bara: float,
    eos: str,
):
    if e300:
        fluid = jneqsim.thermo.util.readwrite.EclipseFluidReadWrite.read(str(e300))
        fluid.setTemperature(temperature_c + 273.15)
        fluid.setPressure(pressure_bara)
        return fluid
    if not components:
        raise ValueError("give components or an e300 file")
    system_class = {
        "SRK": jneqsim.thermo.system.SystemSrkEos,
        "PR": jneqsim.thermo.system.SystemPrEos,
    }[eos.upper()]
    fluid = system_class(temperature_c + 273.15, pressure_bara)
    for name, fraction in components.items():
        if name.lower() != "water":
            fluid.addComponent(name, float(fraction))
    fluid.setMixingRule("classic")
    return fluid


def _pure_water(
    jneqsim, temperature_c: float, pressure_bara: float
) -> Dict[str, float]:
    water = jneqsim.thermo.system.SystemSrkCPAstatoil(
        temperature_c + 273.15, pressure_bara
    )
    water.addComponent("water", 1.0)
    water.setMixingRule(10)
    jneqsim.thermodynamicoperations.ThermodynamicOperations(water).TPflash()
    water.initProperties()
    phase = water.getPhase(0)
    return {
        "water_density": float(phase.getDensity("kg/m3")),
        "water_viscosity": float(phase.getViscosity("cP")),
    }


def phase_properties_from_neqsim(
    components: Optional[Dict[str, float]],
    temperature_c: float,
    pressure_bara: float,
    eos: str = "SRK",
    fallback: Optional[Dict[str, float]] = None,
    e300: Optional[str] = None,
    water: Optional[Dict[str, float]] = None,
) -> Dict[str, object]:
    """Oil, water and gas densities (kg/m3) and viscosities (cP) at device conditions.

    A hydrocarbon phase that does not form (oil above the dew point, gas above the bubble point) takes its value
    from ``fallback`` (keys as ``PhaseProperties`` fields); without a fallback the call fails, so a missing phase
    is never filled silently. ``water`` (``water_density``, ``water_viscosity``) replaces the pure-water flash.

    Returns ``{"properties", "phases", "fallback_used", "source"}``.
    """
    from neqsim import jneqsim  # imported lazily: needs a JVM

    fluid = _hydrocarbon_fluid(
        jneqsim, components, e300, temperature_c, pressure_bara, eos
    )
    fluid.setMultiPhaseCheck(True)
    jneqsim.thermodynamicoperations.ThermodynamicOperations(fluid).TPflash()
    fluid.initProperties()
    values: Dict[str, float] = {}
    found = []
    for key in ("oil", "gas"):
        if fluid.hasPhaseType(key):
            phase = fluid.getPhase(key)
            values[f"{key}_density"] = float(phase.getDensity("kg/m3"))
            values[f"{key}_viscosity"] = float(phase.getViscosity("cP"))
            found.append(key)
    absent = [k for k in ("oil", "gas") if k not in found]
    for key in absent:
        for prop in ("density", "viscosity"):
            name = f"{key}_{prop}"
            if not fallback or name not in fallback:
                raise ValueError(
                    f"no {key} phase at {temperature_c} C and {pressure_bara} bara; give fallback "
                    f"'{name}'"
                )
            values[name] = float(fallback[name])
    if water:
        values.update(
            {k: float(water[k]) for k in ("water_density", "water_viscosity")}
        )
        water_source = "user input"
    else:
        values.update(_pure_water(jneqsim, temperature_c, pressure_bara))
        water_source = "NeqSim CPA pure water (no salinity)"
    return {
        "properties": PhaseProperties(**values),
        "phases": found,
        "fallback_used": absent,
        "source": {
            "hydrocarbon": (
                f"E300 file {e300}" if e300 else f"{eos.upper()} composition"
            ),
            "water": water_source,
            "temperature_c": temperature_c,
            "pressure_bara": pressure_bara,
            "method": "NeqSim TPflash with multiphase check; initProperties",
        },
    }
