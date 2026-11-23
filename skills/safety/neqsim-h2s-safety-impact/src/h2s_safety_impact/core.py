"""Screening calculations for the safety impact of H2S in produced gas.

Everything here is a SCREENING estimate. Limits are arguments with a named source: the library does not claim that a standard is
met. Results carry an evidence status (``evidence_gate``): without a measured H2S value at the sample point the result is UNVERIFIED
and missing inputs are reported as data gaps, never as a pass.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from typing import Any

MW_H2S = 34.081
MW_SO2 = 64.066
#: mg H2S per normal cubic metre (0 C, 1.01325 bara) for one ppm by mole.
MG_PER_NM3_PER_PPM = MW_H2S / 22.414
#: Sm3 per kmol at 15 C and 1 atm.
SM3_PER_KMOL = 23.64
_R = 8.314462


def ppm_to_mg_nm3(ppm: float) -> float:
    """Convert ppm by mole of H2S in gas to mg per normal cubic metre (0 C, 1.01325 bara)."""
    return ppm * MG_PER_NM3_PER_PPM


def mg_nm3_to_ppm(mg_nm3: float) -> float:
    """Convert mg H2S per normal cubic metre (0 C, 1.01325 bara) to ppm by mole."""
    return mg_nm3 / MG_PER_NM3_PER_PPM


def ppm_to_kg_m3(
    ppm: float, temperature_c: float = 20.0, pressure_bara: float = 1.01325
) -> float:
    """H2S mass concentration in air [kg/m3] for a mole fraction in ppm at the given temperature and pressure (ideal gas)."""
    return (
        ppm
        * 1.0e-6
        * (MW_H2S * 1.0e-3)
        * (pressure_bara * 1.0e5)
        / (_R * (temperature_c + 273.15))
    )


def partial_pressure_kpa(y_ppm: float, p_bara: float) -> float:
    """H2S partial pressure [kPa] of a gas phase with y_ppm (mole) at p_bara."""
    if y_ppm < 0 or p_bara <= 0:
        raise ValueError("y_ppm must be >= 0 and p_bara > 0")
    return y_ppm * 1.0e-6 * p_bara * 100.0


def ppm_for_partial_pressure(pp_kpa: float, p_bara: float) -> float:
    """H2S ppm (mole) in the gas that gives the partial pressure pp_kpa at p_bara."""
    if pp_kpa < 0 or p_bara <= 0:
        raise ValueError("pp_kpa must be >= 0 and p_bara > 0")
    return pp_kpa / (p_bara * 100.0) * 1.0e6


def sour_service_screen(
    y_ppm: float,
    p_bara: float,
    threshold_kpa: float = 0.3,
    borderline_ratio: float = 1.0 / 3.0,
    source: str = "convention, standard text not read",
) -> dict[str, Any]:
    """Compare the H2S partial pressure of a gas phase with a sour-service threshold.

    Args:
        y_ppm: H2S in the gas phase [ppm mole].
        p_bara: Total pressure of the location [bara].
        threshold_kpa: Partial-pressure threshold [kPa]; 0.3 kPa is the conventional ISO 15156-2 / NACE MR0175 value. Pass the
            value of the governing document you actually read, and name it in ``source``.
        borderline_ratio: Ratio of partial pressure to threshold from which the result is called borderline. A factor 3 is the
            typical uncertainty of an H2S estimate without a measurement.
        source: Where the threshold comes from; echoed in the result.

    Returns:
        Partial pressure, ratio to threshold, flag (below, borderline, sour) and the H2S ppm that reaches the threshold.
    """
    pp = partial_pressure_kpa(y_ppm, p_bara)
    ratio = pp / threshold_kpa
    flag = (
        "sour"
        if ratio >= 1.0
        else ("borderline" if ratio >= borderline_ratio else "below")
    )
    return {
        "pp_kpa": pp,
        "threshold_kpa": threshold_kpa,
        "ratio": ratio,
        "flag": flag,
        "ppm_for_threshold": ppm_for_partial_pressure(threshold_kpa, p_bara),
        "threshold_source": source,
    }


def detector_equivalence(
    y_gas_ppm: float,
    lfl_vol_frac: float,
    lel_alarm_frac: float = 0.2,
    h2s_alarm_ppm: float = 5.0,
    omit_below_ppm: float | None = 1500.0,
) -> dict[str, Any]:
    """H2S concentration in air that goes with a flammable-gas alarm, and whether the hydrocarbon detector covers H2S.

    Args:
        y_gas_ppm: H2S in the process gas [ppm mole].
        lfl_vol_frac: Lower flammable limit of the gas as a volume fraction (for example 0.04).
        lel_alarm_frac: Hydrocarbon gas alarm as a fraction of LEL (0.2 for 20 % LEL).
        h2s_alarm_ppm: H2S alarm set point [ppm].
        omit_below_ppm: Process-gas H2S below which dedicated H2S detectors may be omitted (1500 ppm is the NORSOK S-001
            clause text; pass None to disable the test).

    Returns:
        H2S in air at the gas alarm, the %LEL at which the H2S alarm would be reached, and a coverage flag.
    """
    air_ppm = y_gas_ppm * lfl_vol_frac * lel_alarm_frac
    lel_for_alarm = (
        h2s_alarm_ppm / (y_gas_ppm * lfl_vol_frac) if y_gas_ppm > 0 else float("inf")
    )
    needed = None if omit_below_ppm is None else y_gas_ppm >= omit_below_ppm
    return {
        "h2s_ppm_in_air_at_gas_alarm": air_ppm,
        "fraction_of_lel_at_h2s_alarm": lel_for_alarm,
        "h2s_alarm_reached_before_gas_alarm": lel_for_alarm <= lel_alarm_frac,
        "dedicated_h2s_detection_required": needed,
    }


def so2_emission_kg_h(gas_kg_h: float, y_ppm: float, gas_mw: float) -> float:
    """SO2 mass rate [kg/h] when a gas stream with y_ppm H2S is burned completely (flare, fuel gas)."""
    h2s_kg_h = gas_kg_h * y_ppm * 1.0e-6 * MW_H2S / gas_mw
    return h2s_kg_h * MW_SO2 / MW_H2S


def export_blend_ppm(streams: Sequence[tuple[float, float]]) -> float:
    """Mole-weighted H2S [ppm] of blended gas streams given as (standard volume rate, ppm)."""
    total = sum(r for r, _ in streams)
    if total <= 0:
        raise ValueError("total gas rate must be positive")
    return sum(r * y for r, y in streams) / total


def removal_and_scavenger(
    blend_ppm: float,
    limit_ppm: float,
    gas_sm3_d: float,
    kg_product_per_kg_h2s: float = 8.0,
) -> dict[str, float]:
    """H2S removal [kg/d] to meet a limit and the scavenger product demand [t/d] at an assumed consumption."""
    over = max(blend_ppm - limit_ppm, 0.0)
    kg_d = over * 1.0e-6 * gas_sm3_d / SM3_PER_KMOL * MW_H2S
    return {
        "removal_kg_d": kg_d,
        "scavenger_t_d": kg_d * kg_product_per_kg_h2s / 1000.0,
        "assumed_kg_product_per_kg_h2s": kg_product_per_kg_h2s,
    }


def vapour_ppm_over_water(
    aq_mg_l: float, temperature_c: float, pressure_bara: float = 1.01325
) -> float:
    """H2S in the vapour above water with aq_mg_l dissolved H2S (ideal Henry law, no ionisation, so a high estimate for alkaline water).

    Uses kH(25 C) = 0.102 mol/(L atm) and d ln kH / d(1/T) = 2100 K (Sander 2015, recalled; verify before design use).
    """
    t_k = temperature_c + 273.15
    kh = 0.102 * math.exp(2100.0 * (1.0 / t_k - 1.0 / 298.15))
    x_aq = (aq_mg_l * 1.0e-3 / MW_H2S) / 55.5
    k_gw = 55.5 / (kh * pressure_bara / 1.01325)
    return x_aq * k_gw * 1.0e6


def probit_h2s(c_ppm: float, t_min: float) -> tuple[float, float]:
    """H2S fatality probit Y = -31.42 + 3.008 ln(C^1.43 t) (C in ppm, t in min; CCPS form as in NeqSim ProbitModel) and probability."""
    if c_ppm <= 0 or t_min <= 0:
        return float("-inf"), 0.0
    y = -31.42 + 3.008 * math.log(c_ppm**1.43 * t_min)
    p = 0.5 * (1.0 + math.erf((y - 5.0) / math.sqrt(2.0)))
    return y, p


def toxic_reach(
    rate_kg_s: float,
    h2s_mass_fraction: float,
    thresholds_ppm: Mapping[str, float],
    plume_distance: Callable[[float, float], float],
    temperature_c: float = 20.0,
) -> dict[str, float]:
    """Downwind distance to H2S threshold concentrations for a release, from a plume model of the released material.

    Args:
        rate_kg_s: Release rate of the whole stream [kg/s].
        h2s_mass_fraction: Mass fraction of H2S in the released stream.
        thresholds_ppm: Named thresholds, for example {"alarm 5": 5, "ERPG-2": 30, "IDLH": 100}.
        plume_distance: Function (rate_kg_s, concentration_of_released_material_kg_m3) -> distance [m]. With NeqSim use
            ``GaussianPlume(...).distanceToConcentration`` of the chosen stability and wind.
        temperature_c: Air temperature for the ppm to kg/m3 conversion.

    Returns:
        Distance per threshold [m]; 0 when the undiluted stream is below the threshold.
    """
    out: dict[str, float] = {}
    for name, ppm in thresholds_ppm.items():
        if h2s_mass_fraction <= 0:
            out[name] = 0.0
            continue
        thr = ppm_to_kg_m3(ppm, temperature_c) / h2s_mass_fraction
        out[name] = float(plume_distance(rate_kg_s, thr))
    return out


def evidence_gate(evidence: str, inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Status of an H2S safety result from the quality of the H2S evidence; missing inputs become data gaps, never a pass.

    Args:
        evidence: ``measured`` (H2S measured in a sample of this reservoir with sample point and basis), ``analogue``,
            ``estimate`` (buffer or correlation) or ``none``.
        inputs: Input record; the keys listed in REQUIRED are checked for presence.

    Returns:
        status (VERIFIED_INPUT or UNVERIFIED_SCREENING), data_gaps (list of dicts) and the evidence class.
    """
    required = {
        "y_h2s_ppm": "H2S in gas at the stated basis",
        "basis": "sample point and basis (test separator, wellhead, stock tank; dry or wet; ppm mole or ppm weight)",
        "temperature_c": "reservoir or flowing temperature",
        "pressure_bara": "pressure of the location",
    }
    gaps = []
    for k, why in required.items():
        if inputs.get(k) in (None, ""):
            gaps.append(
                {
                    "gap": k,
                    "why": why,
                    "status": "OPEN",
                    "assumed": None,
                    "effect": "result cannot be used as a design basis",
                }
            )
    if evidence not in ("measured", "analogue", "estimate", "none"):
        raise ValueError("evidence must be measured, analogue, estimate or none")
    if evidence != "measured":
        gaps.append(
            {
                "gap": "measured H2S",
                "why": "no measurement in this reservoir; evidence is " + evidence,
                "status": "OPEN",
                "assumed": evidence,
                "effect": "all downstream numbers are screening values; sample at the next test",
            }
        )
    status = (
        "VERIFIED_INPUT"
        if evidence == "measured" and not gaps
        else "UNVERIFIED_SCREENING"
    )
    return {"status": status, "evidence": evidence, "data_gaps": gaps}


def h2s_safety_impact(case: Mapping[str, Any]) -> dict[str, Any]:
    """Run the screening for one case and return one record with the evidence status.

    Keys of ``case``: y_h2s_ppm, basis, temperature_c, pressure_bara, evidence (the five needed for the evidence gate) and, optionally,
    locations (name -> (ppm in gas, p_bara)), lfl_vol_frac, tie_in_gas_sm3_d, host_gas ((sm3_d, ppm)), export_limit_mg_nm3,
    threshold_kpa, threshold_source.
    """
    gate = evidence_gate(str(case.get("evidence", "none")), case)
    res: dict[str, Any] = {
        "gate": gate,
        "sour_service": {},
        "detector": None,
        "export": None,
    }
    for name, (y, p) in (case.get("locations") or {}).items():
        res["sour_service"][name] = sour_service_screen(
            y,
            p,
            case.get("threshold_kpa", 0.3),
            source=case.get("threshold_source", "convention, standard text not read"),
        )
    if case.get("lfl_vol_frac"):
        res["detector"] = detector_equivalence(case["y_h2s_ppm"], case["lfl_vol_frac"])
    if case.get("tie_in_gas_sm3_d") and case.get("host_gas"):
        host_rate, host_ppm = case["host_gas"]
        blend = export_blend_ppm(
            [(case["tie_in_gas_sm3_d"], case["y_h2s_ppm"]), (host_rate, host_ppm)]
        )
        lim = mg_nm3_to_ppm(case.get("export_limit_mg_nm3", 5.0))
        res["export"] = {
            "blend_ppm": blend,
            "limit_ppm": lim,
            "exceeds": blend > lim,
            **removal_and_scavenger(blend, lim, case["tie_in_gas_sm3_d"] + host_rate),
        }
    return res
