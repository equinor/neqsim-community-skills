"""Produced-water composition builder (public, deterministic).

Builds a normalized produced-water ion description from presets, explicit ion
concentrations, or a total-dissolved-solids value, performs a charge-balance
check, and emits a NeqSim-ready ion mapping that can be fed to the NeqSim
``ProducedWaterFluidBuilder.createFromIons`` factory to generate a real
electrolyte-CPA fluid for rigorous scale evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib.util import find_spec
from math import isfinite

from .chemistry import (
    ION_MOLAR_MASS,
    NEQSIM_BUILDER_IONS,
    charge_balance_error_pct,
    ionic_strength,
    molality_map,
)

#: Representative public water compositions in mg/L. Seawater follows the
#: standard reference seawater major-ion set; the formation-water example is a
#: generic high-barium North Sea style brine used only for illustration.
PRESETS: dict[str, dict[str, float]] = {
    "seawater": {
        "Na+": 10770.0,
        "K+": 399.0,
        "Ca++": 412.0,
        "Mg++": 1290.0,
        "Sr++": 8.0,
        "Cl-": 19350.0,
        "SO4--": 2710.0,
        "HCO3-": 142.0,
    },
    "formation_water_high_ba": {
        "Na+": 30000.0,
        "K+": 500.0,
        "Ca++": 5000.0,
        "Mg++": 700.0,
        "Sr++": 500.0,
        "Ba++": 250.0,
        "Cl-": 60000.0,
        "SO4--": 0.0,
        "HCO3-": 400.0,
    },
    "brackish": {
        "Na+": 1900.0,
        "Ca++": 90.0,
        "Mg++": 110.0,
        "Cl-": 2700.0,
        "SO4--": 250.0,
        "HCO3-": 250.0,
    },
}


@dataclass(frozen=True)
class ProducedWater:
    """Normalized produced-water description used for screening.

    Attributes:
        name: Label for the water sample.
        ions_mg_l: Ion concentrations in mg/L.
        temperature_c: Temperature in degrees Celsius.
        pressure_bara: Pressure in bara.
        ph: Optional in-situ pH (required for carbonate scaling screening).
        tds_mg_l: Total dissolved solids in mg/L (sum of ions).
        molality: Ion molality in mol/kg.
        ionic_strength_mol_kg: Brine ionic strength in mol/kg.
        charge_balance_error_pct: Cation-anion imbalance as a percentage.
        neqsim_components: Ion-to-mole-fraction mapping for the NeqSim builder.
        neqsim_available: Whether the ``neqsim`` package is importable.
        warnings: Non-fatal screening warnings.
    """

    name: str
    ions_mg_l: dict[str, float]
    temperature_c: float
    pressure_bara: float
    ph: float | None
    tds_mg_l: float
    molality: dict[str, float]
    ionic_strength_mol_kg: float
    charge_balance_error_pct: float
    neqsim_components: dict[str, float]
    neqsim_available: bool
    warnings: tuple[str, ...] = field(default_factory=tuple)


class ProducedWaterBuilder:
    """Builds and combines produced-water ion descriptions."""

    def build(
        self,
        ions_mg_l: dict[str, float] | None = None,
        preset: str | None = None,
        tds_mg_l: float | None = None,
        temperature_c: float = 25.0,
        pressure_bara: float = 1.0,
        ph: float | None = None,
        name: str = "produced_water",
    ) -> ProducedWater:
        """Build a normalized produced-water description.

        Exactly one of ``ions_mg_l``, ``preset``, or ``tds_mg_l`` must be given.

        Args:
            ions_mg_l: Explicit ion concentrations in mg/L.
            preset: Name of a built-in preset (see ``PRESETS``).
            tds_mg_l: Total dissolved solids in mg/L, modelled as pure NaCl.
            temperature_c: Temperature in degrees Celsius.
            pressure_bara: Pressure in bara.
            ph: Optional in-situ pH.
            name: Label for the sample.

        Returns:
            A :class:`ProducedWater` instance.

        Raises:
            ValueError: If the inputs are missing, ambiguous, or non-finite.
        """
        provided = [x for x in (ions_mg_l, preset, tds_mg_l) if x is not None]
        if len(provided) != 1:
            raise ValueError(
                "Provide exactly one of ions_mg_l, preset, or tds_mg_l."
            )

        warnings: list[str] = []

        if preset is not None:
            if preset not in PRESETS:
                raise ValueError(
                    f"Unknown preset '{preset}'. Options: {sorted(PRESETS)}"
                )
            ions = dict(PRESETS[preset])
        elif tds_mg_l is not None:
            if not isfinite(tds_mg_l) or tds_mg_l < 0.0:
                raise ValueError("tds_mg_l must be a finite, non-negative value.")
            # Approximate as sodium chloride (Na/Cl mass split by molar mass).
            na_frac = ION_MOLAR_MASS["Na+"] / (
                ION_MOLAR_MASS["Na+"] + ION_MOLAR_MASS["Cl-"]
            )
            ions = {"Na+": tds_mg_l * na_frac, "Cl-": tds_mg_l * (1.0 - na_frac)}
            warnings.append(
                "TDS input modelled as pure NaCl; supply explicit ions for "
                "carbonate or sulfate scaling screening."
            )
        else:
            assert ions_mg_l is not None
            ions = {}
            for key, value in ions_mg_l.items():
                if not isfinite(value):
                    raise ValueError(f"Concentration for '{key}' is not finite.")
                if value < 0.0:
                    raise ValueError(f"Concentration for '{key}' is negative.")
                if key not in ION_MOLAR_MASS:
                    warnings.append(
                        f"Ion '{key}' is not recognized and is ignored."
                    )
                    continue
                ions[key] = float(value)

        clean_ions = {k: v for k, v in ions.items() if v > 0.0}
        if not clean_ions:
            raise ValueError("No positive ion concentrations were provided.")

        molality = molality_map(clean_ions)
        strength = ionic_strength(molality)
        cb_error = charge_balance_error_pct(molality)
        if abs(cb_error) > 10.0:
            warnings.append(
                f"Charge balance error is {cb_error:.1f}% (>10%); "
                "check the ion analysis."
            )

        unsupported = sorted(set(molality) - NEQSIM_BUILDER_IONS)
        if unsupported:
            warnings.append(
                "Ions "
                + ", ".join(unsupported)
                + " are screened here but are not added by the basic NeqSim "
                "ProducedWaterFluidBuilder presets; use createFromIons or the "
                "NeqSim-backed enterprise skill to include them."
            )

        neqsim_components = self._neqsim_components(molality)
        tds = sum(clean_ions.values())

        return ProducedWater(
            name=name,
            ions_mg_l=clean_ions,
            temperature_c=float(temperature_c),
            pressure_bara=float(pressure_bara),
            ph=ph,
            tds_mg_l=float(tds),
            molality=molality,
            ionic_strength_mol_kg=float(strength),
            charge_balance_error_pct=float(cb_error),
            neqsim_components=neqsim_components,
            neqsim_available=find_spec("neqsim") is not None,
            warnings=tuple(warnings),
        )

    def mix(
        self,
        water_a: ProducedWater,
        water_b: ProducedWater,
        fraction_a: float,
        name: str | None = None,
    ) -> ProducedWater:
        """Linearly blend two waters on a volume basis.

        Args:
            water_a: First water.
            water_b: Second water.
            fraction_a: Volume fraction of ``water_a`` in the mixture (0-1).
            name: Optional label for the mixture.

        Returns:
            A :class:`ProducedWater` for the blended composition.

        Raises:
            ValueError: If ``fraction_a`` is outside [0, 1].
        """
        if not 0.0 <= fraction_a <= 1.0:
            raise ValueError("fraction_a must be between 0 and 1.")
        fraction_b = 1.0 - fraction_a
        mixed: dict[str, float] = {}
        for ion in set(water_a.ions_mg_l) | set(water_b.ions_mg_l):
            mixed[ion] = (
                fraction_a * water_a.ions_mg_l.get(ion, 0.0)
                + fraction_b * water_b.ions_mg_l.get(ion, 0.0)
            )
        ph = None
        if water_a.ph is not None and water_b.ph is not None:
            ph = fraction_a * water_a.ph + fraction_b * water_b.ph
        label = name or f"mix_{fraction_a:.2f}A_{fraction_b:.2f}B"
        return self.build(
            ions_mg_l=mixed,
            temperature_c=fraction_a * water_a.temperature_c
            + fraction_b * water_b.temperature_c,
            pressure_bara=fraction_a * water_a.pressure_bara
            + fraction_b * water_b.pressure_bara,
            ph=ph,
            name=label,
        )

    @staticmethod
    def _neqsim_components(molality: dict[str, float]) -> dict[str, float]:
        """Build a water + ion mole-fraction mapping for the NeqSim builder.

        Args:
            molality: Ion molality in mol/kg.

        Returns:
            Mapping of ``water`` and ion names to mole fractions.
        """
        water_moles = 1000.0 / 18.015  # moles of water per kg
        moles = {"water": water_moles}
        for ion, m in molality.items():
            moles[ion] = m
        total = sum(moles.values())
        return {name: value / total for name, value in moles.items()}
