"""CO2 transport chain screening with NeqSim: pipeline, depressurisation, well.

The chain follows one CO2 stream from the pipeline inlet to the reservoir:

1. **Pipeline profile** - NeqSim ``PipeBeggsAndBrills`` (Peng-Robinson).
2. **Single-phase margin** - at each station, the highest pressure at which
   the stream splits into two phases at that temperature (flash scan with
   bisection, valid above and below the mixture critical temperature); the
   margin is station pressure minus that boundary.
3. **Water** - water solubility in the CO2 phase at each station from an
   SRK-CPA flash with excess water; margin to the stream's water content.
4. **Impurities** - NeqSim ``DensePhaseCO2Corrosion`` at the coldest station.
5. **Depressurisation** - isenthalpic (valve) and isentropic (vessel
   blowdown) expansion to atmosphere from the highest-pressure and coldest
   stations; dry-ice and minimum design temperature checks.
6. **Injection well** - NeqSim ``CO2InjectionWellAnalyzer`` from the arrival
   conditions; bottom-hole pressure against the reservoir pressure.

All results are screening-level.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

NAN = float("nan")
CO2_TRIPLE_POINT_BAR = 5.185
CO2_TRIPLE_POINT_C = -56.56
ATMOSPHERIC_BAR = 1.01325


class CcsInputError(ValueError):
    """Raised for invalid chain inputs."""


@dataclass
class Co2Stream:
    """CO2 stream composition (mole fractions or any molar basis).

    Use NeqSim names: ``CO2``, ``nitrogen``, ``argon``, ``hydrogen``,
    ``oxygen``, ``methane``, ``H2S``, ``CO``, ``water``. ``water`` is the
    dissolved water in the delivered stream.
    """

    components: dict[str, float]
    so2_ppmv: float = 0.0
    nox_ppmv: float = 0.0

    def __post_init__(self) -> None:
        if any(not math.isfinite(v) or v < 0 for v in self.components.values()):
            raise CcsInputError("component amounts must be finite and >= 0")
        if self.components.get("CO2", 0.0) <= 0:
            raise CcsInputError("the stream needs CO2")
        if self.co2_fraction() < 0.8:
            raise CcsInputError("this chain is for CO2-rich streams (>= 80 mol % CO2)")

    def total(self) -> float:
        """Total molar amount."""
        return sum(self.components.values())

    def fraction(self, name: str) -> float:
        """Mole fraction of a component."""
        return self.components.get(name, 0.0) / self.total()

    def co2_fraction(self) -> float:
        """CO2 mole fraction."""
        return self.fraction("CO2")

    def water_ppm_mol(self) -> float:
        """Water content, ppm(mol)."""
        return self.fraction("water") * 1e6

    def dry(self) -> dict[str, float]:
        """Water-free composition, normalised."""
        dry = {k: v for k, v in self.components.items() if k != "water" and v > 0}
        total = sum(dry.values())
        return {k: v / total for k, v in dry.items()}


@dataclass
class Co2Pipeline:
    """Pipeline from compression to the injection site."""

    length_m: float
    inner_diameter_m: float
    mass_flow_kg_h: float
    inlet_pressure_bara: float
    inlet_temperature_c: float
    ambient_temperature_c: float = 4.0
    overall_u_w_m2k: float = 5.0
    elevation_change_m: float = 0.0
    roughness_m: float = 5e-5
    segments: int = 20

    def __post_init__(self) -> None:
        if min(self.length_m, self.inner_diameter_m, self.mass_flow_kg_h) <= 0:
            raise CcsInputError("length, diameter and mass flow must be > 0")
        if self.inlet_pressure_bara <= 1 or not 2 <= self.segments <= 200:
            raise CcsInputError("inlet pressure > 1 bara and 2-200 segments")


@dataclass
class InjectionWell:
    """Injection well for NeqSim ``CO2InjectionWellAnalyzer``."""

    depth_m: float
    tubing_inner_diameter_m: float
    reservoir_pressure_bara: float
    top_formation_temperature_c: float = 4.0
    bottom_formation_temperature_c: float = 40.0
    roughness_m: float = 4.5e-5
    fracture_pressure_bara: float | None = None

    def __post_init__(self) -> None:
        if (
            min(
                self.depth_m, self.tubing_inner_diameter_m, self.reservoir_pressure_bara
            )
            <= 0
        ):
            raise CcsInputError(
                "depth, tubing diameter and reservoir pressure must be > 0"
            )


@dataclass
class ChainLimits:
    """User-stated screening limits."""

    min_single_phase_margin_bar: float = 10.0
    water_margin_factor: float = 2.0
    min_design_temperature_c: float = -46.0
    maop_bara: float | None = None

    def __post_init__(self) -> None:
        if self.water_margin_factor < 1.0:
            raise CcsInputError("water_margin_factor must be >= 1")


@dataclass
class Station:
    """One pipeline station."""

    distance_m: float
    pressure_bara: float
    temperature_c: float
    phases: int = 1
    density_kg_m3: float = NAN
    two_phase_boundary_bara: float = NAN
    single_phase_margin_bar: float = NAN
    water_solubility_ppm_mol: float = NAN
    water_margin_factor: float = NAN


@dataclass(frozen=True)
class Finding:
    """One observation."""

    severity: str
    code: str
    message: str


@dataclass
class ChainReport:
    """Result of :func:`assess_transport_chain`."""

    stations: list[Station]
    depressurisation: list[dict[str, Any]]
    impurities: dict[str, Any] | None
    well: dict[str, Any] | None
    findings: list[Finding] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def highest_severity(self) -> str:
        """``high``, ``warning``, ``info`` or ``none``."""
        for level in ("high", "warning", "info"):
            if any(f.severity == level for f in self.findings):
                return level
        return "none"

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe summary (NaN becomes None)."""

        def clean(value: Any) -> Any:
            if isinstance(value, float) and not math.isfinite(value):
                return None
            if isinstance(value, dict):
                return {k: clean(v) for k, v in value.items()}
            if isinstance(value, list | tuple):
                return [clean(v) for v in value]
            return value

        return clean(
            {
                "calculation_basis": "screening",
                "highest_severity": self.highest_severity,
                "summary": self.summary,
                "findings": [asdict(f) for f in self.findings],
                "stations": [asdict(s) for s in self.stations],
                "depressurisation": self.depressurisation,
                "impurities": self.impurities,
                "well": self.well,
            }
        )

    def to_markdown(self) -> str:
        """Short report."""

        def fmt(value: float, digits: int = 1) -> str:
            return f"{value:.{digits}f}" if math.isfinite(value) else "-"

        lines = ["# CO2 transport chain", "", "## Summary", ""]
        for key, value in self.summary.items():
            text = fmt(value, 2) if isinstance(value, float) else str(value)
            lines.append(f"- {key.replace('_', ' ')}: {text}")
        lines += ["", "## Findings", ""]
        for f in self.findings or [Finding("info", "none", "No issues flagged.")]:
            lines.append(f"- **{f.severity.upper()}** `{f.code}`: {f.message}")
        lines += [
            "",
            "## Pipeline stations",
            "",
            (
                "| km | P (bara) | T (C) | Phases | Density (kg/m3) | 2-phase boundary "
                "(bara) | Margin (bar) | H2O solubility (ppm) | Water factor |"
            ),
            "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for s in self.stations:
            lines.append(
                f"| {s.distance_m / 1000:.1f} | {fmt(s.pressure_bara)} | "
                f"{fmt(s.temperature_c)} | {s.phases} | {fmt(s.density_kg_m3, 0)} | "
                f"{fmt(s.two_phase_boundary_bara)} | {fmt(s.single_phase_margin_bar)} | "
                f"{fmt(s.water_solubility_ppm_mol, 0)} | {fmt(s.water_margin_factor, 1)} |"
            )
        if self.depressurisation:
            lines += ["", "## Depressurisation to atmosphere", ""]
            for d in self.depressurisation:
                lines.append(
                    f"- From {d['from']} ({d['pressure_bara']:.0f} bara, "
                    f"{d['temperature_c']:.1f} C): isenthalpic "
                    f"{fmt(d['isenthalpic_final_c'])} C, isentropic "
                    f"{fmt(d['isentropic_final_c'])} C"
                )
        if self.well:
            lines += ["", "## Injection well", ""]
            w = self.well
            lines.append(f"- Bottom-hole pressure: {fmt(w['bhp_bara'])} bara")
            lines.append(f"- Bottom-hole temperature: {fmt(w['bht_c'])} C")
            lines.append(
                f"- Injectivity margin: {fmt(w['injectivity_margin_bar'])} bar"
            )
            if "fracture_margin_bar" in w:
                lines.append(f"- Fracture margin: {fmt(w['fracture_margin_bar'])} bar")
            lines.append(f"- NeqSim analyzer safe to operate: {w['safe_to_operate']}")
        return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
def _j():
    try:
        from neqsim import jneqsim
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "neqsim is not installed: python -m pip install neqsim"
        ) from exc
    return jneqsim


def _pr(composition: dict[str, float], temperature_c: float, pressure_bara: float):
    j = _j()
    system = j.thermo.system.SystemPrEos(273.15 + temperature_c, float(pressure_bara))
    for name, x in composition.items():
        system.addComponent(name, float(x))
    system.setMixingRule("classic")
    system.setMultiPhaseCheck(True)
    return system


def _phases(composition: dict[str, float], temperature_c: float, pressure_bara: float):
    system = _pr(composition, temperature_c, pressure_bara)
    j = _j()
    j.thermodynamicoperations.ThermodynamicOperations(system).TPflash()
    system.initProperties()
    return system


def two_phase_boundary_bara(
    composition: dict[str, float],
    temperature_c: float,
    p_max_bara: float = 300.0,
    step_bar: float = 2.0,
    tolerance_bar: float = 0.1,
) -> float:
    """Highest pressure with two phases at ``temperature_c``, bara.

    Scans down from ``p_max_bara`` in ``step_bar`` steps with TP flashes and
    bisects the first single-to-two-phase transition. NaN when the stream is
    single-phase over the whole range (above the cricondentherm).
    """
    pressure = p_max_bara
    previous = None
    while pressure >= ATMOSPHERIC_BAR:
        two = _phases(composition, temperature_c, pressure).getNumberOfPhases() > 1
        if two:
            if previous is None:
                return p_max_bara  # already two-phase at the top of the range
            low, high = pressure, previous
            while high - low > tolerance_bar:
                mid = 0.5 * (low + high)
                if _phases(composition, temperature_c, mid).getNumberOfPhases() > 1:
                    low = mid
                else:
                    high = mid
            return low
        previous = pressure
        pressure -= step_bar
    return NAN


def water_solubility_ppm_mol(
    composition: dict[str, float], temperature_c: float, pressure_bara: float
) -> float:
    """Water solubility in the CO2-rich phase with free water present, ppm(mol).

    SRK-CPA (Statoil) flash with 5 mol % added water; the water mole fraction
    in the non-aqueous phase is the saturation content.
    """
    j = _j()
    system = j.thermo.system.SystemSrkCPAstatoil(
        273.15 + temperature_c, float(pressure_bara)
    )
    for name, x in composition.items():
        system.addComponent(name, float(x) * 0.95)
    system.addComponent("water", 0.05)
    system.setMixingRule(10)
    system.setMultiPhaseCheck(True)
    j.thermodynamicoperations.ThermodynamicOperations(system).TPflash()
    system.init(1)
    best = NAN
    for i in range(system.getNumberOfPhases()):
        phase = system.getPhase(i)
        x_water = float(phase.getComponent("water").getx())
        if x_water < 0.5 and (not math.isfinite(best) or x_water < best):
            best = x_water
    return best * 1e6 if math.isfinite(best) else NAN


def pipeline_stations(stream: Co2Stream, pipe: Co2Pipeline) -> list[Station]:
    """Pressure and temperature along the pipeline (NeqSim Beggs and Brill)."""
    j = _j()
    system = _pr(stream.dry(), pipe.inlet_temperature_c, pipe.inlet_pressure_bara)
    feed = j.process.equipment.stream.Stream("CO2 feed", system)
    feed.setFlowRate(float(pipe.mass_flow_kg_h), "kg/hr")
    feed.setTemperature(float(pipe.inlet_temperature_c), "C")
    feed.setPressure(float(pipe.inlet_pressure_bara), "bara")
    line = j.process.equipment.pipeline.PipeBeggsAndBrills("CO2 pipeline", feed)
    line.setLength(float(pipe.length_m))
    line.setDiameter(float(pipe.inner_diameter_m))
    line.setElevation(float(pipe.elevation_change_m))
    line.setPipeWallRoughness(float(pipe.roughness_m))
    line.setNumberOfIncrements(int(pipe.segments))
    line.setRunIsothermal(False)
    line.setConstantSurfaceTemperature(float(pipe.ambient_temperature_c), "C")
    line.setHeatTransferCoefficient(float(pipe.overall_u_w_m2k))
    process = j.process.processmodel.ProcessSystem()
    process.add(feed)
    process.add(line)
    process.run()
    stations = [Station(0.0, pipe.inlet_pressure_bara, pipe.inlet_temperature_c)]
    for i in range(1, pipe.segments + 1):
        stations.append(
            Station(
                distance_m=float(line.getSegmentLength(i)),
                pressure_bara=float(line.getSegmentPressure(i)),
                temperature_c=float(line.getSegmentTemperature(i)) - 273.15,
            )
        )
    return stations


def _depressurise(stream: Co2Stream, station: Station, label: str) -> dict[str, Any]:
    j = _j()
    system = _phases(stream.dry(), station.temperature_c, station.pressure_bara)
    system.init(3)
    enthalpy, entropy = float(system.getEnthalpy()), float(system.getEntropy())
    result = {
        "from": label,
        "pressure_bara": station.pressure_bara,
        "temperature_c": station.temperature_c,
    }
    for key, flash, value in (
        ("isenthalpic_final_c", "PHflash", enthalpy),
        ("isentropic_final_c", "PSflash", entropy),
    ):
        work = system.clone()
        work.setPressure(ATMOSPHERIC_BAR)
        try:
            getattr(j.thermodynamicoperations.ThermodynamicOperations(work), flash)(
                value
            )
            result[key] = float(work.getTemperature()) - 273.15
        except Exception:  # noqa: BLE001
            result[key] = NAN
    return result


def _java_to_python(value: Any) -> Any:
    try:
        import jpype

        if isinstance(value, jpype.JClass("java.util.Map")):
            return {str(k): _java_to_python(value.get(k)) for k in value.keySet()}
        if isinstance(value, jpype.JClass("java.util.List")):
            return [_java_to_python(v) for v in value]
    except Exception:  # noqa: BLE001 - not a Java object
        return value
    if isinstance(value, bool | int | float | str) or value is None:
        return value
    text = str(value)
    try:
        return float(text)
    except ValueError:
        return {"true": True, "false": False}.get(text, text)


def _well(stream: Co2Stream, arrival: Station, pipe: Co2Pipeline, well: InjectionWell):
    j = _j()
    analyzer = j.process.equipment.pipeline.CO2InjectionWellAnalyzer("injector")
    analyzer.setFluid(_pr(stream.dry(), arrival.temperature_c, arrival.pressure_bara))
    analyzer.setWellGeometry(
        float(well.depth_m),
        float(well.tubing_inner_diameter_m),
        float(well.roughness_m),
    )
    analyzer.setOperatingConditions(
        float(arrival.pressure_bara),
        float(arrival.temperature_c),
        float(pipe.mass_flow_kg_h),
    )
    analyzer.setFormationTemperature(
        float(well.top_formation_temperature_c),
        float(well.bottom_formation_temperature_c),
    )
    analyzer.runFullAnalysis()
    raw = _java_to_python(analyzer.getResults())
    design = raw.get("design_case", {}) if isinstance(raw, dict) else {}
    bhp = float(design.get("BHP_bara", NAN)) if isinstance(design, dict) else NAN
    result = {
        "bhp_bara": bhp,
        "bht_c": float(design.get("BHT_C", NAN)) if isinstance(design, dict) else NAN,
        "safe_to_operate": bool(analyzer.isSafeToOperate()),
        "injectivity_margin_bar": bhp - well.reservoir_pressure_bara,
        "analyzer": raw,
    }
    if well.fracture_pressure_bara is not None:
        result["fracture_margin_bar"] = well.fracture_pressure_bara - bhp
    return result


def assess_transport_chain(
    stream: Co2Stream,
    pipe: Co2Pipeline,
    well: InjectionWell | None = None,
    limits: ChainLimits | None = None,
    stations: Sequence[Station] | None = None,
) -> ChainReport:
    """Screen a CO2 transport chain from pipeline inlet to reservoir.

    Args:
        stream: CO2 stream with impurities and water.
        pipe: Pipeline (also gives the mass flow for the well).
        well: Optional injection well at the pipeline outlet.
        limits: Screening limits.
        stations: Optional own pressure-temperature profile instead of the
            NeqSim pipeline model.
    """
    limits = limits or ChainLimits()
    stations = (
        list(stations) if stations is not None else pipeline_stations(stream, pipe)
    )
    dry = stream.dry()
    water = stream.water_ppm_mol()
    p_top = max(s.pressure_bara for s in stations) + 50.0
    for s in stations:
        system = _phases(dry, s.temperature_c, s.pressure_bara)
        s.phases = int(system.getNumberOfPhases())
        s.density_kg_m3 = float(system.getDensity("kg/m3"))
        s.two_phase_boundary_bara = two_phase_boundary_bara(dry, s.temperature_c, p_top)
        if math.isfinite(s.two_phase_boundary_bara):
            s.single_phase_margin_bar = s.pressure_bara - s.two_phase_boundary_bara
        s.water_solubility_ppm_mol = water_solubility_ppm_mol(
            dry, s.temperature_c, s.pressure_bara
        )
        if water > 0 and math.isfinite(s.water_solubility_ppm_mol):
            s.water_margin_factor = s.water_solubility_ppm_mol / water
    coldest = min(stations, key=lambda s: s.temperature_c)
    highest = max(stations, key=lambda s: s.pressure_bara)
    depressurisation = [_depressurise(stream, highest, "highest pressure")]
    if coldest is not highest:
        depressurisation.append(_depressurise(stream, coldest, "coldest point"))
    impurities = _impurities(stream, coldest)
    well_result = _well(stream, stations[-1], pipe, well) if well is not None else None
    report = ChainReport(stations, depressurisation, impurities, well_result)
    _findings(report, stream, limits)
    return report


def _impurities(stream: Co2Stream, station: Station) -> dict[str, Any] | None:
    j = _j()
    model = j.process.corrosion.DensePhaseCO2Corrosion()
    model.setTemperatureC(float(station.temperature_c))
    model.setPressureBara(float(station.pressure_bara))
    model.setCo2PurityMolPct(float(stream.co2_fraction() * 100))
    model.setWaterContentPpmv(float(stream.water_ppm_mol()))
    model.setO2ContentPpmv(float(stream.fraction("oxygen") * 1e6))
    model.setH2sContentPpmv(float(stream.fraction("H2S") * 1e6))
    model.setH2ContentMolPct(float(stream.fraction("hydrogen") * 100))
    model.setN2ContentMolPct(float(stream.fraction("nitrogen") * 100))
    model.setArContentMolPct(float(stream.fraction("argon") * 100))
    model.setSo2ContentPpmv(float(stream.so2_ppmv))
    model.setNoxContentPpmv(float(stream.nox_ppmv))
    model.evaluate()
    return json.loads(str(model.toJson()))


def _findings(report: ChainReport, stream: Co2Stream, limits: ChainLimits) -> None:
    f = report.findings
    st = report.stations
    two_phase = [s for s in st if s.phases > 1]
    margins = [s for s in st if math.isfinite(s.single_phase_margin_bar)]
    worst = min(margins, key=lambda s: s.single_phase_margin_bar) if margins else None
    report.summary = {
        "co2_mol_pct": stream.co2_fraction() * 100,
        "water_ppm_mol": stream.water_ppm_mol(),
        "arrival_pressure_bara": st[-1].pressure_bara,
        "arrival_temperature_c": st[-1].temperature_c,
        "min_single_phase_margin_bar": worst.single_phase_margin_bar if worst else NAN,
        "min_water_margin_factor": min(
            (s.water_margin_factor for s in st if math.isfinite(s.water_margin_factor)),
            default=NAN,
        ),
        "min_depressurisation_temperature_c": min(
            min(d["isenthalpic_final_c"], d["isentropic_final_c"])
            for d in report.depressurisation
        ),
    }
    if two_phase:
        f.append(
            Finding(
                "high",
                "two-phase-flow",
                f"The stream is two-phase at {len(two_phase)} of {len(st)} stations "
                f"(first at {two_phase[0].distance_m / 1000:.1f} km). Raise the inlet "
                "pressure or tighten the light-impurity (N2, H2, Ar, CH4) specification.",
            )
        )
    elif worst and worst.single_phase_margin_bar < limits.min_single_phase_margin_bar:
        f.append(
            Finding(
                "warning",
                "single-phase-margin",
                f"Margin to the two-phase boundary falls to "
                f"{worst.single_phase_margin_bar:.1f} bar at {worst.distance_m / 1000:.1f} km "
                f"(limit {limits.min_single_phase_margin_bar:g} bar).",
            )
        )
    wet = [
        s
        for s in st
        if math.isfinite(s.water_margin_factor) and s.water_margin_factor < 1.0
    ]
    tight = [
        s
        for s in st
        if math.isfinite(s.water_margin_factor)
        and 1.0 <= s.water_margin_factor < limits.water_margin_factor
    ]
    if wet:
        f.append(
            Finding(
                "high",
                "free-water",
                f"Water content {stream.water_ppm_mol():.0f} ppm(mol) exceeds the solubility "
                f"at {len(wet)} stations: free water forms, and wet CO2 is severely "
                "corrosive to carbon steel. Tighten dehydration.",
            )
        )
    elif tight:
        f.append(
            Finding(
                "warning",
                "water-margin",
                f"Water solubility is less than {limits.water_margin_factor:g} times the "
                f"water content at {len(tight)} stations.",
            )
        )
    impurities = report.impurities or {}
    issues = impurities.get("impurityIssues") or []
    if issues:
        f.append(
            Finding(
                "warning",
                "impurity-specification",
                "NeqSim DensePhaseCO2Corrosion: " + "; ".join(map(str, issues)) + ".",
            )
        )
    t_min = report.summary["min_depressurisation_temperature_c"]
    if math.isfinite(t_min):
        if t_min < CO2_TRIPLE_POINT_C:
            f.append(
                Finding(
                    "high",
                    "dry-ice",
                    f"Depressurisation to atmosphere cools to {t_min:.0f} C, below the CO2 "
                    f"triple point ({CO2_TRIPLE_POINT_C} C at {CO2_TRIPLE_POINT_BAR} bara): "
                    "solid CO2 forms. Design vents and blowdown to avoid blockage; the "
                    "Peng-Robinson flash does not model the solid, so the true minimum "
                    "temperature is near the triple point.",
                )
            )
        if t_min < limits.min_design_temperature_c:
            f.append(
                Finding(
                    "high",
                    "below-design-temperature",
                    f"Depressurisation temperature {max(t_min, CO2_TRIPLE_POINT_C):.0f} C "
                    f"is below the minimum design temperature "
                    f"{limits.min_design_temperature_c:g} C. Check low-temperature "
                    "toughness of pipe, valves and vent lines.",
                )
            )
    if limits.maop_bara is not None:
        high = max(s.pressure_bara for s in st)
        if high > limits.maop_bara:
            f.append(
                Finding(
                    "high",
                    "above-maop",
                    f"Pressure {high:.0f} bara exceeds MAOP {limits.maop_bara:g} bara.",
                )
            )
    well = report.well
    if well:
        margin = well.get("injectivity_margin_bar", NAN)
        if math.isfinite(margin) and margin <= 0:
            f.append(
                Finding(
                    "high",
                    "no-injectivity",
                    f"Bottom-hole pressure {well['bhp_bara']:.0f} bara does not exceed the "
                    f"reservoir pressure (margin {margin:.0f} bar). Raise arrival pressure "
                    "or add booster pumping.",
                )
            )
        fracture = well.get("fracture_margin_bar")
        if fracture is not None and fracture <= 0:
            f.append(
                Finding(
                    "high",
                    "above-fracture-pressure",
                    f"Bottom-hole pressure exceeds the fracture pressure by {-fracture:.0f} bar: "
                    "the dense CO2 column adds a large static head. Choke the arrival "
                    "pressure at the wellhead (check Joule-Thomson cooling and two-phase "
                    "flow below the choke) or lower the pipeline operating pressure.",
                )
            )
        if not well.get("safe_to_operate", True):
            f.append(
                Finding(
                    "warning",
                    "well-analyzer",
                    "NeqSim CO2InjectionWellAnalyzer reports the well as not safe to operate "
                    "(two-phase flow, impurity enrichment or shutdown issue); see "
                    "report.well['analyzer'].",
                )
            )
