"""Corrections and companion mechanisms for the CO2 corrosion profile.

* :func:`glycol_factor` - glycol (MEG/DEG/TEG) correction to the CO2 rate, as
  in NeqSim ``NorsokM506CorrosionRate#calculateGlycolCorrectionFactor``.
* :func:`condensation_rates` and :func:`tlc_risk` - top-of-line corrosion
  screening from the water condensation rate between stations.
* :func:`sour_regime` - CO2/H2S corrosion regime from the partial-pressure
  ratio, and :func:`iso15156_region` (NeqSim ``SourServiceAssessment``).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

ISO15156_H2S_THRESHOLD_BAR = 0.003  # 0.3 kPa
TLC_CRITICAL_G_M2_S = 0.25
TLC_ELEVATED_G_M2_S = 0.15
STRATIFIED_REGIMES = (
    "SEGREGATED",
    "STRATIFIED",
    "STRATIFIED_SMOOTH",
    "STRATIFIED_WAVY",
)


def glycol_factor(glycol_weight_fraction: float) -> float:
    """Multiplier on the CO2 rate for glycol in the water phase.

    ``1 - w`` below 50 wt %, ``0.5 (1 - w)^2 + 0.05`` from 50 to 80 wt %, and
    0.05 above. The same piecewise function as NeqSim
    ``NorsokM506CorrosionRate#calculateGlycolCorrectionFactor``; NeqSim's own
    method is used when available.
    """
    w = glycol_weight_fraction
    if not math.isfinite(w) or w <= 0.0:
        return 1.0
    try:
        from neqsim import jneqsim
    except ImportError:
        jneqsim = None
    if jneqsim is not None:
        model = jneqsim.process.corrosion.NorsokM506CorrosionRate()
        model.setGlycolWeightFraction(float(min(w, 0.99)))
        return float(model.calculateGlycolCorrectionFactor())
    if w >= 0.80:
        return 0.05
    if w >= 0.50:
        return 0.5 * (1.0 - w) ** 2 + 0.05
    return 1.0 - w


def condensation_rates(
    distances_m: Sequence[float],
    water_vapour_mass_fractions: Sequence[float],
    mass_flow_kg_h: float,
    inner_diameter_m: float,
) -> list[float]:
    """Water condensation rate on the pipe wall, g/m2/s, per station.

    The water carried as vapour (kg per kg of stream, from the flash) times the
    mass flow gives the vapour flow; its drop between two stations, spread over
    the inner wall area between them, is the condensation rate assigned to the
    downstream station. The first station gets 0. Negative values
    (evaporation) are reported as 0.
    """
    if mass_flow_kg_h <= 0 or inner_diameter_m <= 0:
        raise ValueError("mass flow and diameter must be > 0")
    rates = [0.0]
    flow_kg_s = mass_flow_kg_h / 3600.0
    for i in range(1, len(distances_m)):
        length = distances_m[i] - distances_m[i - 1]
        before, after = (
            water_vapour_mass_fractions[i - 1],
            water_vapour_mass_fractions[i],
        )
        if length <= 0 or not (math.isfinite(before) and math.isfinite(after)):
            rates.append(math.nan)
            continue
        condensed_kg_s = max(before - after, 0.0) * flow_kg_s
        area = math.pi * inner_diameter_m * length
        rates.append(condensed_kg_s * 1000.0 / area)
    return rates


def tlc_risk(condensation_g_m2_s: float, flow_regime: str | None) -> str | None:
    """Top-of-line corrosion risk: ``high``, ``moderate``, ``low`` or None.

    Uses the commonly applied critical condensation rate of 0.25 g/m2/s
    (0.15 g/m2/s as an elevated band). TLC needs stratified flow, where the top
    of the pipe is not wetted by the inhibited liquid; for other known regimes
    the risk is ``low``. An unknown regime is treated as stratified.
    """
    if not math.isfinite(condensation_g_m2_s) or condensation_g_m2_s <= 0:
        return None
    regime = (flow_regime or "").upper()
    stratified = not regime or any(tag in regime for tag in STRATIFIED_REGIMES)
    if not stratified:
        return "low"
    if condensation_g_m2_s > TLC_CRITICAL_G_M2_S:
        return "high"
    if condensation_g_m2_s > TLC_ELEVATED_G_M2_S:
        return "moderate"
    return "low"


def sour_regime(co2_partial_bar: float, h2s_partial_bar: float) -> str:
    """CO2/H2S corrosion regime from the partial-pressure ratio.

    ``sweet`` when H2S is below the ISO 15156 threshold (0.003 bar) or
    pCO2/pH2S > 500; ``mixed`` for a ratio of 20-500; ``sour`` below 20, where
    iron-sulfide films control corrosion and NORSOK M-506 no longer applies.
    Ratio bands as commonly used for screening (e.g. Pots et al., 2002).
    """
    if h2s_partial_bar < ISO15156_H2S_THRESHOLD_BAR:
        return "sweet"
    ratio = co2_partial_bar / h2s_partial_bar
    if ratio > 500:
        return "sweet"
    if ratio >= 20:
        return "mixed"
    return "sour"


def iso15156_region(
    h2s_partial_bar: float,
    co2_partial_bar: float,
    total_pressure_bar: float,
    in_situ_ph: float,
    temperature_c: float,
    chloride_mg_l: float,
    material: str,
) -> dict | None:
    """ISO 15156-2 sour region and risk from NeqSim ``SourServiceAssessment``.

    Returns None when NeqSim is not available.
    """
    try:
        from neqsim import jneqsim
    except ImportError:
        return None
    model = jneqsim.process.corrosion.SourServiceAssessment()
    model.setH2SPartialPressureBar(float(h2s_partial_bar))
    model.setCO2PartialPressureBar(float(co2_partial_bar))
    model.setTotalPressureBar(float(total_pressure_bar))
    model.setInSituPH(float(in_situ_ph))
    model.setTemperatureC(float(temperature_c))
    model.setChlorideConcentrationMgL(float(chloride_mg_l))
    model.setMaterialGrade(str(material))
    model.setFreeWaterPresent(True)
    model.evaluate()
    return {
        "region": int(model.getSourRegion()),
        "overall_risk": str(model.getOverallRiskLevel()),
        "ssc_risk": str(model.getSSCRiskLevel()),
        "hic_risk": str(model.getHICRiskLevel()),
        "recommended_material": str(model.getRecommendedMaterial()),
    }
