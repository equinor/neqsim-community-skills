from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite
from typing import Sequence


@dataclass(frozen=True)
class EnergyEmissionsResult:
    years: int
    emission_factor_kg_co2e_per_mwh: float
    annual_energy_use_mwh: tuple[float, ...]
    annual_co2e_tonnes: tuple[float, ...]
    total_energy_use_mwh: float
    total_co2e_tonnes: float
    total_production_boe: float
    carbon_intensity_kg_per_boe: float | None
    annual_emission_cost_musd: tuple[float, ...]
    total_emission_cost_musd: float
    intensity_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class EnergyEmissionsModel:
    """Educational field-life energy and CO2e emissions roll-up placeholder.

    Aggregates a year-by-year energy use into annual and total CO2-equivalent
    emissions using a public emission factor, computes a carbon intensity
    (kg CO2e per barrel of oil equivalent), and optionally applies a CO2 tax. It
    is a transparent placeholder only: real emission accounting must come from the
    validated NeqSim combustion path (``Standard_ISO6976``, ``GasTurbine``,
    ``GibbsReactor``) and certified emission factors, with qualified reporting.
    """

    def __init__(self, *, watch_intensity_kg_per_boe: float = 17.0) -> None:
        if watch_intensity_kg_per_boe <= 0.0:
            raise ValueError("watch_intensity_kg_per_boe must be positive")
        self.watch_intensity_kg_per_boe = watch_intensity_kg_per_boe

    def evaluate(
        self,
        *,
        annual_energy_use_mwh: Sequence[float],
        emission_factor_kg_co2e_per_mwh: float = 450.0,
        annual_production_boe: Sequence[float] | float = 0.0,
        co2_tax_usd_per_tonne: float = 0.0,
    ) -> EnergyEmissionsResult:
        energy = self._normalize_series("annual_energy_use_mwh", annual_energy_use_mwh)
        years = len(energy)
        if years == 0:
            raise ValueError("annual_energy_use_mwh must contain at least one year")
        for v in energy:
            if v < 0.0:
                raise ValueError("annual_energy_use_mwh values must be non-negative")
        self._require_positive(
            "emission_factor_kg_co2e_per_mwh", emission_factor_kg_co2e_per_mwh
        )
        self._require_non_negative("co2_tax_usd_per_tonne", co2_tax_usd_per_tonne)
        production = self._broadcast(
            "annual_production_boe", annual_production_boe, years
        )

        # kg CO2e = MWh * (kg CO2e / MWh); convert kg -> tonnes (1000 kg).
        annual_co2e_tonnes = [
            (e * emission_factor_kg_co2e_per_mwh) / 1000.0 for e in energy
        ]
        total_co2e = sum(annual_co2e_tonnes)
        total_energy = sum(energy)
        total_production = sum(production)

        if total_production > 0.0:
            # total tonnes -> kg, divide by total boe.
            carbon_intensity = (total_co2e * 1000.0) / total_production
        else:
            carbon_intensity = None

        # MUSD = tonnes * USD/tonne / 1e6.
        annual_cost = [
            (t * co2_tax_usd_per_tonne) / 1.0e6 for t in annual_co2e_tonnes
        ]
        total_cost = sum(annual_cost)

        warning = self._intensity_warning(carbon_intensity)

        return EnergyEmissionsResult(
            years=years,
            emission_factor_kg_co2e_per_mwh=round(emission_factor_kg_co2e_per_mwh, 3),
            annual_energy_use_mwh=tuple(round(v, 3) for v in energy),
            annual_co2e_tonnes=tuple(round(v, 3) for v in annual_co2e_tonnes),
            total_energy_use_mwh=round(total_energy, 3),
            total_co2e_tonnes=round(total_co2e, 3),
            total_production_boe=round(total_production, 3),
            carbon_intensity_kg_per_boe=(
                None if carbon_intensity is None else round(carbon_intensity, 4)
            ),
            annual_emission_cost_musd=tuple(round(v, 4) for v in annual_cost),
            total_emission_cost_musd=round(total_cost, 4),
            intensity_warning=warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational field-life energy and CO2e roll-up placeholder only.",
                "Annual CO2e = annual energy use (MWh) * emission factor (kg CO2e/MWh) / 1000.",
                "The emission factor is a single public average, not a certified or fuel-specific factor.",
                "Carbon intensity = total CO2e (kg) / total production (boe); undefined when production is zero.",
                "CO2 tax cost = annual CO2e (tonnes) * tax (USD/tonne); no allowances or quota trading.",
                "No combustion efficiency, methane slip, flaring, venting, or capture credit is modelled.",
                "Use NeqSim Standard_ISO6976, GasTurbine, and certified factors for real emission accounting.",
            ),
        )

    def _intensity_warning(self, carbon_intensity: float | None) -> str:
        if carbon_intensity is None:
            return "no-production"
        if carbon_intensity >= self.watch_intensity_kg_per_boe:
            return "high"
        if carbon_intensity >= 0.5 * self.watch_intensity_kg_per_boe:
            return "watch"
        return "ok"

    @classmethod
    def _normalize_series(cls, name: str, series: Sequence[float]) -> list[float]:
        try:
            values = [float(v) for v in series]
        except TypeError as exc:  # pragma: no cover - defensive
            raise ValueError(f"{name} must be a sequence of numbers") from exc
        for v in values:
            if not isfinite(v):
                raise ValueError(f"{name} values must be finite")
        return values

    @classmethod
    def _broadcast(
        cls, name: str, value: Sequence[float] | float, years: int
    ) -> list[float]:
        if isinstance(value, (int, float)):
            cls._require_non_negative(name, float(value))
            return [float(value)] * years
        series = cls._normalize_series(name, value)
        if len(series) != years:
            raise ValueError(f"{name} length must match annual_energy_use_mwh length")
        for v in series:
            if v < 0.0:
                raise ValueError(f"{name} values must be non-negative")
        return series

    @staticmethod
    def _require_positive(name: str, value: float) -> None:
        if not isfinite(value):
            raise ValueError(f"{name} must be finite")
        if value <= 0.0:
            raise ValueError(f"{name} must be positive")

    @staticmethod
    def _require_non_negative(name: str, value: float) -> None:
        if not isfinite(value):
            raise ValueError(f"{name} must be finite")
        if value < 0.0:
            raise ValueError(f"{name} must be non-negative")
