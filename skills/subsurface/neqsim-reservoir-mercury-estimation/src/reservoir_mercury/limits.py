"""Mineral-equilibrium limits of mercury in a reservoir fluid, calculated with NeqSim.

Thin wrapper around the Java classes ``neqsim.thermo.util.mineral.ReservoirMercuryEstimator`` (cinnabar with the
pyrite and Fe-carbonate H2S buffer, and liquid mercury) and ``neqsim.thermo.util.mercury.MercuryPhaseEquilibrium``
(partitioning to separator gas). The limits are upper bounds, never predictions.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

#: Mole fraction to microgram per Sm3 of ideal gas at 15 C and 1.01325 bara (200.59 g/mol x 42.2926 mol/Sm3).
UG_PER_SM3_PER_MOLE_FRACTION = 8.4834e9

#: Declared generic reservoir-fluid compositions (mol %) used when no composition is given.
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
C7_PLUS = {
    "gas": (0.160, 0.80),
    "oil": (0.220, 0.85),
}  # molar mass kg/mol, density g/cm3


class MercuryLimitUnavailable(RuntimeError):
    """Raised when the NeqSim classes for the mercury limits cannot be loaded."""


def default_jclass() -> Callable[[str], Any]:
    """Return a function that loads a NeqSim Java class by name through the installed ``neqsim`` package.

    Returns:
        ``jpype.JClass`` after the NeqSim JVM is started.

    Raises:
        MercuryLimitUnavailable: If ``neqsim`` or ``jpype`` is not installed.
    """
    try:
        import jpype
        import neqsim  # noqa: F401  (starts the JVM)
    except Exception as exc:
        raise MercuryLimitUnavailable(
            f"the neqsim Python package is needed for mercury limits: {exc}"
        ) from exc
    return jpype.JClass


def mercury_limits(
    temperature_c: float,
    pressure_bara: float,
    fluid_type: str = "gas",
    co2_molpct: float = 2.0,
    composition: Mapping[str, float] | None = None,
    c7_plus: tuple[float, float] | None = None,
    separator_t_c: float = 40.0,
    separator_p_bara: float = 20.0,
    trace_activity: float = 0.003,
    jclass: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Calculate the mercury limits of a reservoir fluid and express them in separator gas.

    Args:
        temperature_c: Reservoir temperature [C].
        pressure_bara: Reservoir pressure [bara].
        fluid_type: ``"gas"`` (gas or gas condensate) or ``"oil"``; selects the generic composition.
        co2_molpct: CO2 content of the reservoir fluid [mol %]; controls the buffered H2S.
        composition: Reservoir-fluid composition in mol % by NeqSim component name, with ``"C7+"`` for the heavy end
            and without CO2 (CO2 comes from ``co2_molpct``). Default: a declared generic composition.
        c7_plus: Molar mass [kg/mol] and density [g/cm3] of the C7+ fraction.
        separator_t_c: Temperature of the test separator [C].
        separator_p_bara: Pressure of the test separator [bara].
        trace_activity: HgS activity of the trace-sulfide limit (0.003 matched global data in Bryndzia et al. 2022).
        jclass: Function that loads a Java class by name; default uses the installed ``neqsim`` package.

    Returns:
        Limits in microgram per Sm3 of separator gas (``cinnabar_limit``, ``trace_sulfide_limit``, ``liquid_limit``),
        the buffered H2S, the mercury fugacity coefficient, the basis and the warnings of the Java estimator.

    Raises:
        MercuryLimitUnavailable: If the NeqSim version in use does not contain ``ReservoirMercuryEstimator``.
        ValueError: If temperature, pressure or CO2 are not positive.
    """
    if not (temperature_c > -50.0 and pressure_bara > 0.0 and co2_molpct > 0.0):
        raise ValueError("temperature, pressure and CO2 content must be positive")
    load = jclass or default_jclass()
    try:
        estimator_cls = load("neqsim.thermo.util.mineral.ReservoirMercuryEstimator")
        srk_cls = load("neqsim.thermo.system.SystemSrkEos")
        converter = load("neqsim.thermo.util.mercury.MercuryFluidConverter")
        phase_eq = load("neqsim.thermo.util.mercury.MercuryPhaseEquilibrium")
    except Exception as exc:
        raise MercuryLimitUnavailable(
            "this NeqSim version has no ReservoirMercuryEstimator (added with the reservoir mercury mineral buffers); "
            f"update NeqSim or pass limits calculated elsewhere: {str(exc)[:120]}"
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
    work = converter.toUmrPruMc(fluid, 1.0, "ug/Sm3")
    estimate = estimator_cls().estimate(work)
    z_sulfide = float(estimate.getSulfideLimitMoleFraction())
    z_liquid = float(estimate.getLiquidLimitMoleFraction())
    basis = f"flash to {separator_t_c:.0f} C and {separator_p_bara:.0f} bara"
    try:
        ref = estimate.getFluid()
        hg = ref.getComponent("mercury").getNumberOfmoles()
        other = ref.getTotalNumberOfMoles() - hg
        ref.addComponent("mercury", 1.0e-9 * other - hg)
        ref.setTemperature(273.15 + float(separator_t_c))
        ref.setPressure(float(separator_p_bara))
        eq = phase_eq(ref)
        eq.run()
        if not str(eq.getFluid().getPhase(0).getType()).lower().startswith("gas"):
            raise RuntimeError("no gas phase at separator conditions")
        per_z = float(eq.getMercuryConcentration(0, "ug/Sm3")) / 1.0e-9
    except Exception as exc:  # noqa: BLE001
        per_z = UG_PER_SM3_PER_MOLE_FRACTION
        basis = (
            f"all mercury taken to the gas (separator flash failed: {str(exc)[:60]})"
        )
    return {
        "cinnabar_limit": z_sulfide * per_z,
        "trace_sulfide_limit": trace_activity * z_sulfide * per_z,
        "liquid_limit": z_liquid * per_z,
        "trace_activity": trace_activity,
        "reservoir_fluid_cinnabar_limit_mole_fraction": z_sulfide,
        "reservoir_fluid_liquid_limit_mole_fraction": z_liquid,
        "buffered_h2s_ppm": float(estimate.getH2SPpm()),
        "mercury_fugacity_coefficient": float(estimate.getMercuryFugacityCoefficient()),
        "log10_uncertainty_thermochemistry": float(
            estimate.getSulfideLimitLog10Uncertainty()
        ),
        "unit": "microgram per Sm3 of separator gas",
        "separator_basis": basis,
        "fluid_basis": (
            "given composition"
            if composition
            else f"generic {kind} composition (declared)"
        ),
        "equation_of_state": "UMR-PRU-MC",
        "warnings": [str(w) for w in estimate.getWarnings()],
    }
