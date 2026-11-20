"""Release-source helpers: gas properties, rated relief capacity and optional PSV sizing.

The dispersion study needs a release mass flow per case. Typical sources are

* the rated capacity of the installed pressure-safety valve (PSV) orifice, which is
  the conservative unignited-release rate for a single-valve lift,
* the peak flow of an emergency depressurisation (blowdown), and
* the combined rated capacity of several valves that open together.

The functions here turn a composition into the gas properties the plume model needs
(molar mass, fuel fraction, LFL on a fuel basis), compute the rated flow of a chosen
orifice with the public API 520 critical-flow equation, and, only if NeqSim is
importable, size a gas PSV with ``neqsim.process.util.fire.ReliefValveSizing``. Without
NeqSim every function except :func:`size_psv_api520_gas` still works and the sizing
helper reports that it is unavailable; supply the rated mass flow directly instead.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from .model import R_GAS, ReleaseCase

FUEL_LFL_VOL_FRAC: dict[str, float] = {
    "methane": 0.050,
    "ethane": 0.030,
    "propane": 0.021,
    "n-butane": 0.018,
    "i-butane": 0.018,
    "n-pentane": 0.014,
    "i-pentane": 0.014,
    "n-hexane": 0.012,
    "hydrogen": 0.040,
    "ethylene": 0.027,
    "propylene": 0.020,
    "H2S": 0.043,
}
"""Typical literature lower flammability limits in air (volume fraction, near 20-25 C).

Replace them with the limits in the project gas-safety data when these differ."""

INERT_COMPONENTS = ("nitrogen", "CO2", "water")
"""Components that do not contribute to the fuel fraction."""

MOLAR_MASS_KG_MOL: dict[str, float] = {
    "methane": 0.016043,
    "ethane": 0.030070,
    "propane": 0.044097,
    "n-butane": 0.058123,
    "i-butane": 0.058123,
    "n-pentane": 0.072150,
    "i-pentane": 0.072150,
    "n-hexane": 0.086177,
    "hydrogen": 0.002016,
    "ethylene": 0.028054,
    "propylene": 0.042081,
    "H2S": 0.034081,
    "nitrogen": 0.028013,
    "CO2": 0.044010,
    "water": 0.018015,
}
"""Molar masses of the supported components, kg/mol."""

STANDARD_ORIFICES_IN2: dict[str, float] = {
    "D": 0.110,
    "E": 0.196,
    "F": 0.307,
    "G": 0.503,
    "H": 0.785,
    "J": 1.287,
    "K": 1.838,
    "L": 2.853,
    "M": 3.600,
    "N": 4.340,
    "P": 6.380,
    "Q": 11.050,
    "R": 16.000,
    "T": 26.000,
}
"""API 526 standard effective orifice areas, square inches."""

IN2_TO_M2 = 6.4516e-4
ATM_PA = 101325.0


class NeqSimUnavailableError(RuntimeError):
    """Raised when NeqSim-backed sizing is requested but NeqSim cannot be used."""


def composition_to_release_properties(
    composition: Mapping[str, float],
) -> dict[str, Any]:
    """Derive the plume-model gas properties from a mole-fraction composition.

    The LFL of the fuel part is the Le Chatelier mixture limit over the combustible
    components; inerts (nitrogen, CO2, water) only dilute the gas and reduce
    ``fuel_mole_frac``.

    Args:
        composition: Mole fractions (or amounts) by component name from
            :data:`MOLAR_MASS_KG_MOL`; normalised internally.

    Returns:
        Dictionary with ``mw_kg_mol``, ``fuel_mole_frac`` and ``lfl_vol_frac`` (fuel
        basis), ready for :class:`flare_helideck_dispersion.model.ReleaseCase`.

    Raises:
        ValueError: If a component is unknown, an amount is negative or no combustible
            component is present.
    """
    total = float(sum(composition.values()))
    if total <= 0.0 or any(v < 0.0 for v in composition.values()):
        raise ValueError("composition amounts must be non-negative with a positive sum")
    unknown = [c for c in composition if c not in MOLAR_MASS_KG_MOL]
    if unknown:
        raise ValueError(
            f"unknown components {unknown}; supported: {sorted(MOLAR_MASS_KG_MOL)}"
        )
    x = {c: v / total for c, v in composition.items()}
    mw = sum(x[c] * MOLAR_MASS_KG_MOL[c] for c in x)
    fuel = {c: v for c, v in x.items() if c in FUEL_LFL_VOL_FRAC and v > 0.0}
    fuel_total = sum(fuel.values())
    if fuel_total <= 0.0:
        raise ValueError("composition has no combustible component")
    lfl = 1.0 / sum((v / fuel_total) / FUEL_LFL_VOL_FRAC[c] for c, v in fuel.items())
    return {
        "mw_kg_mol": mw,
        "fuel_mole_frac": min(fuel_total, 1.0),
        "lfl_vol_frac": lfl,
    }


def release_case_from_composition(
    name: str,
    mass_flow_kg_s: float,
    composition: Mapping[str, float],
    gamma: float,
    t0_k: float,
    **kwargs: Any,
) -> ReleaseCase:
    """Build a :class:`ReleaseCase` from a composition and a mass flow.

    Args:
        name: Case name.
        mass_flow_kg_s: Release mass flow, kg/s.
        composition: Mole fractions by component name.
        gamma: Heat-capacity ratio Cp/Cv.
        t0_k: Stagnation temperature at the tip, K.
        **kwargs: Other :class:`ReleaseCase` fields (for example ``tip_diameter_m``).

    Returns:
        The release case.
    """
    props = composition_to_release_properties(composition)
    return ReleaseCase(
        name=name,
        mass_flow_kg_s=mass_flow_kg_s,
        gamma=gamma,
        t0_k=t0_k,
        **props,
        **kwargs,
    )


def relieving_pressure_pa(
    set_pressure_barg: float, overpressure_fraction: float
) -> float:
    """Absolute relieving pressure from a gauge set pressure.

    The overpressure is a fraction of the gauge set pressure (0.10 for a single-valve
    process case, 0.21 for fire), added to the absolute set pressure.

    Args:
        set_pressure_barg: Set pressure, bar gauge.
        overpressure_fraction: Fraction of the gauge set pressure.

    Returns:
        Relieving pressure, Pa absolute.
    """
    set_gauge_pa = set_pressure_barg * 1e5
    return (set_gauge_pa + ATM_PA) + set_gauge_pa * overpressure_fraction


def api520_rated_mass_flow_kg_s(
    area_m2: float,
    set_pressure_barg: float,
    overpressure_fraction: float,
    temperature_k: float,
    mw_kg_mol: float,
    compressibility: float,
    gamma: float,
    discharge_coefficient: float = 0.975,
) -> float:
    """Rated gas mass flow of an orifice at critical (choked) flow, API 520 form.

    ``W = Kd A P1 sqrt(k M / (Z R T)) (2 / (k + 1))^((k + 1) / (2 (k - 1)))`` with
    ``Kb = Kc = 1``. It is valid when the back pressure is below the critical pressure.

    Args:
        area_m2: Effective orifice area, m2.
        set_pressure_barg: Set pressure, bar gauge.
        overpressure_fraction: Fraction of the gauge set pressure.
        temperature_k: Relieving temperature, K.
        mw_kg_mol: Molar mass, kg/mol.
        compressibility: Compressibility factor Z at relieving conditions.
        gamma: Heat-capacity ratio Cp/Cv.
        discharge_coefficient: ``Kd``, 0.975 for gas service.

    Returns:
        Rated mass flow, kg/s.

    Raises:
        ValueError: If an input is non-physical.
    """
    if min(area_m2, temperature_k, mw_kg_mol, compressibility) <= 0.0 or gamma <= 1.0:
        raise ValueError(
            "area, temperature, molar mass, Z must be positive and gamma > 1"
        )
    p1 = relieving_pressure_pa(set_pressure_barg, overpressure_fraction)
    c = math.sqrt(gamma) * (2.0 / (gamma + 1.0)) ** (
        (gamma + 1.0) / (2.0 * (gamma - 1.0))
    )
    return (
        discharge_coefficient
        * area_m2
        * p1
        * c
        * math.sqrt(mw_kg_mol / (compressibility * R_GAS * temperature_k))
    )


def neqsim_available() -> bool:
    """Return whether NeqSim and its relief-valve sizing class can be used.

    Returns:
        ``True`` if ``neqsim`` imports and
        ``neqsim.process.util.fire.ReliefValveSizing`` is reachable.
    """
    try:
        from neqsim import jneqsim

        return jneqsim.process.util.fire.ReliefValveSizing is not None
    except Exception:  # noqa: BLE001 - any import or JVM failure means unavailable
        return False


def size_psv_api520_gas(
    mass_flow_kg_s: float,
    set_pressure_barg: float,
    temperature_k: float,
    mw_kg_mol: float,
    compressibility: float,
    gamma: float,
    overpressure_fraction: float = 0.10,
    back_pressure_barg: float = 0.0,
    required: bool = False,
) -> dict[str, Any] | None:
    """Size a gas PSV with NeqSim ``ReliefValveSizing`` (API 520 Part I, API 526 letters).

    Skips gracefully when NeqSim is not importable: with ``required=False`` the
    function returns ``None`` and the caller supplies a rated mass flow instead.

    Args:
        mass_flow_kg_s: Required relieving rate, kg/s.
        set_pressure_barg: Set pressure, bar gauge.
        temperature_k: Relieving temperature, K.
        mw_kg_mol: Molar mass, kg/mol.
        compressibility: Compressibility factor Z at relieving conditions.
        gamma: Heat-capacity ratio Cp/Cv.
        overpressure_fraction: Fraction of the gauge set pressure.
        back_pressure_barg: Back pressure, bar gauge.
        required: Raise instead of returning ``None`` when NeqSim is unavailable.

    Returns:
        Dictionary with the required area, the selected API 526 orifice letter and
        area, and the rated mass flow of the selected orifice, or ``None``.

    Raises:
        NeqSimUnavailableError: If NeqSim is unavailable and ``required`` is true.
    """
    if not neqsim_available():
        if required:
            raise NeqSimUnavailableError(
                "NeqSim is not importable; install the 'neqsim' package or supply a "
                "rated mass flow"
            )
        return None
    from neqsim import jneqsim

    sizing = jneqsim.process.util.fire.ReliefValveSizing
    set_pa = set_pressure_barg * 1e5 + ATM_PA
    back_pa = back_pressure_barg * 1e5 + ATM_PA
    res = sizing.calculateRequiredArea(
        float(mass_flow_kg_s),
        float(set_pa),
        float(overpressure_fraction),
        float(back_pa),
        float(temperature_k),
        float(mw_kg_mol),
        float(compressibility),
        float(gamma),
        False,
        False,
    )
    selected_m2 = float(res.getSelectedAreaIn2()) * IN2_TO_M2
    rated_neqsim = float(
        sizing.calculateMassFlowCapacity(
            selected_m2,
            float(set_pa),
            float(overpressure_fraction),
            float(back_pa),
            float(temperature_k),
            float(mw_kg_mol),
            float(compressibility),
            float(gamma),
            0.975,
        )
    )
    rated = api520_rated_mass_flow_kg_s(
        selected_m2,
        set_pressure_barg,
        overpressure_fraction,
        temperature_k,
        mw_kg_mol,
        compressibility,
        gamma,
    )
    agrees = abs(rated_neqsim - rated) <= 0.01 * rated
    warnings = []
    if not agrees:
        warnings.append(
            f"NeqSim calculateMassFlowCapacity gives {rated_neqsim:.4g} kg/s against {rated:.4g} kg/s from the "
            "API 520 critical-flow equation; the NeqSim build may predate the kg/mol "
            "capacity correction. The API 520 equation value is reported as the rated flow."
        )
    return {
        "required_area_in2": float(res.getRequiredAreaIn2()),
        "required_area_cm2": float(res.getRequiredAreaIn2()) * 6.4516,
        "api526_orifice_letter": str(res.getRecommendedOrifice()),
        "selected_area_in2": float(res.getSelectedAreaIn2()),
        "rated_mass_flow_kg_s": rated,
        "rated_mass_flow_neqsim_kg_s": rated_neqsim,
        "rated_flow_agrees_with_neqsim": agrees,
        "warnings": warnings,
        "relieving_pressure_pa": relieving_pressure_pa(
            set_pressure_barg, overpressure_fraction
        ),
        "basis": "orifice from neqsim ReliefValveSizing (API 520 gas, Kd 0.975, Kb 1, Kc 1); "
        "rated flow from the API 520 critical-flow equation",
    }
