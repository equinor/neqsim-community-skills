"""Capability ledger: what is implemented and validated, what is screening, what needs external tools.

Status labels (exactly four):

``IMPLEMENTED_VALIDATED``  executable in NeqSim and checked against an analytic limit, textbook formula
                           or cross-correlation in the NeqSim test suite (not field-calibrated).
``SCREENING``              executable but approximate, uncalibrated or covering part of the problem.
``EXTERNAL_TOOL_REQUIRED`` needs a specialist tool or discipline; this skill produces an interface
                           specification and an unresolved assessment, never a number.
``NOT_PERFORMED``          not implemented anywhere reachable; recorded so the report cannot imply it.

``available`` is set at run time from the NeqSim runtime probe: a ledger row whose class is missing is
reported as available=False and its calculation is skipped with an explicit reason.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from .runtime import RuntimeStatus, ensure_runtime

STATUS = ("IMPLEMENTED_VALIDATED", "SCREENING", "EXTERNAL_TOOL_REQUIRED", "NOT_PERFORMED")


@dataclass
class LedgerEntry:
    """One calculation or assessment."""

    id: str
    calculation: str
    status: str
    implementation: str
    requires: List[str] = field(default_factory=list)
    validation_evidence: str = ""
    limits: str = ""
    route_if_not_available: str = ""
    available: bool = True


def _e(i, calc, status, impl, requires=None, evidence="", limits="", route=""):
    return LedgerEntry(i, calc, status, impl, list(requires or []), evidence, limits, route)


_LEDGER = [
    _e("L01", "Wellbore temperature profile (Ramey, producer and injector, layered U, shut-in cooldown)", "IMPLEMENTED_VALIDATED",
       "neqsim.process.fielddevelopment.wellplanning.WellboreThermalModel", ["WellboreThermalModel"],
       "analytic limits and ODE cross-check in NeqSim unit tests (8)", "no JT/friction heating, linear geotherm, vertical depth, single exponential cooldown",
       "use PH flash for JT heating; transient thermal tool for cement/annulus transients"),
    _e("L02", "Tubing multiphase hydraulics: drift-flux traverse, flow regime, Turner loading ratio, erosional ratio", "IMPLEMENTED_VALIDATED",
       "wellplanning.DriftFluxWellboreHydraulics", ["DriftFluxWellboreHydraulics"],
       "static column, Darcy-Weisbach, dry-gas integration, Beggs-Brill agreement (10 tests); not field-calibrated",
       "no acceleration term, no emulsion viscosity, no stratified/horizontal model; correlations spread (drift-flux vs Beggs-Brill vs Gray) on gas-condensate",
       "compare with PipeBeggsAndBrills / TwoFluidPipe; transient simulator (OLGA-class) for unloading and slugging"),
    _e("L03", "Gas-condensate inflow with condensate banking and non-Darcy flow", "IMPLEMENTED_VALIDATED",
       "wellplanning.GasCondensateInflowModel", ["GasCondensateInflowModel"],
       "dry-gas limit vs independent pseudo-pressure integral (0.5 %); banking is SCREENING", "no velocity-dependent kr, no CVD composition change, no layered/horizontal wells",
       "reservoir simulator / well-test interpretation for banking skin"),
    _e("L04", "Oil/gas IPR from Darcy (linear above bubble point, Vogel/Standing below) and nodal solve", "SCREENING",
       "integrated_well_planning.producers + model_chain (Python) over NeqSim fluid properties", ["SystemSrkEos"],
       "closed-form checks in the skill tests; NeqSim NodalAnalysis cross-check on linear inflow", "single node at bottom hole, constant GOR, no layered reservoir",
       "reservoir simulator or well-test derived IPR (neqsim-near-well-and-injectivity)"),
    _e("L05", "Nodal analysis intersections, stability, loading onset", "IMPLEMENTED_VALIDATED",
       "wellplanning.NodalAnalysis (cross-check) and the Python root finder in integrated_well_planning.nodal", ["NodalAnalysis"],
       "linear, Vogel and U-shaped outflow closed forms (7 tests)", "single node at bottom hole; no choke/network back pressure in the Java class",
       "WellSystem / network classes for coupled back pressure"),
    _e("L06", "Injection hydraulics: water and gas column, friction, injection temperature, matrix operating point, thermal fracture-pressure reduction", "IMPLEMENTED_VALIDATED",
       "wellplanning.InjectionWellHydraulics", ["InjectionWellHydraulics"],
       "static column, Darcy-Weisbach, gas-column integration, thermal fracture reduction (6 tests)", "no fracture propagation, plugging or Hall-plot dynamics; homogeneous two-phase; full-cooling upper bound for thermal stress",
       "InjectionWellModel (multi-zone, Hall slope); fracture simulator for intentional-fracture injection"),
    _e("L07", "Gas injectivity (radial pseudo-pressure, Z and viscosity from NeqSim) and compression duty (isentropic, NeqSim PS flash)", "SCREENING",
       "integrated_well_planning.injectors", ["SystemSrkEos", "ThermodynamicOperations"], "closed-form limits in skill tests",
       "no non-Darcy term, no layering; efficiency is an input", "reservoir simulator; compressor vendor performance map (neqsim-compressor-power-screening)"),
    _e("L08", "Hydrate-inhibitor dose along the well (MEG, methanol) with CPA partitioning and pump basis", "IMPLEMENTED_VALIDATED",
       "wellplanning.WellChemicalTreatment", ["WellChemicalTreatment"], "Hammerschmidt magnitude and mass balances (5 tests)", "no salt-in-MEG, MEG regeneration, KHI or brine compatibility",
       "laboratory hydrate/inhibitor data; production-chemistry specialist"),
    _e("L09", "Annular pressure build-up (closed form, fluid properties from NeqSim)", "IMPLEMENTED_VALIDATED",
       "wellplanning.AnnularPressureBuildup", ["AnnularPressureBuildup"], "rigid limit, Lame compliance, bleed and gas-cushion balances (8 tests)",
       "vertical, uniform properties, free-standing outer string, single temperature change per annulus", "specialist well-load software for cemented and multi-string systems"),
    _e("L10", "Tubing movement, packer load, buckling and triaxial (von Mises) check", "IMPLEMENTED_VALIDATED",
       "wellplanning.TubingMovementCalculator", ["TubingMovementCalculator"], "piston, ballooning, temperature, buckling thresholds, von Mises closed forms (7 tests)",
       "vertical well, no friction or bending, no ISO 13679 load-case matrix", "specialist tubular-stress software (not a substitute)"),
    _e("L11", "Tubular burst/collapse/body-yield ratings (API TR 5C3 formulas) and utilisation against supplied design factors", "SCREENING",
       "well_design_study.casing_design (required drilling/casing module)", [], "formula cross-check in that skill's tests",
       "design factors are never defaulted here; supplied factors only", "operator casing-design software and the verified standard edition"),
    _e("L12", "Pressure window, casing seats, kick tolerance, torque and drag, ECD, time and cost Monte Carlo", "SCREENING",
       "well_design_study (drilling/casing module)", [], "see that skill", "screening level, offset-calibrated when evidence exists", "operator drilling-engineering tools"),
    _e("L13", "Wellhead/shut-in pressure and barrier schematics (data model and drawings)", "SCREENING",
       "integrated_well_planning.barriers", [], "structure and consistency tests", "status of every element is UNVERIFIED until evidence is supplied; no compliance statement",
       "independent well-integrity review"),
    _e("L14", "Operating-envelope table with limit source, margin and status (fail-closed)", "IMPLEMENTED_VALIDATED",
       "integrated_well_planning.envelope", [], "unit tests: missing source => NEEDS_REVIEW, margins and traffic lights", "limits are only as good as the supplied sources",
       ""),
    _e("L15", "Alternatives comparison (tubing, WHP, lift, completion): feasibility, binding constraint, scorecard, Pareto", "SCREENING",
       "integrated_well_planning.alternatives", [], "tests on synthetic alternatives", "deliverability only; recovery and project value are not inferred",
       "field-development / economics agents with a reservoir forecast"),
    _e("L16", "Gas-lift screening (injection at the shoe, drift-flux VLP)", "SCREENING", "integrated_well_planning.producers.lift_gas", ["DriftFluxWellboreHydraulics"],
       "monotonic benefit tests", "valve depth, stability and injection-pressure limits not modelled", "GasLiftPerformanceCurve / gas-lift allocation agent / ArtificialLiftScreener"),
    _e("L17", "ESP and other artificial-lift design", "EXTERNAL_TOOL_REQUIRED", "ArtificialLiftScreener (screening) then vendor ESP design", [], "", "", "artificial-lift-agent / vendor tool"),
    _e("L18", "Scale prediction and injection-water compatibility", "EXTERNAL_TOOL_REQUIRED",
       "core WaterCompatibilityScreener / BrineMixingScaleEvaluator when water analyses are supplied", [], "", "no water analysis => NOT_PERFORMED",
       "neqsim-produced-water-scale-screening skill; laboratory brine compatibility test"),
    _e("L19", "CO2/H2S corrosion rate and sour-service (partial-pressure) screening", "SCREENING", "core CO2CorrosionAnalyzer / SourServiceAssessment", [],
       "see core tests", "sour-service approval and material selection stay with the materials engineer (ISO 15156)", "materials engineer"),
    _e("L20", "Wax appearance and deposition", "SCREENING", "supplied WAT margin only; NeqSim wax models when a wax characterisation exists", [], "", "no WAT => NOT_PERFORMED",
       "laboratory WAT/pour-point measurement"),
    _e("L21", "Transient start-up, shut-in, unloading and slugging", "EXTERNAL_TOOL_REQUIRED", "TwoFluidPipe (NeqSim) or an OLGA-class simulator", [], "",
       "steady-state screening must never be called transient validation", "olga-simulation-agent / flow-assurance-study-agent"),
    _e("L22", "Anti-collision / survey-uncertainty clearance", "EXTERNAL_TOOL_REQUIRED", "ISCWSA-based tool (well-trajectory-anticollision-agent screening, then Compass-class tool)", [], "",
       "this skill computes geometry only", "well-trajectory-anticollision-agent"),
    _e("L23", "Geomechanics and borehole stability", "EXTERNAL_TOOL_REQUIRED", "specialist geomechanics software", [], "", "interface specification only", "geomechanics specialist"),
    _e("L24", "Drilling hydraulics, cement placement and detailed mechanical design", "EXTERNAL_TOOL_REQUIRED", "operator drilling/cementing/casing-design software", [], "",
       "interface specification only; screening ECD/torque-drag via well_design_study", "drilling engineer"),
    _e("L25", "Reservoir recovery, depletion forecast and project value", "NOT_PERFORMED", "not inferred from deliverability", [], "", "", "reservoir-simulator-agent, reservoir-history-match-agent, field-development, asset-economics-agent"),
    _e("L26", "Velocity-dependent relative permeability, CVD composition change, stratified/horizontal wellbore model, fracture-injection dynamics, ISO 13679 load-case matrix", "NOT_PERFORMED",
       "recorded Java follow-ups (see JAVA_FOLLOW_UPS)", [], "", "", "specialist tools"),
]

JAVA_FOLLOW_UPS = [
    "Expose the wellplanning classes through the automation/MCP layer (runCapability) so single calculations can run without Python glue.",
    "Add a producer-side GOR/water-cut aware VLP (variable solution GOR along the well) and an emulsion-viscosity option to DriftFluxWellboreHydraulics.",
    "Add NodalAnalysis adapters for the composite (Vogel above/below bubble point) IPR and a choke/flowline outflow node so a full chain is one Java call.",
    "Add a WellLoadCaseMatrix (ISO 13679-style) that combines TubingMovementCalculator, AnnularPressureBuildup and tubular ratings across life-cycle states.",
    "Add velocity-dependent (capillary-number) relative permeability to GasCondensateInflowModel.",
    "Add a barrier-schematic data class (elements, envelopes, verification status) next to WellBarrierSchematic for DEXPI-style export.",
]


def build_ledger(runtime: Optional[RuntimeStatus] = None) -> List[LedgerEntry]:
    """Return the ledger with ``available`` set from the runtime probe."""
    rt = runtime or ensure_runtime()
    out = []
    for proto in _LEDGER:
        e = LedgerEntry(**asdict(proto))
        e.available = all(rt.has(r) for r in e.requires) if e.requires else True
        out.append(e)
    return out


def ledger_rows(runtime: Optional[RuntimeStatus] = None) -> List[Dict[str, object]]:
    """Ledger as dictionaries (for JSON, Word tables)."""
    return [asdict(e) for e in build_ledger(runtime)]


def status_counts(runtime: Optional[RuntimeStatus] = None) -> Dict[str, int]:
    """Count ledger rows per status label."""
    counts = {s: 0 for s in STATUS}
    for e in build_ledger(runtime):
        counts[e.status] += 1
    return counts


def lookup(entry_id: str) -> LedgerEntry:
    """Return one ledger entry by id (L01...)."""
    for e in _LEDGER:
        if e.id == entry_id:
            return e
    raise KeyError(entry_id)
