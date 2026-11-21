"""Property evaluation for one blend, with a NeqSim backend.

The screening logic in :mod:`.screening` only needs a :class:`BlendProperties`
per blend fraction. Anything that implements :class:`BlendEvaluator` can supply
them; :class:`NeqSimBlendEvaluator` computes them with the NeqSim Java engine.
Tests use a lightweight stand-in so the logic runs without Java.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol

from .fluids import Blend

NAN = float("nan")


def refractive_index_from_density(density_kg_m3: float) -> float:
    """Refractive index of a liquid hydrocarbon from its density.

    Lorentz-Lorenz function of refractive index ``F_RI = (n^2-1)/(n^2+2)``
    correlated against specific gravity (Buckley et al., 1998). Applied here to
    the live-oil density at pressure, so the index falls as the oil expands
    towards its bubble point. Identical to NeqSim
    ``RefractiveIndexAsphalteneScreening#estimateRIFromDensity``.
    """
    if not math.isfinite(density_kg_m3) or density_kg_m3 <= 0:
        return NAN
    sg = density_kg_m3 / 1000.0
    fri = 0.2898 * sg + 0.07602 * sg * sg
    if fri >= 1.0:
        return NAN
    n_squared = max((1.0 + 2.0 * fri) / (1.0 - fri), 1.0)
    return math.sqrt(n_squared)


@dataclass(frozen=True)
class EvaluationConditions:
    """Conditions at which each blend is evaluated.

    Attributes:
        commingling_pressure_bara: Pressure where the streams meet, bara.
        commingling_temperature_c: Mixed-stream temperature, deg C.
        path_end_pressure_bara: Lowest pressure of the depressurisation path
            scanned for the live-oil refractive-index minimum, bara.
        path_points: Number of pressures on that path (>= 3).
        separator_pressure_bara: First-stage separator pressure, bara, or None.
        separator_temperature_c: First-stage separator temperature, deg C.
        hydrate_pressure_bara: Pressure for the hydrate equilibrium
            temperature, bara, or None to skip the hydrate check.
    """

    commingling_pressure_bara: float
    commingling_temperature_c: float
    path_end_pressure_bara: float = 10.0
    path_points: int = 12
    separator_pressure_bara: float | None = None
    separator_temperature_c: float | None = None
    hydrate_pressure_bara: float | None = None

    def __post_init__(self) -> None:
        if not self.commingling_pressure_bara > 0:
            raise ValueError("commingling_pressure_bara must be > 0")
        if not -50.0 <= self.commingling_temperature_c <= 250.0:
            raise ValueError("commingling_temperature_c must be within -50..250 C")
        if not 0 < self.path_end_pressure_bara < self.commingling_pressure_bara:
            raise ValueError(
                "path_end_pressure_bara must be > 0 and below the commingling pressure"
            )
        if self.path_points < 3:
            raise ValueError("path_points must be >= 3")
        if (self.separator_pressure_bara is None) != (
            self.separator_temperature_c is None
        ):
            raise ValueError("give both separator pressure and temperature, or neither")
        if (
            self.separator_pressure_bara is not None
            and self.separator_pressure_bara <= 0
        ):
            raise ValueError("separator_pressure_bara must be > 0")
        if self.hydrate_pressure_bara is not None and self.hydrate_pressure_bara <= 0:
            raise ValueError("hydrate_pressure_bara must be > 0")

    def path_pressures(self) -> list[float]:
        """Pressures from commingling pressure down to the path end, bara."""
        high, low, n = (
            self.commingling_pressure_bara,
            self.path_end_pressure_bara,
            self.path_points,
        )
        return [high - (high - low) * i / (n - 1) for i in range(n)]


@dataclass
class BlendProperties:
    """Computed properties of one blend.

    All values are NaN (or None) when they could not be computed; the reason is
    recorded in ``notes``.
    """

    fraction_b: float
    saturation_pressure_bara: float = NAN
    phases_at_commingling: list[str] = field(default_factory=list)
    liquid_density_kg_m3: float = NAN
    gas_volume_fraction: float = NAN
    min_live_oil_ri: float = NAN
    min_live_oil_ri_pressure_bara: float = NAN
    de_boer_risk: str | None = None
    hydrate_temperature_c: float = NAN
    free_water_assumed: bool = False
    separator_gas_h2s_ppm: float = NAN
    separator_gas_co2_mol_pct: float = NAN
    notes: list[str] = field(default_factory=list)

    @property
    def free_gas_at_commingling(self) -> bool:
        """True when a gas phase exists where the streams meet."""
        return "gas" in self.phases_at_commingling


class BlendEvaluator(Protocol):
    """Anything that turns a blend into :class:`BlendProperties`."""

    def evaluate(
        self, blend: Blend, conditions: EvaluationConditions
    ) -> BlendProperties: ...


class NeqSimUnavailableError(RuntimeError):
    """Raised when the neqsim Python package cannot be imported."""


class NeqSimBlendEvaluator:
    """Evaluate blends with the NeqSim Java engine.

    Args:
        eos: ``"auto"`` (SRK-CPA when water is present, otherwise SRK),
            ``"srk"``, ``"pr"`` or ``"cpa"``.
        volume_correction: Apply Peneloux volume translation. Keep it on:
            the refractive index is computed from liquid density.
        free_water_mol_frac: Water added to a dry blend for the hydrate check,
            as a mole fraction of the blend (free water assumed).
    """

    def __init__(
        self,
        eos: str = "auto",
        volume_correction: bool = True,
        free_water_mol_frac: float = 0.05,
    ) -> None:
        if eos not in ("auto", "srk", "pr", "cpa"):
            raise ValueError("eos must be 'auto', 'srk', 'pr' or 'cpa'")
        if not 0 < free_water_mol_frac < 0.5:
            raise ValueError("free_water_mol_frac must be within 0-0.5")
        try:
            from neqsim import jneqsim
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise NeqSimUnavailableError(
                "neqsim is not installed: python -m pip install neqsim"
            ) from exc
        self._j = jneqsim
        self.eos = eos
        self.volume_correction = volume_correction
        self.free_water_mol_frac = free_water_mol_frac

    # -- system construction -------------------------------------------------
    def _eos_for(self, blend: Blend) -> str:
        if self.eos != "auto":
            return self.eos
        return "cpa" if blend.has_water() else "srk"

    def build_system(self, blend: Blend, temperature_c: float, pressure_bara: float):
        """Build a NeqSim fluid for a blend."""
        thermo = self._j.thermo.system
        eos = self._eos_for(blend)
        cls = {
            "srk": thermo.SystemSrkEos,
            "pr": thermo.SystemPrEos,
            "cpa": thermo.SystemSrkCPAstatoil,
        }[eos]
        system = cls(273.15 + temperature_c, pressure_bara)
        for name, x in blend.components.items():
            system.addComponent(name, float(x))
        for pseudo in blend.pseudo_components:
            system.addTBPfraction(
                pseudo.name,
                float(pseudo.mole_fraction),
                float(pseudo.molar_mass_kg_mol),
                float(pseudo.density_g_cm3),
            )
        system.setMixingRule(10 if eos == "cpa" else "classic")
        system.setMultiPhaseCheck(True)
        if self.volume_correction:
            system.useVolumeCorrection(True)
        return system

    def _flash(self, system):
        ops = self._j.thermodynamicoperations.ThermodynamicOperations(system)
        ops.TPflash()
        system.initPhysicalProperties()
        return system

    @staticmethod
    def _phase_names(system) -> list[str]:
        names = []
        for i in range(system.getNumberOfPhases()):
            names.append(str(system.getPhase(i).getType()).lower())
        return names

    @staticmethod
    def _oil_density(system) -> float:
        if system.hasPhaseType("oil"):
            return float(system.getPhase("oil").getDensity("kg/m3"))
        return NAN

    # -- evaluation ----------------------------------------------------------
    def evaluate(
        self, blend: Blend, conditions: EvaluationConditions
    ) -> BlendProperties:
        """Compute all properties for one blend."""
        props = BlendProperties(fraction_b=blend.fraction_b)
        dry = blend.without_water()
        t_c = conditions.commingling_temperature_c
        p_bar = conditions.commingling_pressure_bara

        # Saturation (bubble-point) pressure of the hydrocarbon blend.
        try:
            system = self.build_system(dry, t_c, p_bar)
            ops = self._j.thermodynamicoperations.ThermodynamicOperations(system)
            ops.bubblePointPressureFlash(False)
            psat = float(system.getPressure())
            props.saturation_pressure_bara = psat if math.isfinite(psat) else NAN
        except Exception as exc:  # noqa: BLE001 - Java exceptions vary
            props.notes.append(f"bubble point not found ({type(exc).__name__})")

        # Phase state and liquid density at the commingling point.
        try:
            system = self._flash(self.build_system(dry, t_c, p_bar))
            props.phases_at_commingling = self._phase_names(system)
            props.liquid_density_kg_m3 = self._oil_density(system)
            if system.hasPhaseType("gas"):
                gas_volume = float(system.getPhase("gas").getVolume("m3"))
                total_volume = sum(
                    float(system.getPhase(i).getVolume("m3"))
                    for i in range(system.getNumberOfPhases())
                )
                props.gas_volume_fraction = gas_volume / total_volume
            else:
                props.gas_volume_fraction = 0.0
        except Exception as exc:  # noqa: BLE001
            props.notes.append(f"commingling flash failed ({type(exc).__name__})")

        # de Boer at the commingling point (needs a liquid and a saturation P).
        if math.isfinite(props.liquid_density_kg_m3) and math.isfinite(
            props.saturation_pressure_bara
        ):
            screening = self._j.pvtsimulation.flowassurance.DeBoerAsphalteneScreening(
                float(p_bar),
                float(props.saturation_pressure_bara),
                float(props.liquid_density_kg_m3),
            )
            props.de_boer_risk = str(screening.evaluateRisk().name())

        # Live-oil refractive index along the depressurisation path.
        best = (NAN, NAN)
        pressures = conditions.path_pressures()
        psat = props.saturation_pressure_bara
        if math.isfinite(psat) and pressures[-1] < psat + 0.5 < pressures[0]:
            # Live-oil density, and so the refractive index, is lowest just
            # above the bubble point; sample it explicitly.
            pressures.append(psat + 0.5)
        failed_pressures = []
        for pressure in pressures:
            try:
                system = self._flash(self.build_system(dry, t_c, pressure))
            except Exception:  # noqa: BLE001
                failed_pressures.append(pressure)
                continue
            ri = refractive_index_from_density(self._oil_density(system))
            if math.isfinite(ri) and not ri >= best[0]:
                best = (ri, pressure)
        props.min_live_oil_ri, props.min_live_oil_ri_pressure_bara = best
        if failed_pressures:
            props.notes.append(
                f"path flash failed at {len(failed_pressures)} pressure(s), from "
                f"{min(failed_pressures):.0f} to {max(failed_pressures):.0f} bara"
            )
        if not math.isfinite(best[0]):
            props.notes.append("no liquid hydrocarbon phase along the pressure path")

        # Hydrate equilibrium temperature.
        if conditions.hydrate_pressure_bara is not None:
            props.hydrate_temperature_c, props.free_water_assumed = self._hydrate(
                blend, conditions.hydrate_pressure_bara, props.notes
            )

        # Separator gas sour-component content.
        if conditions.separator_pressure_bara is not None:
            try:
                system = self._flash(
                    self.build_system(
                        blend,
                        float(conditions.separator_temperature_c),
                        float(conditions.separator_pressure_bara),
                    )
                )
                if system.hasPhaseType("gas"):
                    gas = system.getPhase("gas")
                    if "H2S" in blend.components:
                        props.separator_gas_h2s_ppm = (
                            float(gas.getComponent("H2S").getx()) * 1e6
                        )
                    if "CO2" in blend.components:
                        props.separator_gas_co2_mol_pct = (
                            float(gas.getComponent("CO2").getx()) * 100.0
                        )
                else:
                    props.notes.append("no gas phase at separator conditions")
            except Exception as exc:  # noqa: BLE001
                props.notes.append(f"separator flash failed ({type(exc).__name__})")
        return props

    def _hydrate(
        self, blend: Blend, pressure_bara: float, notes: list[str]
    ) -> tuple[float, bool]:
        assumed = False
        work = blend
        if not blend.has_water():
            assumed = True
            scale = 1.0 - self.free_water_mol_frac
            work = type(blend)(
                fraction_b=blend.fraction_b,
                components={
                    **{k: v * scale for k, v in blend.components.items()},
                    "water": self.free_water_mol_frac,
                },
                pseudo_components=tuple(
                    type(p)(
                        p.name,
                        p.mole_fraction * scale,
                        p.molar_mass_kg_mol,
                        p.density_g_cm3,
                    )
                    for p in blend.pseudo_components
                ),
            )
        try:
            system = self.build_system(work, 20.0, pressure_bara)
            system.setHydrateCheck(True)
            ops = self._j.thermodynamicoperations.ThermodynamicOperations(system)
            ops.hydrateFormationTemperature()
            temperature = float(system.getTemperature()) - 273.15
            return (temperature if math.isfinite(temperature) else NAN), assumed
        except Exception as exc:  # noqa: BLE001
            notes.append(f"hydrate temperature not found ({type(exc).__name__})")
            return NAN, assumed
