"""CO2 corrosion along a flowline profile, with a materials review.

For each station the NeqSim chemistry gives free water, in-situ pH and gas
CO2/H2S; the NORSOK M-506 Rev. 2 correlation gives the bare-steel rate; a
user-stated inhibitor availability gives the design rate; and the design life
turns it into wall loss against the corrosion allowance. CO2-rich streams
(CCS, CO2 injection) are assessed with NeqSim ``DensePhaseCO2Corrosion``
instead, because M-506 does not cover dense CO2. The inlet, outlet and worst
station go through NeqSim ``MaterialsReviewEngine`` (NORSOK M-001 material
selection, sour service, chloride SCC, dense CO2 and other mechanisms), and a
NORSOK M-001 recommendation is also made from the Rev. 2 design rate.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from . import m506
from .mechanisms import (
    ISO15156_H2S_THRESHOLD_BAR,
    condensation_rates,
    glycol_factor,
    iso15156_region,
    sour_regime,
    tlc_risk,
)
from .model import (
    NAN,
    ChemistryModel,
    CorrosionFluid,
    CorrosionInputError,
    ProfilePoint,
    wall_shear_stress_pa,
)

SEVERITY_ORDER = ("info", "warning", "high")


@dataclass
class DesignBasis:
    """User-stated design assumptions.

    Attributes:
        design_life_years: Service life for wall-loss accumulation.
        corrosion_allowance_mm: Allowance on carbon steel, mm.
        inhibitor_availability: Fraction of time inhibition is effective, 0-1.
            0 means no credit for inhibition.
        inhibited_rate_mm_y: Rate while inhibited, mm/year (often 0.1).
        inner_diameter_m: Pipe inner diameter for shear and materials review.
        roughness_m: Wall roughness for shear stress.
        default_wall_shear_pa: Shear used where a station gives no flow data.
        existing_material: Material for the materials review.
        mass_flow_kg_h: Total mass rate, kg/h. Enables the top-of-line
            corrosion (condensation rate) screen.
        apply_glycol_correction: Reduce the rate for glycol in the water.
    """

    design_life_years: float = 25.0
    corrosion_allowance_mm: float = 3.0
    inhibitor_availability: float = 0.0
    inhibited_rate_mm_y: float = 0.1
    inner_diameter_m: float = 0.254
    roughness_m: float = 5e-5
    default_wall_shear_pa: float | None = None
    existing_material: str = "Carbon Steel"
    mass_flow_kg_h: float | None = None
    apply_glycol_correction: bool = True

    def __post_init__(self) -> None:
        if self.design_life_years <= 0 or self.corrosion_allowance_mm < 0:
            raise CorrosionInputError("design life must be > 0 and allowance >= 0")
        if not 0.0 <= self.inhibitor_availability <= 1.0:
            raise CorrosionInputError("inhibitor_availability must be 0-1")
        if self.inhibited_rate_mm_y < 0 or self.inner_diameter_m <= 0:
            raise CorrosionInputError("inhibited rate >= 0 and diameter > 0")

    def design_rate(self, bare_rate_mm_y: float) -> float:
        """Rate with inhibitor availability: A*min(CR_inh, CR) + (1-A)*CR."""
        a = self.inhibitor_availability
        return (
            a * min(self.inhibited_rate_mm_y, bare_rate_mm_y) + (1 - a) * bare_rate_mm_y
        )


@dataclass
class StationResult:
    """Corrosion result at one profile station."""

    distance_m: float
    pressure_bara: float
    temperature_c: float
    free_water: bool
    in_situ_ph: float = NAN
    ph_source: str = ""
    gas_co2_mole_fraction: float = NAN
    gas_h2s_mole_fraction: float = NAN
    co2_fugacity_bar: float = NAN
    wall_shear_pa: float = NAN
    bare_rate_mm_y: float = 0.0
    design_rate_mm_y: float = 0.0
    wall_loss_mm: float = 0.0
    rate_upper_bound_only: bool = False
    glycol_weight_fraction: float = 0.0
    glycol_factor: float = 1.0
    water_vapour_mass_fraction: float = NAN
    condensation_g_m2_s: float = NAN
    tlc_risk: str | None = None
    h2s_partial_pressure_bar: float = NAN
    sour_regime: str | None = None
    iso15156: dict[str, Any] | None = None
    flow_regime: str | None = None
    dense_phase: dict[str, Any] | None = None
    flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Finding:
    """One observation from the assessment."""

    severity: str
    code: str
    message: str


@dataclass
class CorrosionProfileReport:
    """Result of :func:`assess_corrosion_profile`."""

    stations: list[StationResult]
    basis: DesignBasis
    rate_engine: str
    mode: str
    findings: list[Finding] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    materials_review: dict[str, Any] | None = None
    m001_recommendation: dict[str, Any] | None = None

    @property
    def highest_severity(self) -> str:
        """``high``, ``warning``, ``info`` or ``none``."""
        for level in reversed(SEVERITY_ORDER):
            if any(f.severity == level for f in self.findings):
                return level
        return "none"

    def worst_station(self) -> StationResult | None:
        """Station with the highest design rate (None when all are dry)."""
        wet = [s for s in self.stations if s.design_rate_mm_y > 0]
        return max(wet, key=lambda s: s.design_rate_mm_y) if wet else None

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
                "mode": self.mode,
                "rate_engine": self.rate_engine,
                "basis": asdict(self.basis),
                "highest_severity": self.highest_severity,
                "summary": self.summary,
                "findings": [asdict(f) for f in self.findings],
                "stations": [asdict(s) for s in self.stations],
                "m001_recommendation": self.m001_recommendation,
                "materials_review": self.materials_review,
            }
        )

    def to_markdown(self) -> str:
        """Short report: summary, findings, materials, station table."""
        s = self.summary
        lines = [
            "# CO2 corrosion profile",
            "",
            (
                f"Mode: {self.mode}. Rate model: {self.rate_engine}. Design life "
                f"{self.basis.design_life_years:g} years, corrosion allowance "
                f"{self.basis.corrosion_allowance_mm:g} mm, inhibitor availability "
                f"{self.basis.inhibitor_availability:.0%}. Screening-level result."
            ),
            "",
            "## Summary",
            "",
        ]
        for key, label in (
            ("max_design_rate_mm_y", "Maximum design rate (mm/year)"),
            ("max_rate_distance_m", "At distance (m)"),
            ("max_wall_loss_mm", "Maximum wall loss over design life (mm)"),
            ("required_allowance_mm", "Corrosion allowance needed (mm)"),
            ("wet_length_fraction", "Share of stations with free water"),
        ):
            if key in s and s[key] is not None:
                value = s[key]
                text = f"{value:.2f}" if isinstance(value, float) else str(value)
                lines.append(f"- {label}: {text}")
        lines += ["", "## Findings", ""]
        if not self.findings:
            lines.append("- None.")
        for f in self.findings:
            lines.append(f"- **{f.severity.upper()}** `{f.code}`: {f.message}")
        if self.m001_recommendation:
            m = self.m001_recommendation
            lines += [
                "",
                "## Material recommendation (NORSOK M-001, from the Rev. 2 design rate)",
                "",
                (
                    f"- {m.get('recommended_material')}, corrosion allowance "
                    f"{m.get('recommended_allowance_mm')} mm "
                    f"({m.get('service_category')})"
                ),
            ]
        if self.materials_review:
            lines += ["", "## Materials review (NeqSim MaterialsReviewEngine)", ""]
            for item in self.materials_review.get("items", []):
                tag = item.get("item", {}).get("tag", "?")
                lines.append(f"- **{tag}**: {item.get('verdict')}")
                for mech in item.get("damageMechanisms", []):
                    if mech.get("status") in ("FAIL", "WARNING"):
                        lines.append(
                            f"  - {mech.get('mechanism')} ({mech.get('standard')}): "
                            f"{mech.get('status')} - {mech.get('message')}"
                        )
        lines += [
            "",
            "## Stations",
            "",
            (
                "| km | P (bara) | T (C) | Water | pH | fCO2 (bar) | Shear (Pa) | "
                "Bare (mm/y) | Design (mm/y) | Loss (mm) | Cond (g/m2/s) | Regime "
                "| Flags |"
            ),
            (
                "| ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: "
                "| ---: | --- | --- |"
            ),
        ]

        def fmt(value: float, digits: int = 2) -> str:
            return f"{value:.{digits}f}" if math.isfinite(value) else "-"

        for st in self.stations:
            lines.append(
                f"| {st.distance_m / 1000:.2f} | {fmt(st.pressure_bara, 1)} | "
                f"{fmt(st.temperature_c, 1)} | {'yes' if st.free_water else 'no'} | "
                f"{fmt(st.in_situ_ph)} | {fmt(st.co2_fugacity_bar)} | "
                f"{fmt(st.wall_shear_pa, 1)} | {fmt(st.bare_rate_mm_y)} | "
                f"{fmt(st.design_rate_mm_y)} | {fmt(st.wall_loss_mm)} | "
                f"{fmt(st.condensation_g_m2_s, 3)} | {st.sour_regime or '-'} | "
                f"{len(st.flags) or ''} |"
            )
        return "\n".join(lines) + "\n"


def _shear(point: ProfilePoint, basis: DesignBasis) -> tuple[float, list[str]]:
    if point.wall_shear_pa is not None:
        return float(point.wall_shear_pa), []
    if None not in (
        point.mixture_velocity_m_s,
        point.mixture_density_kg_m3,
        point.mixture_viscosity_pa_s,
    ):
        tau = wall_shear_stress_pa(
            point.mixture_velocity_m_s,
            point.mixture_density_kg_m3,
            point.mixture_viscosity_pa_s,
            basis.inner_diameter_m,
            basis.roughness_m,
        )
        if math.isfinite(tau):
            return tau, []
    if basis.default_wall_shear_pa is not None:
        return basis.default_wall_shear_pa, ["shear from default_wall_shear_pa"]
    raise CorrosionInputError(
        f"station at {point.distance_m:.0f} m has no flow data or wall_shear_pa; "
        "set DesignBasis.default_wall_shear_pa"
    )


def _dense_phase(fluid: CorrosionFluid, point: ProfilePoint, basis: DesignBasis):
    from .model import _jneqsim

    j = _jneqsim()
    model = j.process.corrosion.DensePhaseCO2Corrosion()
    model.setTemperatureC(float(point.temperature_c))
    model.setPressureBara(float(point.pressure_bara))
    model.setCo2PurityMolPct(float(fluid.dry_co2_fraction() * 100))
    dry_total = fluid.total() - fluid.components.get("water", 0.0)
    model.setWaterContentPpmv(float(fluid.components["water"] / dry_total * 1e6))
    model.setH2sContentPpmv(float(fluid.components.get("H2S", 0.0) / dry_total * 1e6))
    model.setH2ContentMolPct(
        float(fluid.components.get("hydrogen", 0.0) / dry_total * 100)
    )
    model.setN2ContentMolPct(
        float(fluid.components.get("nitrogen", 0.0) / dry_total * 100)
    )
    model.setArContentMolPct(
        float(fluid.components.get("argon", 0.0) / dry_total * 100)
    )
    impurities = fluid.dense_phase_impurities_ppmv
    model.setO2ContentPpmv(float(impurities.get("O2", 0.0)))
    model.setSo2ContentPpmv(float(impurities.get("SO2", 0.0)))
    model.setNoxContentPpmv(float(impurities.get("NOx", 0.0)))
    model.setMaterialType(basis.existing_material)
    model.evaluate()
    return (
        json.loads(str(model.toJson())),
        bool(model.isFreeWaterRisk()),
        float(model.getWetCorrosionRateMmYr()),
    )


def assess_corrosion_profile(
    fluid: CorrosionFluid,
    profile: Sequence[ProfilePoint],
    basis: DesignBasis,
    chemistry: ChemistryModel | None = None,
    materials_review: bool = True,
    co2_rich_threshold: float = 0.5,
) -> CorrosionProfileReport:
    """Corrosion rates along a flowline and a materials review.

    Args:
        fluid: The stream, with water (and chloride if produced water).
        profile: Stations from :func:`neqsim_pipeline_profile` or your own.
        basis: Design life, allowance, inhibition and pipe data.
        chemistry: Chemistry backend; defaults to :class:`NeqSimChemistry`.
        materials_review: Run NeqSim MaterialsReviewEngine and NORSOK M-001.
        co2_rich_threshold: Dry CO2 fraction above which the dense-phase
            assessment replaces M-506.

    Returns:
        A :class:`CorrosionProfileReport`.
    """
    if len(profile) < 1:
        raise CorrosionInputError("profile needs at least one station")
    dense = fluid.dry_co2_fraction() >= co2_rich_threshold
    if chemistry is None and not dense:
        from .model import NeqSimChemistry

        chemistry = NeqSimChemistry()
    stations: list[StationResult] = []
    for point in sorted(profile, key=lambda p: p.distance_m):
        if dense:
            stations.append(_dense_station(fluid, point, basis))
        else:
            stations.append(_m506_station(fluid, point, basis, chemistry))
    if basis.mass_flow_kg_h and not dense:
        rates = condensation_rates(
            [s.distance_m for s in stations],
            [s.water_vapour_mass_fraction for s in stations],
            basis.mass_flow_kg_h,
            basis.inner_diameter_m,
        )
        for station, rate in zip(stations, rates):
            station.condensation_g_m2_s = rate
            station.tlc_risk = tlc_risk(rate, station.flow_regime)
    report = CorrosionProfileReport(
        stations=stations,
        basis=basis,
        rate_engine="NeqSim DensePhaseCO2Corrosion" if dense else m506.engine_name(),
        mode="dense-phase CO2" if dense else "NORSOK M-506 Rev. 2",
    )
    _summarise(report)
    if materials_review:
        _materials(report, fluid)
    return report


def _m506_station(
    fluid: CorrosionFluid,
    point: ProfilePoint,
    basis: DesignBasis,
    chemistry: ChemistryModel,
) -> StationResult:
    chem = chemistry.evaluate(fluid, point.pressure_bara, point.temperature_c)
    station = StationResult(
        distance_m=point.distance_m,
        pressure_bara=point.pressure_bara,
        temperature_c=point.temperature_c,
        free_water=chem.free_water,
        in_situ_ph=chem.in_situ_ph,
        ph_source=chem.ph_source,
        gas_co2_mole_fraction=chem.gas_co2_mole_fraction,
        gas_h2s_mole_fraction=chem.gas_h2s_mole_fraction,
        flow_regime=point.flow_regime,
        flags=list(chem.notes),
        glycol_weight_fraction=chem.glycol_weight_fraction,
        water_vapour_mass_fraction=chem.water_vapour_mass_fraction,
    )
    if not chem.free_water:
        station.flags.append("no free water: no CO2 corrosion")
        return station
    if chem.gas_co2_mole_fraction <= 0:
        station.flags.append("no CO2 in the gas phase")
        return station
    shear, notes = _shear(point, basis)
    station.flags += notes
    if chem.has_gas_phase:
        rate = m506.assess_rate(
            point.temperature_c,
            point.pressure_bara,
            chem.gas_co2_mole_fraction,
            chem.in_situ_ph,
            shear,
        )
    else:
        rate = m506.assess_rate_at_fugacity(
            point.temperature_c, chem.co2_fugacity_eos_bar, chem.in_situ_ph, shear
        )
    station.co2_fugacity_bar = rate.co2_fugacity_bar
    station.wall_shear_pa = shear
    station.bare_rate_mm_y = rate.rate_mm_y
    if basis.apply_glycol_correction and chem.glycol_weight_fraction > 0:
        station.glycol_factor = glycol_factor(chem.glycol_weight_fraction)
    station.design_rate_mm_y = basis.design_rate(rate.rate_mm_y * station.glycol_factor)
    station.wall_loss_mm = station.design_rate_mm_y * basis.design_life_years
    station.rate_upper_bound_only = rate.upper_bound_only
    station.flags += rate.flags
    p_h2s = chem.gas_h2s_mole_fraction * point.pressure_bara
    p_co2 = chem.gas_co2_mole_fraction * point.pressure_bara
    station.h2s_partial_pressure_bar = p_h2s
    station.sour_regime = sour_regime(p_co2, p_h2s)
    if p_h2s >= ISO15156_H2S_THRESHOLD_BAR:
        try:
            station.iso15156 = iso15156_region(
                p_h2s,
                p_co2,
                point.pressure_bara,
                station.in_situ_ph,
                point.temperature_c,
                fluid.chloride_mg_l,
                basis.existing_material,
            )
        except Exception as exc:  # noqa: BLE001
            station.flags.append(f"ISO 15156 check failed ({type(exc).__name__})")
    return station


def _dense_station(
    fluid: CorrosionFluid, point: ProfilePoint, basis: DesignBasis
) -> StationResult:
    data, water_risk, wet_rate = _dense_phase(fluid, point, basis)
    rate = wet_rate if water_risk else 0.0
    station = StationResult(
        distance_m=point.distance_m,
        pressure_bara=point.pressure_bara,
        temperature_c=point.temperature_c,
        free_water=water_risk,
        bare_rate_mm_y=rate,
        design_rate_mm_y=basis.design_rate(rate) if rate > 0 else 0.0,
        dense_phase=data,
        flow_regime=point.flow_regime,
    )
    station.wall_loss_mm = station.design_rate_mm_y * basis.design_life_years
    if not water_risk:
        station.flags.append("dense phase: water within solubility limit")
    return station


def _summarise(report: CorrosionProfileReport) -> None:
    stations, basis, findings = report.stations, report.basis, report.findings
    wet = [s for s in stations if s.free_water]
    worst = report.worst_station()
    report.summary = {
        "stations": len(stations),
        "wet_length_fraction": len(wet) / len(stations),
        "max_design_rate_mm_y": worst.design_rate_mm_y if worst else 0.0,
        "max_bare_rate_mm_y": max((s.bare_rate_mm_y for s in stations), default=0.0),
        "max_rate_distance_m": worst.distance_m if worst else None,
        "max_wall_loss_mm": worst.wall_loss_mm if worst else 0.0,
        "required_allowance_mm": worst.wall_loss_mm if worst else 0.0,
    }
    if report.mode.startswith("dense"):
        _dense_findings(report)
    if not wet:
        if report.mode.startswith("dense"):
            return
        findings.append(
            Finding(
                "info",
                "dry-line",
                "No free water at any station: no CO2 corrosion is predicted. Confirm "
                "the water dew-point margin, start-up and upset cases.",
            )
        )
        return
    first_wet = min(s.distance_m for s in wet)
    if 0 < first_wet:
        findings.append(
            Finding(
                "info",
                "water-dropout",
                f"Free water first appears at {first_wet / 1000:.2f} km; upstream "
                "stations are dry.",
            )
        )
    if worst is None:
        return
    over = [s for s in stations if s.wall_loss_mm > basis.corrosion_allowance_mm]
    if over:
        findings.append(
            Finding(
                "high",
                "allowance-exceeded",
                f"Wall loss over {basis.design_life_years:g} years exceeds the "
                f"{basis.corrosion_allowance_mm:g} mm allowance at {len(over)} of "
                f"{len(stations)} stations (worst {worst.wall_loss_mm:.1f} mm at "
                f"{worst.distance_m / 1000:.2f} km, design rate "
                f"{worst.design_rate_mm_y:.2f} mm/year). Options: inhibition with a "
                "stated availability, larger allowance, or corrosion-resistant alloy.",
            )
        )
    elif worst.wall_loss_mm > 0.8 * basis.corrosion_allowance_mm:
        findings.append(
            Finding(
                "warning",
                "allowance-margin",
                f"Wall loss uses {worst.wall_loss_mm / basis.corrosion_allowance_mm:.0%} "
                "of the corrosion allowance at the worst station.",
            )
        )
    bounded = [s for s in wet if s.rate_upper_bound_only]
    if bounded:
        findings.append(
            Finding(
                "info",
                "low-fugacity",
                f"CO2 fugacity is below 0.1 bar at {len(bounded)} wet stations; their "
                "rates are upper bounds from the edge of the correlation.",
            )
        )
    clamped = [
        s
        for s in wet
        if any("range" in f and "fugacity below" not in f for f in s.flags)
    ]
    if clamped:
        findings.append(
            Finding(
                "warning",
                "outside-correlation",
                f"Temperature, pH, fugacity or shear lies outside the M-506 Rev. 2 "
                f"range at {len(clamped)} stations; the nearest bound was used. See "
                "station flags.",
            )
        )
    _mechanism_findings(report, wet)


def _mechanism_findings(
    report: CorrosionProfileReport, wet: list[StationResult]
) -> None:
    findings = report.findings
    sour = [s for s in wet if s.h2s_partial_pressure_bar >= ISO15156_H2S_THRESHOLD_BAR]
    if sour:
        regions = sorted({s.iso15156["region"] for s in sour if s.iso15156})
        findings.append(
            Finding(
                "warning",
                "sour-service",
                f"H2S partial pressure is at or above 0.3 kPa (ISO 15156) at {len(sour)} "
                f"wet stations (max {max(s.h2s_partial_pressure_bar for s in sour) * 100:.2f}"
                " kPa)"
                + (
                    f"; ISO 15156-2 region {', '.join(map(str, regions))}"
                    if regions
                    else ""
                )
                + ". Carbon steel needs sour-service qualification (hardness, HIC).",
            )
        )
    regimes = {s.sour_regime for s in wet if s.sour_regime}
    if regimes & {"mixed", "sour"}:
        worst = "sour" if "sour" in regimes else "mixed"
        findings.append(
            Finding(
                "high" if worst == "sour" else "warning",
                "h2s-regime",
                f"pCO2/pH2S indicates {worst} corrosion at some stations"
                + (
                    " (ratio < 20): iron-sulfide films control corrosion and NORSOK "
                    "M-506 does not apply there."
                    if worst == "sour"
                    else " (ratio 20-500): H2S modifies CO2 corrosion; treat M-506 "
                    "rates with caution."
                ),
            )
        )
    tlc = [s for s in report.stations if s.tlc_risk in ("high", "moderate")]
    if tlc:
        worst_tlc = max(tlc, key=lambda s: s.condensation_g_m2_s)
        level = "high" if any(s.tlc_risk == "high" for s in tlc) else "warning"
        findings.append(
            Finding(
                level,
                "top-of-line-corrosion",
                f"Water condenses at up to {worst_tlc.condensation_g_m2_s:.2f} g/m2/s "
                f"({worst_tlc.distance_m / 1000:.2f} km) in stratified or unknown flow, "
                f"above {'0.25' if level == 'high' else '0.15'} g/m2/s at {len(tlc)} "
                "stations. Continuous inhibitor injection does not protect the top of "
                "the line; consider insulation, pH stabilisation limits or CRA.",
            )
        )
    elif report.basis.mass_flow_kg_h is None and not report.mode.startswith("dense"):
        findings.append(
            Finding(
                "info",
                "tlc-not-assessed",
                "Top-of-line corrosion not screened: set DesignBasis.mass_flow_kg_h.",
            )
        )
    glycol = [s for s in wet if s.glycol_factor < 1.0]
    if glycol:
        findings.append(
            Finding(
                "info",
                "glycol-correction",
                f"Glycol in the water reduces the CO2 rate at {len(glycol)} stations "
                f"(factor {min(s.glycol_factor for s in glycol):.2f}-"
                f"{max(s.glycol_factor for s in glycol):.2f}).",
            )
        )


def _dense_findings(report: CorrosionProfileReport) -> None:
    stations = [s for s in report.stations if s.dense_phase]
    risky = [s for s in stations if s.free_water]
    if risky:
        report.findings.append(
            Finding(
                "high",
                "dense-phase-free-water",
                f"Free water can form at {len(risky)} of {len(stations)} stations of "
                "the CO2 line; wet dense-phase CO2 is severely corrosive to carbon "
                "steel. Tighten the water specification or dehydration.",
            )
        )
    issues = sorted(
        {issue for s in stations for issue in s.dense_phase.get("impurityIssues", [])}
    )
    if issues:
        report.findings.append(
            Finding(
                "warning",
                "dense-phase-impurities",
                "Impurity specification issues: " + "; ".join(issues) + ".",
            )
        )
    levels = [str(s.dense_phase.get("riskLevel", "")) for s in stations]
    phases = sorted({str(s.dense_phase.get("co2PhaseState", "")) for s in stations})
    report.findings.append(
        Finding(
            "info",
            "dense-phase-summary",
            f"CO2 phase along the line: {', '.join(phases)}; NeqSim risk levels: "
            f"{', '.join(sorted(set(levels)))}. DensePhaseCO2Corrosion is a "
            "screening heuristic, not DNV-RP-F104 conformity evidence.",
        )
    )


def _materials(report: CorrosionProfileReport, fluid: CorrosionFluid) -> None:
    from .model import _jneqsim

    try:
        j = _jneqsim()
    except Exception as exc:  # noqa: BLE001
        report.findings.append(
            Finding("info", "materials-review-skipped", f"NeqSim unavailable: {exc}")
        )
        return
    stations = report.stations
    worst = report.worst_station()
    picks = {"inlet": stations[0], "outlet": stations[-1]}
    if worst is not None:
        picks["worst"] = worst
    basis = report.basis
    items, seen = [], set()
    for label, st in picks.items():
        if id(st) in seen:
            continue
        seen.add(id(st))
        items.append(
            {
                "tag": f"{label} {st.distance_m / 1000:.2f} km",
                "equipmentType": "Pipeline",
                "existingMaterial": basis.existing_material,
                "service": {
                    "temperature_C": st.temperature_c,
                    "pressure_bara": st.pressure_bara,
                    "co2_mole_fraction": (
                        st.gas_co2_mole_fraction
                        if math.isfinite(st.gas_co2_mole_fraction)
                        else fluid.dry_co2_fraction()
                    ),
                    "h2s_mole_fraction": (
                        st.gas_h2s_mole_fraction
                        if math.isfinite(st.gas_h2s_mole_fraction)
                        else 0.0
                    ),
                    "free_water": st.free_water,
                    "pH": st.in_situ_ph if math.isfinite(st.in_situ_ph) else 6.5,
                    "chloride_mg_per_l": fluid.chloride_mg_l,
                    "bicarbonate_mg_per_l": fluid.bicarbonate_mg_l,
                    "pipe_diameter_m": basis.inner_diameter_m,
                    "inhibitor_efficiency": 0.0,
                    "design_life_years": basis.design_life_years,
                },
                "m506Rev2DesignRate_mm_per_year": st.design_rate_mm_y,
            }
        )
    payload = {
        "projectName": "co2-corrosion-profile",
        "designLifeYears": basis.design_life_years,
        "items": items,
    }
    try:
        engine_input = j.process.materials.MaterialsReviewInput.fromJson(
            json.dumps(payload)
        )
        review = j.process.materials.MaterialsReviewEngine().evaluate(engine_input)
        report.materials_review = json.loads(str(review.toJson()))
    except Exception as exc:  # noqa: BLE001
        report.findings.append(
            Finding("info", "materials-review-failed", f"{type(exc).__name__}: {exc}")
        )
    if worst is None:
        return
    try:
        sel = j.process.corrosion.NorsokM001MaterialSelection()
        sel.setCO2CorrosionRateMmyr(float(worst.design_rate_mm_y))
        sel.setH2SPartialPressureBar(
            float(max(worst.gas_h2s_mole_fraction, 0.0) * worst.pressure_bara)
        )
        sel.setDesignTemperatureC(float(max(s.temperature_c for s in stations)))
        sel.setMaxDesignTemperatureC(float(max(s.temperature_c for s in stations)))
        sel.setChlorideConcentrationMgL(float(fluid.chloride_mg_l))
        sel.setDesignLifeYears(float(basis.design_life_years))
        sel.setAqueousPH(
            float(worst.in_situ_ph if math.isfinite(worst.in_situ_ph) else 6.5)
        )
        sel.setCO2PartialPressureBar(
            float(max(worst.gas_co2_mole_fraction, 0.0) * worst.pressure_bara)
        )
        sel.setFreeWaterPresent(True)
        sel.evaluate()
        report.m001_recommendation = {
            "recommended_material": str(sel.getRecommendedMaterial()),
            "recommended_allowance_mm": float(sel.getRecommendedCorrosionAllowanceMm()),
            "service_category": str(sel.getServiceCategory()),
            "alternatives": [str(a) for a in sel.getAlternativeMaterials()],
            "notes": [str(n) for n in sel.getNotes()],
            "design_rate_mm_y": worst.design_rate_mm_y,
        }
    except Exception as exc:  # noqa: BLE001
        report.findings.append(
            Finding("info", "m001-selection-failed", f"{type(exc).__name__}: {exc}")
        )
    review = report.materials_review or {}
    for item in review.get("items", []):
        if item.get("verdict") == "FAIL":
            failing = [
                m.get("mechanism")
                for m in item.get("damageMechanisms", [])
                if m.get("status") == "FAIL"
            ]
            report.findings.append(
                Finding(
                    "warning",
                    "materials-review-fail",
                    f"MaterialsReviewEngine: {item.get('item', {}).get('tag')} fails "
                    f"for {', '.join(failing)}. Its CO2 rate uses NeqSim's legacy "
                    "de Waard-Milliams model; the Rev. 2 design rate is in the "
                    "station table.",
                )
            )
