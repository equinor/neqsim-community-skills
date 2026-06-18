from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from typing import Iterable


# Public simplified API RP 14C / ISO 10418 protective-function defaults per component type.
_REQUIRED_FUNCTIONS: dict[str, tuple[str, ...]] = {
    "pressure_vessel": ("PSH", "PSL", "PSV", "LSH"),
    "separator": ("PSH", "PSL", "PSV", "LSH", "LSL"),
    "gas_pipeline_segment": ("PSH", "PSL", "PSV"),
    "liquid_pipeline_segment": ("PSH", "PSL", "PSV"),
    "fired_heater": ("PSH", "PSL", "TSH", "PSV", "BSDV"),
    "compressor": ("PSH", "PSL", "TSH", "PSV"),
    "pump": ("PSH", "PSL", "PSV"),
    "wellhead": ("PSH", "PSL", "PSV", "BSDV"),
}


@dataclass(frozen=True)
class SafetyFunctionCoverageResult:
    component_type: str
    required_functions: tuple[str, ...]
    provided_functions: tuple[str, ...]
    missing_functions: tuple[str, ...]
    coverage_ratio: float
    coverage_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class SafetyFunctionCoverageModel:
    """Educational API RP 14C / ISO 10418 safety-function coverage screening placeholder."""

    def __init__(self, watch_threshold: float = 1.0) -> None:
        if not 0.0 < watch_threshold <= 1.0:
            raise ValueError("watch_threshold must be in the interval (0, 1]")
        self.watch_threshold = watch_threshold

    def evaluate(
        self,
        *,
        component_type: str,
        provided_functions: Iterable[str],
    ) -> SafetyFunctionCoverageResult:
        normalized_type = self._normalize_type(component_type)
        required = _REQUIRED_FUNCTIONS[normalized_type]
        provided = self._normalize_functions(provided_functions)

        missing = tuple(code for code in required if code not in provided)
        coverage_ratio = (len(required) - len(missing)) / len(required)
        warning = self._warning(missing, coverage_ratio)

        return SafetyFunctionCoverageResult(
            component_type=normalized_type,
            required_functions=required,
            provided_functions=provided,
            missing_functions=missing,
            coverage_ratio=round(coverage_ratio, 4),
            coverage_warning=warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Required-function sets are simplified public API RP 14C / ISO 10418 defaults.",
                "No undesirable-event analysis, alternate protection, or reliability is assessed.",
                "Move to a formal SAFE chart and the NeqSim SafetyAnalysisFunctionEvaluation class.",
            ),
        )

    def _warning(self, missing: tuple[str, ...], coverage_ratio: float) -> str:
        if missing:
            return "gap"
        if coverage_ratio < self.watch_threshold:
            return "watch"
        return "ok"

    @staticmethod
    def _normalize_type(component_type: str) -> str:
        if not isinstance(component_type, str):
            raise ValueError("component_type must be a string")
        key = component_type.strip().lower().replace(" ", "_").replace("-", "_")
        if key not in _REQUIRED_FUNCTIONS:
            supported = ", ".join(sorted(_REQUIRED_FUNCTIONS))
            raise ValueError(f"component_type must be one of: {supported}")
        return key

    @staticmethod
    def _normalize_functions(provided_functions: Iterable[str]) -> tuple[str, ...]:
        normalized: list[str] = []
        for code in provided_functions:
            if not isinstance(code, str):
                raise ValueError("provided_functions must contain strings")
            token = code.strip().upper()
            if not token:
                raise ValueError("provided_functions must not contain blank codes")
            if token not in normalized:
                normalized.append(token)
        return tuple(normalized)
