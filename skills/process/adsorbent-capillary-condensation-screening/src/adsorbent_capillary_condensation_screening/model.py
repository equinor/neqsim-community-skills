"""Screening model for capillary condensation of a contaminant in adsorbent pores.

Public, educational logic only. The Kelvin equation converts a sorbent pore
radius into the relative saturation at which liquid fills the pore, and hence
into a maximum tolerable contaminant concentration in the feed gas.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

R_GAS = 8.314462618
"""Universal gas constant in J/(mol K)."""

KELVIN_VALIDITY_RADIUS_NM = 2.0
"""Below this pore radius the continuum Kelvin equation is non-conservative."""


@dataclass
class CapillaryScreeningResult:
    """Result of a capillary condensation screening."""

    kelvin_length_nm: float
    onset_relative_saturation: float
    max_mole_fraction: float
    max_ppmv: float
    kelvin_valid: bool
    warning: str
    relative_saturation: Optional[float] = None
    margin_ratio: Optional[float] = None
    assumptions: List[str] = field(default_factory=list)


def micropore_filling_fraction(
    relative_saturation: float,
    temperature: float,
    characteristic_energy: float = 15000.0,
    affinity_coefficient: float = 1.0,
) -> float:
    """Dubinin-Radushkevich micropore volume filling fraction.

    :param relative_saturation: contaminant activity, 0 to 1.
    :param temperature: temperature in kelvin.
    :param characteristic_energy: DR characteristic energy in J/mol.
    :param affinity_coefficient: DR affinity coefficient relative to the reference vapour.
    :returns: fraction of micropore volume filled, 0 to 1.
    """
    if relative_saturation <= 0.0:
        return 0.0
    if relative_saturation >= 1.0:
        return 1.0
    adsorption_potential = R_GAS * temperature * math.log(1.0 / relative_saturation)
    exponent = adsorption_potential / (affinity_coefficient * characteristic_energy)
    return math.exp(-(exponent**2))


class CapillaryCondensationScreeningModel:
    """Screening-level Kelvin capillary condensation limit for an adsorbent bed."""

    def evaluate(
        self,
        temperature: float,
        surface_tension: float,
        molar_volume: float,
        pore_radius_nm: float,
        saturation_mole_fraction: float,
        contaminant_mole_fraction: Optional[float] = None,
        contact_angle_deg: float = 0.0,
        geometry_factor: float = 2.0,
        watch_margin: float = 0.5,
    ) -> CapillaryScreeningResult:
        """Screen the maximum contaminant concentration a sorbent pore tolerates.

        :param temperature: gas temperature in kelvin, must be positive.
        :param surface_tension: contaminant liquid surface tension in N/m, must be positive.
        :param molar_volume: contaminant liquid molar volume in m3/mol, must be positive.
        :param pore_radius_nm: representative sorbent pore radius in nm, must be positive.
        :param saturation_mole_fraction: bulk saturation mole fraction of the contaminant in
            the gas at bed conditions, from a real equation of state, between 0 and 1.
        :param contaminant_mole_fraction: optional current contaminant mole fraction.
        :param contact_angle_deg: liquid-solid contact angle in degrees, 0 means perfect wetting.
        :param geometry_factor: 2.0 for cylindrical pores, 1.0 for slit pores.
        :param watch_margin: fraction of the limit above which the result is flagged `watch`.
        :returns: a :class:`CapillaryScreeningResult`.
        :raises ValueError: if any physical input is out of range.
        """
        if temperature <= 0.0:
            raise ValueError("temperature must be positive")
        if surface_tension <= 0.0:
            raise ValueError("surface_tension must be positive")
        if molar_volume <= 0.0:
            raise ValueError("molar_volume must be positive")
        if pore_radius_nm <= 0.0:
            raise ValueError("pore_radius_nm must be positive")
        if not 0.0 < saturation_mole_fraction <= 1.0:
            raise ValueError("saturation_mole_fraction must be between 0 and 1")

        cos_theta = math.cos(math.radians(contact_angle_deg))
        kelvin_length_nm = (
            geometry_factor * surface_tension * molar_volume * cos_theta / (R_GAS * temperature) * 1e9
        )
        onset = math.exp(-kelvin_length_nm / pore_radius_nm)
        max_mole_fraction = onset * saturation_mole_fraction

        assumptions = [
            "Kelvin equation with a continuum meniscus",
            f"contact angle {contact_angle_deg:.0f} deg (cos = {cos_theta:.3f})",
            f"geometry factor {geometry_factor:.1f}",
            "single condensable contaminant; a mixed condensate condenses earlier",
            "saturation mole fraction supplied by the caller, not derived here",
        ]

        kelvin_valid = pore_radius_nm >= KELVIN_VALIDITY_RADIUS_NM
        if not kelvin_valid:
            assumptions.append(
                "pore radius below 2 nm: Kelvin over-predicts the onset, treat the "
                "limit as an upper bound and use micropore_filling_fraction()"
            )

        relative_saturation = None
        margin_ratio = None
        warning = "ok"
        if contaminant_mole_fraction is not None:
            if contaminant_mole_fraction < 0.0:
                raise ValueError("contaminant_mole_fraction must be non-negative")
            relative_saturation = contaminant_mole_fraction / saturation_mole_fraction
            margin_ratio = contaminant_mole_fraction / max_mole_fraction
            if margin_ratio >= 1.0:
                warning = "condensation-expected"
            elif margin_ratio >= watch_margin:
                warning = "watch"

        return CapillaryScreeningResult(
            kelvin_length_nm=kelvin_length_nm,
            onset_relative_saturation=onset,
            max_mole_fraction=max_mole_fraction,
            max_ppmv=max_mole_fraction * 1e6,
            kelvin_valid=kelvin_valid,
            warning=warning,
            relative_saturation=relative_saturation,
            margin_ratio=margin_ratio,
            assumptions=assumptions,
        )
