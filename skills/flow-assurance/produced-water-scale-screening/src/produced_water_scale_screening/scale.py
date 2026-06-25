"""Screening-level scale and corrosion indicators for produced water.

The saturation indices computed here use public solubility products at 25 degC
and the Davies activity model. They are intended to rank scaling tendency and
flag water-mixing incompatibility, not to size scale inhibitor programs. Use
the NeqSim ``ThermodynamicOperations.checkScalePotential`` routine on an
electrolyte-CPA fluid for design-grade results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import log10

from .builder import ProducedWater, ProducedWaterBuilder
from .chemistry import (
    DAVIES_A,
    K2_CARBONIC,
    KSP_25C,
    SCALE_IONS,
    davies_activity_coefficient,
)

#: Saturation-index risk band thresholds.
_MODERATE_SI = 0.0
_HIGH_SI = 0.5


@dataclass(frozen=True)
class ScaleResult:
    """Screening result for a single scale mineral.

    Attributes:
        salt: Mineral name (e.g. ``BaSO4``).
        saturation_index: log10(IAP / Ksp); >0 indicates supersaturation.
        risk: One of ``low``, ``moderate``, ``high``, ``unknown``.
        note: Short explanation of the result.
    """

    salt: str
    saturation_index: float | None
    risk: str
    note: str


@dataclass(frozen=True)
class ScaleScreening:
    """Collection of scale results for a single water.

    Attributes:
        water_name: Label of the screened water.
        temperature_c: Temperature in degrees Celsius.
        results: Per-mineral :class:`ScaleResult` entries.
        warnings: Non-fatal screening warnings.
    """

    water_name: str
    temperature_c: float
    results: tuple[ScaleResult, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MixIncompatibility:
    """Worst-case scaling found while sweeping a two-water blend.

    Attributes:
        salt: Mineral name.
        worst_fraction_a: Volume fraction of water A giving the highest index.
        worst_saturation_index: Highest saturation index across the sweep.
        risk: Risk band at the worst point.
        profile: Tuple of (fraction_a, saturation_index) sample points.
    """

    salt: str
    worst_fraction_a: float
    worst_saturation_index: float | None
    risk: str
    profile: tuple[tuple[float, float | None], ...]


def _risk_band(si: float | None) -> str:
    """Map a saturation index to a screening risk band.

    Args:
        si: Saturation index, or ``None`` when undetermined.

    Returns:
        Risk band string.
    """
    if si is None:
        return "unknown"
    if si >= _HIGH_SI:
        return "high"
    if si >= _MODERATE_SI:
        return "moderate"
    return "low"


class ScaleScreener:
    """Computes screening scale indices and corrosion flags."""

    def __init__(self) -> None:
        self._builder = ProducedWaterBuilder()

    def screen(self, water: ProducedWater) -> ScaleScreening:
        """Screen a produced water for common oilfield scales.

        Args:
            water: The produced water to screen.

        Returns:
            A :class:`ScaleScreening` summary.
        """
        warnings: list[str] = []
        if abs(water.temperature_c - 25.0) > 5.0:
            warnings.append(
                "Screening Ksp values are referenced to 25 degC; rerun with "
                "NeqSim checkScalePotential for temperature dependence."
            )
        if water.ionic_strength_mol_kg > 0.7:
            warnings.append(
                "Ionic strength exceeds the Davies model validity range "
                "(~0.5 mol/kg); indices are indicative only."
            )

        gamma2 = davies_activity_coefficient(2, water.ionic_strength_mol_kg)
        results: list[ScaleResult] = []

        for salt in ("BaSO4", "SrSO4", "CaSO4"):
            results.append(self._sulfate_scale(salt, water, gamma2))
        results.append(self._calcite_scale(water, gamma2, warnings))

        return ScaleScreening(
            water_name=water.name,
            temperature_c=water.temperature_c,
            results=tuple(results),
            warnings=tuple(warnings),
        )

    def mixing_incompatibility(
        self,
        water_a: ProducedWater,
        water_b: ProducedWater,
        steps: int = 11,
    ) -> tuple[MixIncompatibility, ...]:
        """Sweep blend ratios and report worst-case sulfate/carbonate scaling.

        This is the classic seawater-injection incompatibility check: barium or
        strontium from formation water meeting sulfate from injected seawater.

        Args:
            water_a: First water (e.g. formation water).
            water_b: Second water (e.g. injection seawater).
            steps: Number of blend fractions to sample (>= 2).

        Returns:
            One :class:`MixIncompatibility` per screened mineral.

        Raises:
            ValueError: If ``steps`` is less than 2.
        """
        if steps < 2:
            raise ValueError("steps must be at least 2.")

        fractions = [i / (steps - 1) for i in range(steps)]
        profiles: dict[str, list[tuple[float, float | None]]] = {
            salt: [] for salt in SCALE_IONS
        }

        for fraction_a in fractions:
            blend = self._builder.mix(water_a, water_b, fraction_a)
            screening = self.screen(blend)
            by_salt = {r.salt: r.saturation_index for r in screening.results}
            for salt in SCALE_IONS:
                profiles[salt].append((fraction_a, by_salt.get(salt)))

        out: list[MixIncompatibility] = []
        for salt, profile in profiles.items():
            valued = [(f, si) for f, si in profile if si is not None]
            if valued:
                worst_f, worst_si = max(valued, key=lambda pair: pair[1])
                risk = _risk_band(worst_si)
            else:
                worst_f, worst_si, risk = 0.0, None, "unknown"
            out.append(
                MixIncompatibility(
                    salt=salt,
                    worst_fraction_a=worst_f,
                    worst_saturation_index=worst_si,
                    risk=risk,
                    profile=tuple(profile),
                )
            )
        return tuple(out)

    def corrosion_flags(
        self,
        water: ProducedWater,
        co2_mol_percent: float | None = None,
        h2s_mol_percent: float | None = None,
    ) -> tuple[str, ...]:
        """Informational CO2/H2S corrosion flags (NORSOK M-001 oriented).

        Args:
            water: The produced water (used for pressure context).
            co2_mol_percent: CO2 content of the associated gas in mol%.
            h2s_mol_percent: H2S content of the associated gas in mol%.

        Returns:
            A tuple of human-readable, screening-level flag strings.
        """
        flags: list[str] = []
        if co2_mol_percent is not None and co2_mol_percent > 0.0:
            p_co2 = (co2_mol_percent / 100.0) * water.pressure_bara
            if p_co2 > 2.0:
                level = "high"
            elif p_co2 >= 0.5:
                level = "moderate"
            else:
                level = "low"
            flags.append(
                f"CO2 partial pressure ~{p_co2:.2f} bar: {level} sweet-corrosion "
                "tendency; apply NORSOK M-001 material selection."
            )
        if h2s_mol_percent is not None and h2s_mol_percent > 0.0:
            p_h2s = (h2s_mol_percent / 100.0) * water.pressure_bara
            sour = "sour" if p_h2s > 0.0003 else "trace"
            flags.append(
                f"H2S partial pressure ~{p_h2s:.4f} bar: {sour} service; assess "
                "against ISO 15156 / NACE MR0175 and NORSOK M-001."
            )
        if not flags:
            flags.append("No CO2/H2S data supplied; corrosion screening skipped.")
        return tuple(flags)

    @staticmethod
    def _sulfate_scale(
        salt: str, water: ProducedWater, gamma2: float
    ) -> ScaleResult:
        """Compute the saturation index for a divalent sulfate scale.

        Args:
            salt: Mineral name (``BaSO4``, ``SrSO4`` or ``CaSO4``).
            water: The produced water.
            gamma2: Divalent-ion activity coefficient.

        Returns:
            A :class:`ScaleResult`.
        """
        cation, anion = SCALE_IONS[salt]
        m_cat = water.molality.get(cation, 0.0)
        m_an = water.molality.get(anion, 0.0)
        if m_cat <= 0.0 or m_an <= 0.0:
            return ScaleResult(
                salt=salt,
                saturation_index=None,
                risk="unknown",
                note=f"Missing {cation} or {anion}; cannot evaluate {salt}.",
            )
        iap = (gamma2 * m_cat) * (gamma2 * m_an)
        si = log10(iap / KSP_25C[salt])
        return ScaleResult(
            salt=salt,
            saturation_index=si,
            risk=_risk_band(si),
            note=f"SI=log10(IAP/Ksp); Ksp(25C)={KSP_25C[salt]:.2e}.",
        )

    @staticmethod
    def _calcite_scale(
        water: ProducedWater, gamma2: float, warnings: list[str]
    ) -> ScaleResult:
        """Compute the calcite saturation index from pH and bicarbonate.

        Args:
            water: The produced water.
            gamma2: Divalent-ion activity coefficient.
            warnings: Mutable warning list to append to.

        Returns:
            A :class:`ScaleResult`.
        """
        m_ca = water.molality.get("Ca++", 0.0)
        m_hco3 = water.molality.get("HCO3-", 0.0)
        if m_ca <= 0.0 or m_hco3 <= 0.0 or water.ph is None:
            return ScaleResult(
                salt="CaCO3",
                saturation_index=None,
                risk="unknown",
                note="Requires Ca++, HCO3- and pH; supply pH to evaluate calcite.",
            )
        h_plus = 10.0 ** (-water.ph)
        # Carbonate from bicarbonate equilibrium: [CO3] = K2 [HCO3] / [H+].
        m_co3 = K2_CARBONIC * m_hco3 / h_plus
        iap = (gamma2 * m_ca) * (gamma2 * m_co3)
        si = log10(iap / KSP_25C["CaCO3"])
        _ = DAVIES_A  # keep activity model explicit for readers
        return ScaleResult(
            salt="CaCO3",
            saturation_index=si,
            risk=_risk_band(si),
            note="Calcite SI from pH-derived carbonate; 25 degC Ksp basis.",
        )
