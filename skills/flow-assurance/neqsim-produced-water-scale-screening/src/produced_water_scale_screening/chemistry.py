"""Public, deterministic brine chemistry helpers for produced-water screening.

All correlations and constants in this module are taken from the open
literature and are used only for screening-level orientation. They are not a
replacement for a validated electrolyte equation of state such as the NeqSim
``SystemElectrolyteCPAstatoil`` model or the rigorous
``ThermodynamicOperations.checkScalePotential`` routine.
"""

from __future__ import annotations

from math import sqrt

# ---------------------------------------------------------------------------
# Ion property tables (public values)
# ---------------------------------------------------------------------------

#: Ion molar masses in g/mol.
ION_MOLAR_MASS: dict[str, float] = {
    "Na+": 22.99,
    "K+": 39.10,
    "Ca++": 40.08,
    "Mg++": 24.31,
    "Ba++": 137.33,
    "Sr++": 87.62,
    "Fe++": 55.85,
    "Cl-": 35.45,
    "SO4--": 96.07,
    "HCO3-": 61.02,
    "CO3--": 60.01,
}

#: Ion charge numbers (signed).
ION_CHARGE: dict[str, int] = {
    "Na+": 1,
    "K+": 1,
    "Ca++": 2,
    "Mg++": 2,
    "Ba++": 2,
    "Sr++": 2,
    "Fe++": 2,
    "Cl-": -1,
    "SO4--": -2,
    "HCO3-": -1,
    "CO3--": -2,
}

#: Ion names accepted directly by the NeqSim ``ProducedWaterFluidBuilder``
#: ``createFromIons`` factory. Other ions (Ba++, Sr++, Fe++, CO3--, K+) are
#: still screened here but flagged because the basic NeqSim builder presets do
#: not add them automatically.
NEQSIM_BUILDER_IONS: frozenset[str] = frozenset(
    {"Na+", "Cl-", "Ca++", "Mg++", "SO4--", "HCO3-"}
)

#: Debye-Huckel constant A at 25 degC (log10 base), water.
DAVIES_A: float = 0.509

#: Second dissociation constant of carbonic acid at 25 degC (mol/L).
K2_CARBONIC: float = 4.69e-11

#: Solubility products (mol^2/L^2) at 25 degC from the open literature.
KSP_25C: dict[str, float] = {
    "BaSO4": 1.08e-10,
    "SrSO4": 3.44e-7,
    "CaSO4": 3.14e-5,
    "CaCO3": 3.36e-9,
}

#: Cation and anion that form each screened scale.
SCALE_IONS: dict[str, tuple[str, str]] = {
    "BaSO4": ("Ba++", "SO4--"),
    "SrSO4": ("Sr++", "SO4--"),
    "CaSO4": ("Ca++", "SO4--"),
    "CaCO3": ("Ca++", "CO3--"),
}


def molality_map(ions_mg_l: dict[str, float]) -> dict[str, float]:
    """Convert ion concentrations in mg/L to approximate molality (mol/kg).

    A dilute approximation (1 L of solution ~ 1 kg of water) is used, which is
    adequate for screening but degrades at very high total dissolved solids.

    Args:
        ions_mg_l: Mapping of ion name to concentration in mg/L.

    Returns:
        Mapping of ion name to molality in mol/kg.
    """
    molality: dict[str, float] = {}
    for name, mg_l in ions_mg_l.items():
        mw = ION_MOLAR_MASS.get(name)
        if mw is None or mg_l <= 0.0:
            continue
        molality[name] = (mg_l / 1000.0) / mw
    return molality


def ionic_strength(molality: dict[str, float]) -> float:
    """Compute the molal ionic strength of the brine.

    Args:
        molality: Mapping of ion name to molality in mol/kg.

    Returns:
        Ionic strength in mol/kg.
    """
    total = 0.0
    for name, m in molality.items():
        z = ION_CHARGE.get(name)
        if z is None:
            continue
        total += m * z * z
    return 0.5 * total


def davies_activity_coefficient(charge: int, ionic_strength_value: float) -> float:
    """Activity coefficient from the Davies equation.

    Args:
        charge: Signed ion charge number.
        ionic_strength_value: Ionic strength in mol/kg.

    Returns:
        Molal activity coefficient (dimensionless).
    """
    if ionic_strength_value <= 0.0:
        return 1.0
    sqrt_i = sqrt(ionic_strength_value)
    z2 = float(charge * charge)
    log_gamma = -DAVIES_A * z2 * (sqrt_i / (1.0 + sqrt_i) - 0.3 * ionic_strength_value)
    return float(10.0 ** log_gamma)


def charge_balance_error_pct(molality: dict[str, float]) -> float:
    """Relative charge-balance error of the ion list as a percentage.

    Args:
        molality: Mapping of ion name to molality in mol/kg.

    Returns:
        Charge imbalance as a percentage of the total ionic charge. Returns
        0.0 when no charged species are present.
    """
    cation_eq = 0.0
    anion_eq = 0.0
    for name, m in molality.items():
        z = ION_CHARGE.get(name)
        if z is None:
            continue
        if z > 0:
            cation_eq += m * z
        else:
            anion_eq += m * (-z)
    total = cation_eq + anion_eq
    if total <= 0.0:
        return 0.0
    return 100.0 * (cation_eq - anion_eq) / total
