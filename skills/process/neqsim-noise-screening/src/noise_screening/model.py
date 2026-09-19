from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite, log10, sqrt

_BAR_TO_PA = 1.0e5
_R_UNIVERSAL = 8314.0  # J/(kmol K) when used with molar mass in g/mol
_REF_SOUND_POWER = 1.0e-12  # W (reference for sound power level)


@dataclass(frozen=True)
class ValveNoiseResult:
    vena_contracta_velocity_m_s: float
    mach_number: float
    internal_sound_power_level_db: float
    estimated_spl_1m_dba: float
    estimated_spl_at_distance_dba: float
    assessment_distance_m: float
    assessment_basis: str
    noise_warning: str
    uncertainty_db: float
    standards_basis: tuple[str, ...]
    neqsim_available: bool
    assumptions: tuple[str, ...]


class ValveNoiseModel:
    """Educational valve/line aerodynamic-noise indicator placeholder.

    Estimates a screening sound-pressure-level indicator from the gas mass flow,
    pressure drop, and density using a public IEC 60534-8 style energy approach.
    """

    def __init__(
        self,
        action_level: float = 85.0,
        high_level: float = 110.0,
        acoustic_efficiency_factor: float = 1.0e-4,
        transmission_loss: float = 45.0,
        uncertainty_db: float = 10.0,
    ) -> None:
        self._require_positive("action_level", action_level)
        self._require_positive("high_level", high_level)
        self._require_positive("acoustic_efficiency_factor", acoustic_efficiency_factor)
        self._require_finite("transmission_loss", transmission_loss)
        self._require_positive("uncertainty_db", uncertainty_db)
        if high_level <= action_level:
            raise ValueError("high_level must be greater than action_level")
        self.action_level = action_level
        self.high_level = high_level
        self.acoustic_efficiency_factor = acoustic_efficiency_factor
        self.transmission_loss = transmission_loss
        self.uncertainty_db = uncertainty_db

    def evaluate(
        self,
        *,
        mass_flow: float,
        pressure_drop: float,
        inlet_density: float,
        sound_speed: float | None = None,
        specific_heat_ratio: float = 1.3,
        temperature: float | None = None,
        molar_mass: float | None = None,
        distance: float = 1.0,
        measured_spl_at_distance: float | None = None,
        measured_uncertainty_db: float | None = None,
    ) -> ValveNoiseResult:
        self._require_positive("mass_flow", mass_flow)
        self._require_positive("pressure_drop", pressure_drop)
        self._require_positive("inlet_density", inlet_density)
        self._require_positive("distance", distance)
        if measured_spl_at_distance is not None:
            self._require_positive("measured_spl_at_distance", measured_spl_at_distance)
        if measured_uncertainty_db is not None:
            self._require_positive("measured_uncertainty_db", measured_uncertainty_db)
            if measured_spl_at_distance is None:
                raise ValueError(
                    "measured_uncertainty_db requires measured_spl_at_distance"
                )

        # Vena-contracta velocity from a simple energy balance across the drop.
        velocity = sqrt(2.0 * pressure_drop * _BAR_TO_PA / inlet_density)

        speed_of_sound = self._sound_speed(
            sound_speed, specific_heat_ratio, temperature, molar_mass
        )
        mach = velocity / speed_of_sound

        # Mechanical stream power and acoustic conversion (capped efficiency).
        mechanical_power = 0.5 * mass_flow * velocity * velocity
        acoustic_efficiency = min(0.01, self.acoustic_efficiency_factor * mach**3)
        acoustic_power = max(acoustic_efficiency * mechanical_power, 1.0e-20)

        sound_power_level = 10.0 * log10(acoustic_power / _REF_SOUND_POWER)
        spl_1m = sound_power_level - self.transmission_loss
        spl_at_distance = (
            measured_spl_at_distance
            if measured_spl_at_distance is not None
            else spl_1m - 20.0 * log10(distance)
        )
        result_uncertainty = (
            measured_uncertainty_db
            if measured_uncertainty_db is not None
            else self.uncertainty_db
        )
        warning = self._warning(spl_at_distance)

        return ValveNoiseResult(
            vena_contracta_velocity_m_s=round(velocity, 3),
            mach_number=round(mach, 4),
            internal_sound_power_level_db=round(sound_power_level, 2),
            estimated_spl_1m_dba=round(spl_1m, 2),
            estimated_spl_at_distance_dba=round(spl_at_distance, 2),
            assessment_distance_m=round(distance, 3),
            assessment_basis=(
                "measurement"
                if measured_spl_at_distance is not None
                else "screening-model"
            ),
            noise_warning=warning,
            uncertainty_db=result_uncertainty,
            standards_basis=(
                "IEC 60534-8-3: detailed aerodynamic control-valve noise prediction",
                "ISO 3744: sound-power determination from sound-pressure measurements",
                "ISO 11201: emission sound-pressure measurement at a work station",
                "ISO 9613-2: outdoor sound propagation",
                "ISO 15664: noise-control design procedures for open plant",
                "ISO 1999: occupational noise exposure and hearing-risk estimation",
            ),
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening indicator only, not a full IEC 60534-8-3 prediction.",
                "Vena-contracta velocity from a simple energy balance across the drop.",
                "Acoustic power = min(0.01, eta_f * Mach^3) * 0.5 * mdot * v^2.",
                "A fixed transmission loss converts internal power level to a 1 m SPL.",
                "Distance correction uses free-field spherical spreading only.",
                "No valve style, trim, pipe schedule, or frequency weighting.",
                "Action thresholds are configurable project inputs, not ISO limits.",
                "Move to validated NeqSim valve / IEC 60534-8 tools and qualified review.",
            ),
        )

    def _sound_speed(
        self,
        sound_speed: float | None,
        specific_heat_ratio: float,
        temperature: float | None,
        molar_mass: float | None,
    ) -> float:
        if sound_speed is not None:
            self._require_positive("sound_speed", sound_speed)
            return sound_speed
        if temperature is None or molar_mass is None:
            raise ValueError(
                "provide sound_speed, or temperature and molar_mass to estimate it"
            )
        if specific_heat_ratio <= 1.0:
            raise ValueError("specific_heat_ratio must be greater than 1")
        self._require_positive("temperature", temperature)
        self._require_positive("molar_mass", molar_mass)
        return sqrt(specific_heat_ratio * _R_UNIVERSAL * temperature / molar_mass)

    def _warning(self, spl_1m: float) -> str:
        if spl_1m >= self.high_level:
            return "high"
        if spl_1m >= self.action_level:
            return "action"
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
