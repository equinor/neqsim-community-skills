from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite
from typing import Mapping, Sequence


FLAG_ALIASES = {
    "water": {"water", "h2o"},
    "CO2": {"co2", "carbon dioxide"},
    "H2S": {"h2s", "hydrogen sulfide", "hydrogen sulphide"},
}


@dataclass(frozen=True)
class FluidQualityResult:
    total_fraction: float
    total_within_tolerance: bool
    negative_components: tuple[str, ...]
    missing_components: tuple[str, ...]
    flagged_components: dict[str, float]
    warnings: tuple[str, ...]
    is_usable: bool
    neqsim_available: bool


class FluidQualityChecker:
    """Public composition quality checks before simulation."""

    def __init__(
        self,
        required_components: Sequence[str] = ("methane",),
        tolerance: float = 1.0e-6,
    ) -> None:
        if tolerance <= 0.0 or not isfinite(tolerance):
            raise ValueError("tolerance must be a positive finite number")
        self.required_components = tuple(required_components)
        self.tolerance = tolerance

    def check(self, composition: Mapping[str, float]) -> FluidQualityResult:
        if not composition:
            raise ValueError("composition must contain at least one component")

        normalized = {self._normalize_name(name): value for name, value in composition.items()}
        for name, value in normalized.items():
            if not isfinite(value):
                raise ValueError(f"fraction for {name} must be finite")

        total_fraction = sum(normalized.values())
        total_within_tolerance = abs(total_fraction - 1.0) <= self.tolerance
        negative_components = tuple(
            original_name
            for original_name, value in composition.items()
            if value < 0.0
        )
        missing_components = tuple(
            component
            for component in self.required_components
            if self._normalize_name(component) not in normalized
        )
        flagged_components = self._flagged_components(normalized)
        warnings = self._warnings(
            total_fraction,
            total_within_tolerance,
            negative_components,
            missing_components,
            flagged_components,
        )

        return FluidQualityResult(
            total_fraction=round(total_fraction, 10),
            total_within_tolerance=total_within_tolerance,
            negative_components=negative_components,
            missing_components=missing_components,
            flagged_components=flagged_components,
            warnings=warnings,
            is_usable=not negative_components and not missing_components and total_within_tolerance,
            neqsim_available=find_spec("neqsim") is not None,
        )

    @staticmethod
    def _normalize_name(name: str) -> str:
        return " ".join(name.strip().lower().replace("_", " ").replace("-", " ").split())

    @classmethod
    def _flagged_components(cls, normalized: Mapping[str, float]) -> dict[str, float]:
        flags: dict[str, float] = {}
        for display_name, aliases in FLAG_ALIASES.items():
            value = sum(value for name, value in normalized.items() if name in aliases)
            if value > 0.0:
                flags[display_name] = round(value, 10)
        return flags

    @staticmethod
    def _warnings(
        total_fraction: float,
        total_within_tolerance: bool,
        negative_components: tuple[str, ...],
        missing_components: tuple[str, ...],
        flagged_components: Mapping[str, float],
    ) -> tuple[str, ...]:
        warnings: list[str] = []
        if not total_within_tolerance:
            warnings.append(f"composition sum is {total_fraction:.8f}, expected 1.0")
        if negative_components:
            warnings.append("negative fractions: " + ", ".join(negative_components))
        if missing_components:
            warnings.append("missing required components: " + ", ".join(missing_components))
        for component in flagged_components:
            warnings.append(f"{component} present; check whether this matters for the simulation basis")
        return tuple(warnings)