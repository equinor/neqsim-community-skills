from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite


@dataclass(frozen=True)
class PipeWallThicknessResult:
    pressure_design_thickness_mm: float
    required_thickness_mm: float
    nominal_thickness_mm: float
    thickness_margin_ratio: float
    wall_thickness_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class PipeWallThicknessModel:
    """Educational ASME B31.3 pressure-design wall-thickness screening placeholder."""

    def __init__(
        self,
        watch_threshold: float = 1.1,
        inadequate_threshold: float = 1.0,
    ) -> None:
        self._require_positive("watch_threshold", watch_threshold)
        self._require_positive("inadequate_threshold", inadequate_threshold)
        if watch_threshold <= inadequate_threshold:
            raise ValueError("watch_threshold must be above inadequate_threshold")
        self.watch_threshold = watch_threshold
        self.inadequate_threshold = inadequate_threshold

    def evaluate(
        self,
        *,
        design_pressure: float,
        outer_diameter: float,
        allowable_stress: float,
        weld_joint_factor: float = 1.0,
        coefficient_y: float = 0.4,
        corrosion_allowance: float = 3.0,
        nominal_thickness: float,
    ) -> PipeWallThicknessResult:
        self._require_positive("design_pressure", design_pressure)
        self._require_positive("outer_diameter", outer_diameter)
        self._require_positive("allowable_stress", allowable_stress)
        self._require_positive("weld_joint_factor", weld_joint_factor)
        self._require_non_negative("coefficient_y", coefficient_y)
        self._require_non_negative("corrosion_allowance", corrosion_allowance)
        self._require_positive("nominal_thickness", nominal_thickness)

        # Work in consistent units: pressure bar -> MPa (1 bar = 0.1 MPa).
        pressure_mpa = design_pressure * 0.1
        # ASME B31.3 internal pressure design thickness, weld factor W taken as 1.0.
        denominator = 2.0 * (
            allowable_stress * weld_joint_factor + pressure_mpa * coefficient_y
        )
        pressure_design_thickness = pressure_mpa * outer_diameter / denominator
        required_thickness = pressure_design_thickness + corrosion_allowance
        margin_ratio = nominal_thickness / required_thickness
        warning = self._warning(margin_ratio)

        return PipeWallThicknessResult(
            pressure_design_thickness_mm=round(pressure_design_thickness, 4),
            required_thickness_mm=round(required_thickness, 4),
            nominal_thickness_mm=round(nominal_thickness, 4),
            thickness_margin_ratio=round(margin_ratio, 4),
            wall_thickness_warning=warning,
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational screening placeholder only.",
                "Pressure-design thickness uses the public ASME B31.3 form "
                "t = P D / (2 (S E W + P Y)) with W = 1.0.",
                "Required thickness adds a configurable corrosion and mechanical allowance.",
                "No mill tolerance, bend thinning, external pressure, or combined stresses are included.",
                "Move to validated NeqSim mechanical design (PipelineMechanicalDesign) and qualified review.",
            ),
        )

    def _warning(self, margin_ratio: float) -> str:
        if margin_ratio < self.inadequate_threshold:
            return "inadequate"
        if margin_ratio < self.watch_threshold:
            return "watch"
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

    @classmethod
    def _require_non_negative(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value < 0.0:
            raise ValueError(f"{name} must be non-negative")
