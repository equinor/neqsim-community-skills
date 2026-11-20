"""Mineral-buffered H2S of a reservoir fluid, calculated with NeqSim and expressed in separator gas.

Thin wrapper around the Java class ``neqsim.thermo.util.mineral.ReservoirH2SEstimator``: pyrite and an Fe-bearing
carbonate fix the H2S fugacity through ``4 FeS2 + CH4 + 3 CO2 + 6 H2O = 4 FeCO3 + 8 H2S``. The reservoir fluid with
the buffered H2S is then flashed to test-separator conditions, because H2S is measured in separator gas.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from typing import Any

#: Declared generic reservoir-fluid compositions (mol %, without CO2) used when no composition is given.
GENERIC_COMPOSITION: dict[str, dict[str, float]] = {
    "gas": {
        "nitrogen": 1.0,
        "methane": 80.0,
        "ethane": 7.5,
        "propane": 4.0,
        "n-butane": 1.5,
        "n-pentane": 0.6,
        "n-hexane": 0.4,
        "C7+": 3.0,
    },
    "oil": {
        "nitrogen": 0.5,
        "methane": 45.0,
        "ethane": 7.0,
        "propane": 6.0,
        "n-butane": 3.0,
        "n-pentane": 1.25,
        "n-hexane": 0.75,
        "C7+": 34.5,
    },
}
#: Molar mass [kg/mol] and density [g/cm3] of the C7+ fraction of the generic compositions.
C7_PLUS = {"gas": (0.160, 0.80), "oil": (0.220, 0.85)}

#: H2S partial pressure above which ISO 15156-2 defines sour service [kPa].
SOUR_SERVICE_KPA = 0.3

#: Milligram H2S per normal cubic metre (0 C, 1.01325 bara) for one ppm by mole.
MG_PER_NM3_PER_PPM = 34.08 / 22.414


class H2SBufferUnavailable(RuntimeError):
    """Raised when the NeqSim class for the H2S buffer cannot be loaded."""


def default_jclass() -> Callable[[str], Any]:
    """Return a function that loads a NeqSim Java class by name through the installed ``neqsim`` package.

    Returns:
        ``jpype.JClass`` after the NeqSim JVM is started.

    Raises:
        H2SBufferUnavailable: If ``neqsim`` or ``jpype`` is not installed.
    """
    try:
        import jpype
        import neqsim  # noqa: F401  (starts the JVM)
    except Exception as exc:
        raise H2SBufferUnavailable(
            f"the neqsim Python package is needed for the H2S buffer: {exc}"
        ) from exc
    return jpype.JClass


def haaland_ppm(temperature_c: float) -> float:
    """H2S in reservoir fluid from the temperature correlation of Håland et al. (1999) for the Norwegian shelf.

    Args:
        temperature_c: Reservoir temperature [C].

    Returns:
        H2S [ppm by mole].
    """
    return math.exp(17.575 - 6478.4 / (temperature_c + 273.15))


def correlation_buffer(
    temperature_c: float,
    pressure_bara: float = 0.0,
    co2_molpct: float = 0.0,
    fluid_type: str = "gas",
) -> dict[str, Any]:
    """Stand-in for :func:`buffered_h2s` that uses the temperature correlation only (no NeqSim needed).

    Args:
        temperature_c: Reservoir temperature [C].
        pressure_bara: Reservoir pressure [bara]; not used by the correlation.
        co2_molpct: CO2 content [mol %]; not used by the correlation.
        fluid_type: ``"gas"`` or ``"oil"``; not used by the correlation.

    Returns:
        Record with the same keys as :func:`buffered_h2s`; reservoir fluid and separator gas carry the same value.
    """
    value = haaland_ppm(float(temperature_c))
    kind = "oil" if str(fluid_type).lower().startswith("oil") else "gas"
    return {
        "reservoir_fluid_ppm": value,
        "separator_gas_ppm": value,
        "h2s_fugacity_bar": value * 1.0e-6 * float(pressure_bara),
        "siderite_margin_log10": float("nan"),
        "pyrite_margin_log10": float("nan"),
        "fe_carbonate_activity": float("nan"),
        "haaland_ppm": value,
        "unit": "ppm by mole",
        "separator_basis": "temperature correlation, no flash",
        "fluid_basis": "not used by the correlation",
        "fluid_type": kind,
        "equation_of_state": "none (temperature correlation of Håland et al. 1999)",
        "warnings": [],
    }


def buffered_h2s(
    temperature_c: float,
    pressure_bara: float,
    co2_molpct: float,
    fluid_type: str = "gas",
    composition: Mapping[str, float] | None = None,
    c7_plus: tuple[float, float] | None = None,
    separator_t_c: float = 40.0,
    separator_p_bara: float = 40.0,
    fe_carbonate_activity: float | None = None,
    water_activity: float | None = None,
    jclass: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Calculate the mineral-buffered H2S of a reservoir fluid and the H2S of its separator gas.

    Args:
        temperature_c: Reservoir temperature [C].
        pressure_bara: Reservoir pressure [bara].
        co2_molpct: CO2 content of the reservoir fluid [mol %].
        fluid_type: ``"gas"`` (gas or gas condensate) or ``"oil"``; selects the generic composition.
        composition: Reservoir-fluid composition in mol % by NeqSim component name, with ``"C7+"`` for the heavy end
            and without CO2 (CO2 comes from ``co2_molpct``). Default: a declared generic composition.
        c7_plus: Molar mass [kg/mol] and density [g/cm3] of the C7+ fraction.
        separator_t_c: Temperature of the test separator [C].
        separator_p_bara: Pressure of the test separator [bara].
        fe_carbonate_activity: Activity of FeCO3 in the carbonate; default is the value of the Java class.
        water_activity: Activity of the formation water; default 1.
        jclass: Function that loads a Java class by name; default uses the installed ``neqsim`` package.

    Returns:
        ``reservoir_fluid_ppm`` and ``separator_gas_ppm`` [ppm by mole], the H2S fugacity [bar], the stability margins
        of siderite and pyrite [log10 units], the Haaland value, the basis texts and the warnings of the estimator.

    Raises:
        H2SBufferUnavailable: If the NeqSim version in use does not contain ``ReservoirH2SEstimator``.
        ValueError: If temperature, pressure or CO2 are not positive.
    """
    if not (temperature_c > -50.0 and pressure_bara > 0.0 and co2_molpct > 0.0):
        raise ValueError("temperature, pressure and CO2 content must be positive")
    load = jclass or default_jclass()
    try:
        estimator_cls = load("neqsim.thermo.util.mineral.ReservoirH2SEstimator")
        srk_cls = load("neqsim.thermo.system.SystemSrkEos")
        ops_cls = load("neqsim.thermodynamicoperations.ThermodynamicOperations")
    except Exception as exc:
        raise H2SBufferUnavailable(
            "this NeqSim version has no ReservoirH2SEstimator (added in 3.29); update NeqSim or pass a buffer "
            f"calculated elsewhere: {str(exc)[:120]}"
        ) from exc
    kind = "oil" if str(fluid_type).lower().startswith("oil") else "gas"
    comp = dict(composition or GENERIC_COMPOSITION[kind])
    mw, rho = c7_plus or C7_PLUS[kind]
    fluid = srk_cls(273.15 + float(temperature_c), float(pressure_bara))
    fluid.addComponent("CO2", float(co2_molpct))
    for name, amount in comp.items():
        if amount <= 0.0 or name == "CO2":
            continue
        if name == "C7+":
            fluid.addTBPfraction("C7", float(amount), float(mw), float(rho))
        else:
            fluid.addComponent(name, float(amount))
    fluid.setMixingRule("classic")
    estimator = estimator_cls()
    if fe_carbonate_activity is not None:
        estimator.setFeCarbonateActivity(float(fe_carbonate_activity))
    if water_activity is not None:
        estimator.setWaterActivity(float(water_activity))
    estimate = estimator.estimate(fluid)
    reservoir_ppm = float(estimate.getH2SPpm())
    basis = f"flash to {separator_t_c:.0f} C and {separator_p_bara:.0f} bara"
    separator_ppm = reservoir_ppm
    try:
        sep = estimate.getFluid().clone()
        sep.setTemperature(273.15 + float(separator_t_c))
        sep.setPressure(float(separator_p_bara))
        ops_cls(sep).TPflash()
        if not sep.hasPhaseType("gas"):
            raise RuntimeError("no gas phase at separator conditions")
        gas = sep.getPhase("gas")
        separator_ppm = 1.0e6 * float(gas.getComponent("H2S").getx())
    except Exception as exc:  # noqa: BLE001
        basis = f"reservoir-fluid value used (separator flash failed: {str(exc)[:60]})"
    return {
        "reservoir_fluid_ppm": reservoir_ppm,
        "separator_gas_ppm": separator_ppm,
        "h2s_fugacity_bar": float(estimate.getH2SFugacity()),
        "siderite_margin_log10": float(estimate.getSideriteStabilityMargin()),
        "pyrite_margin_log10": float(estimate.getPyriteStabilityMargin()),
        "fe_carbonate_activity": float(estimate.getFeCarbonateActivity()),
        "haaland_ppm": haaland_ppm(float(temperature_c)),
        "unit": "ppm by mole",
        "separator_basis": basis,
        "fluid_basis": (
            "given composition"
            if composition
            else f"generic {kind} composition (declared)"
        ),
        "fluid_type": kind,
        "equation_of_state": "SRK",
        "warnings": [str(w) for w in estimate.getWarnings()],
    }
