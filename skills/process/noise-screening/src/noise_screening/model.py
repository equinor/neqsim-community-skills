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
    noise_warning: str
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
    ) -> None:
        self._require_positive("action_level", action_level)
        self._require_positive("high_level", high_level)
        self._require_positive("acoustic_efficiency_factor", acoustic_efficiency_factor)
        self._require_finite("transmission_loss", transmission_loss)
        if high_level <= action_level:
            raise ValueError("high_level must be greater than action_level")
        self.action_level = action_level
        self.high_level = high_level
        self.acoustic_efficiency_factor = acoustic_efficiency_factor
        self.transmission_loss = transmission_loss

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
    ) -> ValveNoiseResult:
        self._require_positive("mass_flow", mass_flow)
        self._require_positive("pressure_drop", pressure_drop)
        self._require_positive("inlet_density", inlet_density)

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
        warning = self._warning(spl_1m)

        return ValveNoiseResult(
            vena_contracta_velocity_m_s=round(velocity, 3),
            mach_number=round(mach, 4),
            internal_sound_power_level_db=round(sound_power_level, 2),
            estimated_spl_1m_dba=round(spl_1m, 2),
            noise_warning=warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening indicator only, not a full IEC 60534-8-3 prediction.",
                "Vena-contracta velocity from a simple energy balance across the drop.",
                "Acoustic power = min(0.01, eta_f * Mach^3) * 0.5 * mdot * v^2.",
                "A fixed transmission loss converts internal power level to a 1 m SPL.",
                "No valve style, trim, pipe schedule, or frequency weighting.",
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
        if spl_1m > self.high_level:
            return "high"
        if spl_1m > self.action_level:
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
