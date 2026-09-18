from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite

# Molar mass of CO2 in kg/mol.
_M_CO2 = 44.01e-3
_SECONDS_PER_DAY = 86400.0

# Carbon atoms per molecule for common fuel-gas components.
_CARBON_NUMBER: dict[str, int] = {
    "methane": 1,
    "ethane": 2,
    "propane": 3,
    "n-butane": 4,
    "i-butane": 4,
    "isobutane": 4,
    "n-pentane": 5,
    "i-pentane": 5,
    "isopentane": 5,
    "n-hexane": 6,
    "hexane": 6,
    "co2": 1,
    "carbon dioxide": 1,
    "co": 1,
    "carbon monoxide": 1,
    "nitrogen": 0,
    "hydrogen": 0,
    "water": 0,
    "oxygen": 0,
    "h2s": 0,
    "hydrogen sulfide": 0,
    "helium": 0,
}

# Molar mass in g/mol for the mixture molecular-weight estimate.
_MOLAR_MASS_G: dict[str, float] = {
    "methane": 16.043,
    "ethane": 30.070,
    "propane": 44.097,
    "n-butane": 58.123,
    "i-butane": 58.123,
    "isobutane": 58.123,
    "n-pentane": 72.150,
    "i-pentane": 72.150,
    "isopentane": 72.150,
    "n-hexane": 86.177,
    "hexane": 86.177,
    "co2": 44.010,
    "carbon dioxide": 44.010,
    "co": 28.010,
    "carbon monoxide": 28.010,
    "nitrogen": 28.014,
    "hydrogen": 2.016,
    "water": 18.015,
    "oxygen": 31.998,
    "h2s": 34.081,
    "hydrogen sulfide": 34.081,
    "helium": 4.003,
}


@dataclass(frozen=True)
class CombustionCO2Result:
    mixture_molecular_weight_g_mol: float
    carbon_per_mole_fuel: float
    co2_mass_rate_kg_s: float
    co2_mass_rate_t_per_day: float
    specific_co2_kg_per_kg_fuel: float
    emission_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class CombustionCO2Model:
    """Educational combustion-CO2 emission screening placeholder.

    Estimates the CO2 mass rate from full combustion of a fuel-gas stream using
    public per-component carbon counts and the IPCC stoichiometric basis.
    """

    def __init__(self) -> None:
        pass

    def evaluate(
        self,
        *,
        composition: dict[str, float],
        molar_flow: float | None = None,
        mass_flow: float | None = None,
        co2_limit_t_per_day: float | None = None,
    ) -> CombustionCO2Result:
        if not composition:
            raise ValueError("composition must contain at least one component")
        if (molar_flow is None) == (mass_flow is None):
            raise ValueError("provide exactly one of molar_flow or mass_flow")
        if molar_flow is not None:
            self._require_positive("molar_flow", molar_flow)
        if mass_flow is not None:
            self._require_positive("mass_flow", mass_flow)
        if co2_limit_t_per_day is not None:
            self._require_positive("co2_limit_t_per_day", co2_limit_t_per_day)

        normalized = self._normalize(composition)
        carbon_per_mole = 0.0
        mixture_mw_g = 0.0
        for name, fraction in normalized.items():
            if name not in _CARBON_NUMBER:
                raise ValueError(f"unsupported component: {name}")
            carbon_per_mole += fraction * _CARBON_NUMBER[name]
            mixture_mw_g += fraction * _MOLAR_MASS_G[name]

        mixture_mw_kg = mixture_mw_g / 1000.0
        if molar_flow is not None:
            molar_flow_mol_s = molar_flow
        else:
            molar_flow_mol_s = mass_flow / mixture_mw_kg

        co2_mass_rate_kg_s = molar_flow_mol_s * carbon_per_mole * _M_CO2
        fuel_mass_rate_kg_s = molar_flow_mol_s * mixture_mw_kg
        specific_co2 = co2_mass_rate_kg_s / fuel_mass_rate_kg_s
        co2_t_per_day = co2_mass_rate_kg_s * _SECONDS_PER_DAY / 1000.0

        warning = self._warning(co2_t_per_day, co2_limit_t_per_day)

        return CombustionCO2Result(
            mixture_molecular_weight_g_mol=round(mixture_mw_g, 4),
            carbon_per_mole_fuel=round(carbon_per_mole, 6),
            co2_mass_rate_kg_s=round(co2_mass_rate_kg_s, 6),
            co2_mass_rate_t_per_day=round(co2_t_per_day, 4),
            specific_co2_kg_per_kg_fuel=round(specific_co2, 4),
            emission_warning=warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Complete combustion: every fuel carbon atom becomes one CO2.",
                "CO2 in the feed is carried through and counted as emitted CO2.",
                "Composition is mole fractions, normalized to sum to one.",
                "No combustion efficiency, slip, flaring, or capture credit.",
                "Move to validated NeqSim combustion / ISO 6976 tools and qualified review.",
            ),
        )

    @staticmethod
    def _normalize(composition: dict[str, float]) -> dict[str, float]:
        cleaned: dict[str, float] = {}
        total = 0.0
        for name, fraction in composition.items():
            if not isfinite(fraction):
                raise ValueError(f"fraction for {name} must be finite")
            if fraction < 0.0:
                raise ValueError(f"fraction for {name} must not be negative")
            key = name.strip().lower()
            cleaned[key] = cleaned.get(key, 0.0) + fraction
            total += fraction
        if total <= 0.0:
            raise ValueError("composition fractions must sum to a positive value")
        return {name: fraction / total for name, fraction in cleaned.items()}

    def _warning(
        self,
        co2_t_per_day: float,
        co2_limit_t_per_day: float | None,
    ) -> str:
        if co2_limit_t_per_day is None:
            return "no-limit"
        if co2_t_per_day > co2_limit_t_per_day:
            return "over-limit"
        return "ok"

    @staticmethod
    def _require_finite(name: str, value: float) -> None:
        if not isfinite(value):
            raise ValueError(f"{name} must be finite")

    @classmethod
    def _require_positive(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value <= 0.0:
            raise ValueError(f"{name} must be positive")
