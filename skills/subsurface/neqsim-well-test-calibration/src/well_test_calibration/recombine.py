"""Recombine a well stream from measured actual separator volumes and convert it to stock tank with NeqSim."""

from __future__ import annotations

from typing import Dict, Iterable, Sequence, Tuple

P_ATM = 1.01325
MOL_PER_SM3 = 42.29    # mol per Sm3 of ideal gas at 15 C, 1.01325 bara


def _flash(fluid, t_c: float, p_barg: float):
    from neqsim import jneqsim
    fluid.setMultiPhaseCheck(True)          # keep free water out of the oil phase
    fluid.setTemperature(t_c + 273.15)
    fluid.setPressure(p_barg + P_ATM)
    jneqsim.thermodynamicoperations.ThermodynamicOperations(fluid).TPflash()
    fluid.initProperties()
    return fluid


def _phase_m3(phase) -> float:
    """Phase volume as mass / density, the same basis as the separator molar volumes (getVolume() may omit the
    volume translation that getDensity() applies, which inflates a liquid volume by 10-20 % with SRK)."""
    return phase.getNumberOfMolesInPhase() * phase.getMolarMass() / phase.getDensity("kg/m3")


def stock_tank_rates(fluid, z: Sequence[float], kg_per_h: float, mol_per_h: float, p_sep_barg: float, t_sep_c: float,
                     train: Iterable[Tuple[float, float]] = ((0.0, 15.0),)) -> Tuple[float, float]:
    """Stock-tank oil and total gas (Sm3/d) of a well stream taken through a separation train.

    The separator oil is re-flashed stage by stage (``train`` = [(p_barg, t_C), ...], last stage = stock tank), as an
    allocation system and a laboratory separator test do. A single flash from test-separator to standard conditions
    over-states the oil by several per cent for a live oil; the stage path closes that gap.
    """
    f = fluid.clone()
    f.setMolarComposition(list(z))
    f.setTotalFlowRate(kg_per_h, "kg/hr")
    _flash(f, t_sep_c, p_sep_barg)
    model_mol_s = f.getTotalNumberOfMoles()
    scale = (mol_per_h / 3600.0) / model_mol_s if model_mol_s > 0 else 1.0
    n = int(f.getNumberOfComponents())
    gas_mol = f.getPhase("gas").getNumberOfMolesInPhase() * scale if f.hasPhaseType("gas") else 0.0
    oil = f
    for p_barg, t_c in train:
        if not oil.hasPhaseType("oil"):
            break
        o = oil.getPhase("oil")
        x = [o.getComponent(i).getx() for i in range(n)]
        nxt = fluid.clone()
        nxt.setMolarComposition(x)
        nxt.setTotalNumberOfMoles(o.getNumberOfMolesInPhase())
        _flash(nxt, t_c, p_barg)
        if nxt.hasPhaseType("gas"):
            gas_mol += nxt.getPhase("gas").getNumberOfMolesInPhase() * scale
        oil = nxt
    oil_sm3d = _phase_m3(oil.getPhase("oil")) * scale * 86400.0 if oil.hasPhaseType("oil") else 0.0   # moles are per second
    return float(oil_sm3d), float(gas_mol / MOL_PER_SM3 * 86400.0)


def recombine_separator_volumes(fluid, p_sep_barg: float, t_oil_c: float, gas_act_m3h: float, oil_act_m3h: float,
                                water_m3h: float = 0.0, t_gas_c: float = None, water_name: str = "water",
                                train: Iterable[Tuple[float, float]] = ((0.0, 15.0),)) -> Dict[str, object]:
    """Well-stream composition and standard rates from measured ACTUAL gas and oil volumes at the test separator.

    ``fluid`` is a NeqSim fluid of the right reservoir/formation (it sets the phase compositions at separator
    conditions; the measured volumes set the proportions). The gas meter is corrected to its own temperature
    ``t_gas_c`` when it differs from the oil temperature. Returns the composition ``z``, mass flow, stock-tank oil and
    gas (Sm3/d), separator gas (Sm3/d, to compare with a flow computer) and shrinkage (stock-tank / separator oil).
    """
    t_gas_c = t_oil_c if t_gas_c is None else t_gas_c
    fl = _flash(fluid.clone(), t_oil_c, p_sep_barg)
    if not (fl.hasPhaseType("gas") and fl.hasPhaseType("oil")):
        raise ValueError("fluid is not two-phase at test-separator conditions: check the fluid or the separator P/T")
    g, o = fl.getPhase("gas"), fl.getPhase("oil")
    n = int(fl.getNumberOfComponents())
    names = [str(fl.getComponent(i).getComponentName()) for i in range(n)]
    vm_g = g.getMolarMass() / g.getDensity("kg/m3") * (t_gas_c + 273.15) / (t_oil_c + 273.15)
    vm_o = o.getMolarMass() / o.getDensity("kg/m3")
    ng, no = gas_act_m3h / vm_g, oil_act_m3h / vm_o
    mol = [ng * g.getComponent(i).getx() + no * o.getComponent(i).getx() for i in range(n)]
    if water_m3h:
        if water_name not in names:
            raise ValueError("water is measured but the fluid has no '{}' component".format(water_name))
        mol[names.index(water_name)] += water_m3h * 1.0e6 / 18.015
    tot = sum(mol)
    z = [m / tot for m in mol]
    kgh = sum(mol[i] * float(fl.getComponent(i).getMolarMass()) for i in range(n))
    oil_sm3d, gas_sm3d = stock_tank_rates(fluid, z, kgh, tot, p_sep_barg, t_oil_c, train)
    return {"z": z, "names": names, "kg_per_h": kgh, "mol_per_h": tot, "oil_Sm3d": oil_sm3d, "gas_Sm3d": gas_sm3d,
            "water_m3d": water_m3h * 24.0, "sep_gas_Sm3d": ng / MOL_PER_SM3 * 24.0,
            "shrinkage": oil_sm3d / (oil_act_m3h * 24.0) if oil_act_m3h else None,
            "rho_oil_sep": float(o.getDensity("kg/m3"))}
