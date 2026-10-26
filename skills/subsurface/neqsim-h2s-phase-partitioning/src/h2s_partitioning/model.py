"""H2S phase partitioning and separator-gas to wellstream conversion with NeqSim.

Physical partitioning only (SRK-CPA, gas / oil / aqueous). Aqueous ionisation of H2S
(HS-, S2-) and iron-sulphide scavenging are not modelled and are reported as limits.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

H2S_MOLAR_MASS_G_MOL = 34.081
WATER_MOLAR_MASS_G_MOL = 18.015
WATER_DENSITY_KG_M3 = 998.0

DEFAULT_COMPOSITION: Dict[str, float] = {
    "nitrogen": 0.004,
    "CO2": 0.020,
    "methane": 0.560,
    "ethane": 0.070,
    "propane": 0.060,
    "i-butane": 0.010,
    "n-butane": 0.025,
    "i-pentane": 0.010,
    "n-pentane": 0.015,
    "n-hexane": 0.026,
    "nC10": 0.200,
}


@dataclass(frozen=True)
class SeparatorStage:
    """One isothermal flash stage of a separation train."""

    temperature_c: float
    pressure_bara: float
    name: str = ""


@dataclass
class StageResult:
    """H2S distribution leaving one separator stage."""

    name: str
    temperature_c: float
    pressure_bara: float
    gas_h2s_ppmv: float
    gas_h2s_mol_s: float
    oil_h2s_ppmw: float
    oil_h2s_mol_s: float
    water_h2s_ppmw: float
    water_h2s_mg_per_l: float
    water_h2s_mol_s: float
    gas_pressure_h2s_kpa: float


@dataclass
class TrainResult:
    """H2S mass balance of a separator train fed with a given wellstream."""

    wellstream_h2s_mol_fraction: float
    stages: List[StageResult]
    to_gas_fraction: float
    to_oil_fraction: float
    to_water_fraction: float
    warnings: List[str] = field(default_factory=list)


@dataclass
class ConversionResult:
    """Wellstream H2S back-calculated from a measured separator gas H2S."""

    wellstream_h2s_mol_fraction: float
    wellstream_h2s_ppmv: float
    measured_gas_h2s_ppmv: float
    stage_index: int
    conversion_factor: float
    train: TrainResult
    warnings: List[str] = field(default_factory=list)


def _jneqsim():
    from neqsim import jneqsim

    return jneqsim


def water_mole_fraction(water_sm3_d: float, dry_wellstream_kmol_d: float) -> float:
    """Mole fraction of water in a wellstream from a water rate and dry molar rate."""
    if water_sm3_d < 0 or dry_wellstream_kmol_d <= 0:
        raise ValueError("water rate must be >= 0 and dry molar rate > 0")
    water_kmol_d = water_sm3_d * WATER_DENSITY_KG_M3 / WATER_MOLAR_MASS_G_MOL
    return water_kmol_d / (water_kmol_d + dry_wellstream_kmol_d)


def h2s_partial_pressure_kpa(h2s_mol_fraction: float, pressure_bara: float) -> float:
    """H2S partial pressure in kPa from gas-phase mole fraction and absolute pressure."""
    return h2s_mol_fraction * pressure_bara * 100.0


def is_sour_service(h2s_mol_fraction: float, pressure_bara: float, threshold_kpa: float = 0.3) -> bool:
    """ISO 15156-2 / NACE MR0175 carbon-steel screening: sour when pH2S reaches 0.3 kPa."""
    return h2s_partial_pressure_kpa(h2s_mol_fraction, pressure_bara) >= threshold_kpa


def make_wellstream(
    composition: Optional[Dict[str, float]] = None,
    water_mol_fraction: float = 0.0,
    h2s_mol_fraction: float = 0.0,
    temperature_c: float = 70.0,
    pressure_bara: float = 10.0,
    eos: str = "cpa",
):
    """Create a NeqSim wellstream fluid (dry composition, water and H2S) with a mixing rule."""
    if not 0.0 <= water_mol_fraction < 1.0:
        raise ValueError("water_mol_fraction must be in [0, 1)")
    if not 0.0 <= h2s_mol_fraction < 0.5:
        raise ValueError("h2s_mol_fraction must be in [0, 0.5)")
    comp = dict(composition or DEFAULT_COMPOSITION)
    comp = {k: v for k, v in comp.items() if k not in ("H2S", "water")}
    total = sum(comp.values())
    if total <= 0:
        raise ValueError("composition must have positive total")
    jn = _jneqsim()
    use_cpa = eos.lower() == "cpa"
    cls = jn.thermo.system.SystemSrkCPAstatoil if use_cpa else jn.thermo.system.SystemSrkEos
    fluid = cls(273.15 + temperature_c, pressure_bara)
    dry = 1.0 - water_mol_fraction - h2s_mol_fraction
    for name, value in comp.items():
        fluid.addComponent(name, dry * value / total)
    fluid.addComponent("H2S", h2s_mol_fraction)
    fluid.addComponent("water", water_mol_fraction)
    if use_cpa:
        fluid.setMixingRule(10)
    else:
        fluid.setMixingRule("classic")
    fluid.setMultiPhaseCheck(True)
    return fluid


def with_h2s(fluid, h2s_mol_fraction: float):
    """Clone a fluid that already contains H2S and set its H2S mole fraction, rescaling the rest."""
    if not 0.0 <= h2s_mol_fraction < 0.5:
        raise ValueError("h2s_mol_fraction must be in [0, 0.5)")
    new = fluid.clone()
    new.init(0)
    names = [str(n) for n in new.getComponentNames()]
    if "H2S" not in names:
        raise ValueError("fluid must contain an H2S component")
    z = [float(new.getPhase(0).getComponent(n).getz()) for n in names]
    k = names.index("H2S")
    rest = sum(v for i, v in enumerate(z) if i != k)
    scaled = [(1.0 - h2s_mol_fraction) * v / rest if i != k else h2s_mol_fraction for i, v in enumerate(z)]
    new.setMolarComposition(scaled)
    return new


def _component_x(stream_fluid, name: str) -> float:
    return float(stream_fluid.getPhase(0).getComponent(name).getx())


def _stream_flow_mol_s(stream) -> float:
    try:
        return float(stream.getFlowRate("mole/sec"))
    except Exception:
        return 0.0


def _ppmw(x_h2s: float, molar_mass_kg_mol: float) -> float:
    return x_h2s * H2S_MOLAR_MASS_G_MOL / (molar_mass_kg_mol * 1000.0) * 1.0e6


def run_train(fluid, stages: Sequence[SeparatorStage], flow_mol_s: float = 1.0) -> TrainResult:
    """Flash a wellstream through a train of three-phase separators and report H2S distribution.

    Gas from each stage leaves the train. Oil feeds the next stage. Water leaves each
    stage to the drain with its dissolved H2S.
    """
    if not stages:
        raise ValueError("at least one separator stage is required")
    jn = _jneqsim()
    warnings: List[str] = []
    current = fluid.clone()
    current.init(0)
    h2s_in =  float(current.getPhase(0).getComponent("H2S").getz()) * flow_mol_s
    results: List[StageResult] = []
    gas_total = oil_total = water_total = 0.0
    current_flow = flow_mol_s
    for idx, st in enumerate(stages):
        feed = jn.process.equipment.stream.Stream("feed%d" % idx, current)
        feed.setTemperature(st.temperature_c, "C")
        feed.setPressure(st.pressure_bara, "bara")
        feed.setFlowRate(current_flow, "mole/sec")
        sep = jn.process.equipment.separator.ThreePhaseSeparator("sep%d" % idx, feed)
        ps = jn.process.processmodel.ProcessSystem()
        ps.add(feed)
        ps.add(sep)
        ps.run()
        gas_flow = _stream_flow_mol_s(sep.getGasOutStream())
        oil_flow = _stream_flow_mol_s(sep.getOilOutStream())
        water_flow = _stream_flow_mol_s(sep.getWaterOutStream())
        gas_y = oil_x = water_x = 0.0
        oil_ppmw = water_ppmw = water_mg_l = 0.0
        if gas_flow > 1.0e-12:
            gas_y = _component_x(sep.getGasOutStream().getFluid(), "H2S")
        if oil_flow > 1.0e-12:
            ofl = sep.getOilOutStream().getFluid()
            oil_x = _component_x(ofl, "H2S")
            oil_ppmw = _ppmw(oil_x, float(ofl.getPhase(0).getMolarMass()))
        if water_flow > 1.0e-12:
            wfl = sep.getWaterOutStream().getFluid()
            water_x = _component_x(wfl, "H2S")
            water_ppmw = _ppmw(water_x, float(wfl.getPhase(0).getMolarMass()))
            water_mg_l = water_ppmw * WATER_DENSITY_KG_M3 / 1000.0
        g_mol, o_mol, w_mol = gas_y * gas_flow, oil_x * oil_flow, water_x * water_flow
        gas_total += g_mol
        water_total += w_mol
        if idx == len(stages) - 1:
            oil_total = o_mol
        results.append(
            StageResult(
                name=st.name or "stage%d" % (idx + 1),
                temperature_c=st.temperature_c,
                pressure_bara=st.pressure_bara,
                gas_h2s_ppmv=gas_y * 1.0e6,
                gas_h2s_mol_s=g_mol,
                oil_h2s_ppmw=oil_ppmw,
                oil_h2s_mol_s=o_mol,
                water_h2s_ppmw=water_ppmw,
                water_h2s_mg_per_l=water_mg_l,
                water_h2s_mol_s=w_mol,
                gas_pressure_h2s_kpa=h2s_partial_pressure_kpa(gas_y, st.pressure_bara),
            )
        )
        if oil_flow <= 1.0e-12 and idx < len(stages) - 1:
            warnings.append("no oil phase leaving %s; downstream stages not evaluated" % results[-1].name)
            break
        current = sep.getOilOutStream().getFluid().clone()
        current_flow = oil_flow
    if h2s_in > 0:
        closure = (gas_total + oil_total + water_total) / h2s_in
        if abs(closure - 1.0) > 0.02:
            warnings.append("H2S balance closure %.3f outside 2 percent" % closure)
    denom = h2s_in if h2s_in > 0 else 1.0
    return TrainResult(
        wellstream_h2s_mol_fraction=h2s_in / flow_mol_s,
        stages=results,
        to_gas_fraction=gas_total / denom,
        to_oil_fraction=oil_total / denom,
        to_water_fraction=water_total / denom,
        warnings=warnings,
    )


def _bisect_log(func: Callable[[float], float], target: float, lo: float, hi: float, tol: float = 1.0e-6, itmax: int = 80) -> float:
    """Solve func(z) = target for z in [lo, hi] assuming func is monotonic increasing; log-spaced."""
    f_lo, f_hi = func(lo), func(hi)
    if not (f_lo <= target <= f_hi):
        raise ValueError(
            "measured value %.4g is outside the bracket [%.4g, %.4g] reachable for z in [%.2g, %.2g]"
            % (target, f_lo, f_hi, lo, hi)
        )
    a, b = math.log(lo), math.log(hi)
    for _ in range(itmax):
        mid = 0.5 * (a + b)
        val = func(math.exp(mid))
        if abs(val - target) <= tol * target:
            return math.exp(mid)
        if val < target:
            a = mid
        else:
            b = mid
    return math.exp(0.5 * (a + b))


def wellstream_h2s_from_separator_gas(
    fluid,
    stages: Sequence[SeparatorStage],
    measured_gas_h2s_ppmv: float,
    stage_index: int = 0,
    z_min: float = 1.0e-9,
    z_max: float = 0.05,
) -> ConversionResult:
    """Back-calculate wellstream H2S from the measured H2S in the gas leaving one separator stage.

    fluid must contain H2S, water if present and the dry composition; its H2S content is
    replaced during the solve. The gas H2S ppmv is monotonic in wellstream H2S, so a log
    bisection is used.
    """
    if measured_gas_h2s_ppmv <= 0:
        raise ValueError("measured_gas_h2s_ppmv must be positive")
    if not 0 <= stage_index < len(stages):
        raise ValueError("stage_index outside the separator train")
    stages_eval = list(stages[: stage_index + 1])

    def gas_ppmv(z: float) -> float:
        return run_train(with_h2s(fluid, z), stages_eval).stages[-1].gas_h2s_ppmv

    z_sol = _bisect_log(gas_ppmv, measured_gas_h2s_ppmv, z_min, z_max)
    train = run_train(with_h2s(fluid, z_sol), stages)
    warnings = list(train.warnings)
    if len(train.stages) <= stage_index:
        warnings.append("train did not reach the measurement stage")
    if train.to_water_fraction > 0.5:
        warnings.append("most H2S reports to water; aqueous ionisation (pH) is not modelled and may bias the result")
    return ConversionResult(
        wellstream_h2s_mol_fraction=z_sol,
        wellstream_h2s_ppmv=z_sol * 1.0e6,
        measured_gas_h2s_ppmv=measured_gas_h2s_ppmv,
        stage_index=stage_index,
        conversion_factor=z_sol * 1.0e6 / measured_gas_h2s_ppmv,
        train=train,
        warnings=warnings,
    )


def conversion_factor_curve(
    composition: Optional[Dict[str, float]],
    stages: Sequence[SeparatorStage],
    water_mol_fractions: Sequence[float],
    stage_index: int = 0,
    probe_h2s_ppmv: float = 100.0,
    eos: str = "cpa",
) -> List[Tuple[float, float]]:
    """Wellstream-to-separator-gas H2S factor versus water mole fraction (the module's lookup table).

    In the dilute limit gas H2S is linear in wellstream H2S, so one probe level suffices.
    """
    probe = probe_h2s_ppmv * 1.0e-6
    out: List[Tuple[float, float]] = []
    for wf in water_mol_fractions:
        fl = make_wellstream(composition, water_mol_fraction=wf, h2s_mol_fraction=probe, eos=eos)
        y = run_train(fl, list(stages[: stage_index + 1])).stages[-1].gas_h2s_ppmv
        out.append((wf, probe * 1.0e6 / y if y > 0 else float("nan")))
    return out


_R = 8.314462618
_T_SC_K = 288.15
_P_SC_PA = 101325.0


@dataclass
class RecombinationResult:
    """Wellstream recombined so that a test separator reproduces measured GOR and gas H2S."""

    fluid: object
    wellstream_h2s_mol_fraction: float
    gor_calc: float
    gor_measured: float
    y_h2s_calc: float
    y_h2s_measured: float
    n_iter: int
    converged: bool
    warnings: List[str] = field(default_factory=list)


def _phase_by_type(flashed) -> Dict[str, object]:
    out = {}
    for i in range(int(flashed.getNumberOfPhases())):
        ph = flashed.getPhase(i)
        out[str(ph.getPhaseTypeName())] = ph
    return out


def _flash_stage(fluid, stage: SeparatorStage):
    jn = _jneqsim()
    f = fluid.clone()
    f.setTemperature(stage.temperature_c + 273.15)
    f.setPressure(stage.pressure_bara)
    jn.thermodynamicoperations.ThermodynamicOperations(f).TPflash()
    f.initProperties()
    return f


def separator_gor_and_gas_h2s(fluid, stage: SeparatorStage) -> Tuple[float, float]:
    """GOR (standard gas Sm3 per actual separator-oil m3) and separator-gas H2S mole fraction.

    Volumes come from the phase compressibility factor, as for an ideal-gas standard volume,
    to avoid the unreliable molar volume of characterised fluids.
    """
    f = _flash_stage(fluid, stage)
    ph = _phase_by_type(f)
    if "gas" not in ph or "oil" not in ph:
        raise ValueError("separator flash must give gas and oil; got %s" % sorted(ph))
    t_k, p_pa = stage.temperature_c + 273.15, stage.pressure_bara * 1.0e5
    v_oil = float(ph["oil"].getBeta()) * float(ph["oil"].getZ()) * _R * t_k / p_pa
    v_gas_sc = float(ph["gas"].getBeta()) * _R * _T_SC_K / _P_SC_PA
    return v_gas_sc / v_oil, float(ph["gas"].getComponent("H2S").getx())


def recombine_to_gor_and_h2s(
    fluid,
    stage: SeparatorStage,
    gor_measured: float,
    y_h2s_measured: float,
    water_mol_fraction: Optional[float] = None,
    max_iter: int = 30,
    tol: float = 1.0e-4,
) -> RecombinationResult:
    """Adjust a wellstream so a test separator reproduces the measured GOR and gas H2S together.

    Each pass flashes at the separator conditions, sets gas H2S to the measurement (other gas
    components rescaled), sets oil H2S from the calculated K value, and recombines gas and oil at
    gor_measured (Sm3 standard gas per m3 actual separator oil). Water is held at
    water_mol_fraction (default: the input fluid's water mole fraction) and added back after
    recombination. Convergence is relative on GOR and on gas H2S, never absolute on composition,
    because H2S is a trace component.
    """
    if gor_measured <= 0 or not 0 < y_h2s_measured < 0.5:
        raise ValueError("gor_measured must be positive and y_h2s_measured in (0, 0.5)")
    jn = _jneqsim()
    cur = fluid.clone()
    cur.init(0)
    names = [str(n) for n in cur.getComponentNames()]
    if "H2S" not in names:
        raise ValueError("fluid must contain an H2S component")
    i_h2s = names.index("H2S")
    i_w = names.index("water") if "water" in names else None
    z0 = [float(cur.getPhase(0).getComponent(n).getz()) for n in names]
    w = z0[i_w] if (i_w is not None and water_mol_fraction is None) else (water_mol_fraction or 0.0)
    if w > 0 and i_w is None:
        raise ValueError("water_mol_fraction given but fluid has no water component")
    warnings: List[str] = []
    t_k, p_pa = stage.temperature_c + 273.15, stage.pressure_bara * 1.0e5
    v_gas_sc = _R * _T_SC_K / _P_SC_PA
    converged = False
    trim = 1.0
    gor_calc = y_calc = float("nan")
    it = 0
    for it in range(1, max_iter + 1):
        f = _flash_stage(cur, stage)
        ph = _phase_by_type(f)
        if "gas" not in ph or "oil" not in ph:
            warnings.append("separator flash lost a gas or oil phase at iteration %d" % it)
            break
        gas, oil = ph["gas"], ph["oil"]
        z_oil = float(oil.getZ())
        gor_calc = float(gas.getBeta()) * v_gas_sc / (float(oil.getBeta()) * z_oil * _R * t_k / p_pa)
        y = [float(gas.getComponent(n).getx()) for n in names]
        x = [float(oil.getComponent(n).getx()) for n in names]
        y_calc = y[i_h2s]
        if abs(y_calc / y_h2s_measured - 1.0) < tol and abs(gor_calc / gor_measured - 1.0) < tol:
            converged = True
            break
        if y_calc <= 0 or x[i_h2s] <= 0:
            warnings.append("calculated H2S is zero in gas or oil; cannot rescale")
            break
        k_h2s = y_calc / x[i_h2s]
        sg = (1.0 - y_h2s_measured) / (1.0 - y_calc)
        y_star = [y_h2s_measured if i == i_h2s else v * sg for i, v in enumerate(y)]
        x_h2s_new = y_h2s_measured / k_h2s
        so = (1.0 - x_h2s_new) / (1.0 - x[i_h2s])
        x_star = [x_h2s_new if i == i_h2s else v * so for i, v in enumerate(x)]
        n_oil = 1.0 / (z_oil * _R * t_k / p_pa)
        n_gas = gor_measured / v_gas_sc
        if abs(y_calc / y_h2s_measured - 1.0) < 0.05:
            trim *= y_h2s_measured / y_calc
        z_hc = [n_oil * x_star[i] + n_gas * y_star[i] if i != i_w else 0.0 for i in range(len(names))]
        z_hc[i_h2s] *= trim
        tot = sum(z_hc)
        z_new = [(1.0 - w) * v / tot for v in z_hc]
        if i_w is not None:
            z_new[i_w] = w
        cur = cur.clone()
        cur.setMolarComposition(z_new)
        cur.init(0)
    if not converged:
        warnings.append("recombination did not converge in %d iterations (tol %.1e relative)" % (max_iter, tol))
    cur_z = float(cur.getPhase(0).getComponent("H2S").getz())
    return RecombinationResult(
        fluid=cur,
        wellstream_h2s_mol_fraction=cur_z,
        gor_calc=gor_calc,
        gor_measured=gor_measured,
        y_h2s_calc=y_calc,
        y_h2s_measured=y_h2s_measured,
        n_iter=it,
        converged=converged,
        warnings=warnings,
    )