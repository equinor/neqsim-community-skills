from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite


@dataclass(frozen=True)
class FlowInducedVibrationResult:
    kinetic_energy_pa: float
    threshold_ratio: float
    likelihood_of_failure_band: str
    fiv_warning: str
    small_bore_flag: bool
    neqsim_available: bool
    assumptions: tuple[str, ...]


class FlowInducedVibrationModel:
    """Educational flow-induced vibration screening placeholder."""

    def __init__(
        self,
        watch_threshold: float = 0.8,
        high_threshold: float = 1.0,
        small_bore_factor: float = 0.6,
    ) -> None:
        self._require_positive("watch_threshold", watch_threshold)
        self._require_positive("high_threshold", high_threshold)
        self._require_positive("small_bore_factor", small_bore_factor)
        if watch_threshold >= high_threshold:
            raise ValueError("watch_threshold must be below high_threshold")
        if small_bore_factor >= 1.0:
            raise ValueError("small_bore_factor must be below 1.0")
        self.watch_threshold = watch_threshold
        self.high_threshold = high_threshold
        self.small_bore_factor = small_bore_factor

    def evaluate(
        self,
        *,
        fluid_velocity: float,
        mixture_density: float,
        kinetic_energy_threshold: float = 10000.0,
        small_bore_present: bool = False,
    ) -> FlowInducedVibrationResult:
        self._require_positive("fluid_velocity", fluid_velocity)
        self._require_positive("mixture_density", mixture_density)
        self._require_positive("kinetic_energy_threshold", kinetic_energy_threshold)

        kinetic_energy = mixture_density * fluid_velocity * fluid_velocity
        effective_threshold = kinetic_energy_threshold
        if small_bore_present:
            effective_threshold = kinetic_energy_threshold * self.small_bore_factor

        threshold_ratio = kinetic_energy / effective_threshold
        fiv_warning = self._warning(threshold_ratio)
        likelihood_band = self._likelihood_band(threshold_ratio)

        return FlowInducedVibrationResult(
            kinetic_energy_pa=round(kinetic_energy, 1),
            threshold_ratio=round(threshold_ratio, 4),
            likelihood_of_failure_band=likelihood_band,
            fiv_warning=fiv_warning,
            small_bore_flag=bool(small_bore_present),
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Fluid kinetic energy uses the public index FKE = rho v^2 in Pa.",
                "This is the primary driver in public Energy Institute style FIV screening.",
                "A small-bore connection lowers the effective screening threshold.",
                "No proprietary Energy Institute scoring tables or fatigue logic are used.",
                "Move to a validated FIV likelihood-of-failure assessment and qualified review.",
            ),
        )

    def _warning(self, threshold_ratio: float) -> str:
        if threshold_ratio > self.high_threshold:
            return "high"
        if threshold_ratio > self.watch_threshold:
            return "watch"
        return "ok"

    def _likelihood_band(self, threshold_ratio: float) -> str:
        if threshold_ratio > self.high_threshold:
            return "high"
        if threshold_ratio > self.watch_threshold:
            return "medium"
        return "low"

    @staticmethod
    def _require_finite(name: str, value: float) -> None:
        if not isfinite(value):
            raise ValueError(f"{name} must be finite")

    @classmethod
    def _require_positive(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value <= 0.0:
            raise ValueError(f"{name} must be positive")
