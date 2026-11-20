"""Screening-level checks for hot tapping a live subsea pipeline."""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass

Table = tuple[tuple[float, float], ...]


def interpolate(table: Table, x: float) -> tuple[float, bool]:
    """Linear interpolation on an (x, y) table; the end value is held outside it.

    Returns ``(value, extrapolated)`` so the caller can report a data gap.
    """
    if not table:
        raise ValueError("table is empty")
    points = sorted(table)
    if x <= points[0][0]:
        return points[0][1], x < points[0][0]
    if x >= points[-1][0]:
        return points[-1][1], x > points[-1][0]
    for (x0, y0), (x1, y1) in itertools.pairwise(points):
        if x0 <= x <= x1:
            return y0 + (x - x0) / (x1 - x0) * (y1 - y0), False
    raise AssertionError("unreachable")


@dataclass(frozen=True)
class RunPipe:
    """The live line that is tapped."""

    outer_diameter_m: float
    wall_m: float
    smys_mpa: float
    corrosion_allowance_m: float = 0.0
    design_factor: float = 0.72

    def __post_init__(self) -> None:
        if not self.outer_diameter_m > 0.0 or not self.smys_mpa > 0.0:
            raise ValueError("diameter and smys_mpa must be positive")
        if not 0.0 < self.wall_m < self.outer_diameter_m / 2.0:
            raise ValueError("wall_m must be between 0 and half the diameter")
        if not 0.0 <= self.corrosion_allowance_m < self.wall_m:
            raise ValueError("corrosion_allowance_m must be below the wall")
        if not 0.0 < self.design_factor <= 1.0:
            raise ValueError("design_factor must be in (0, 1]")

    @property
    def inner_diameter_m(self) -> float:
        """Inner diameter in metres."""
        return self.outer_diameter_m - 2.0 * self.wall_m


@dataclass(frozen=True)
class HotTapTee:
    """Hot-tap clamp and branch; all ratings come from the vendor."""

    cutter_diameter_m: float
    pressure_rating_bar: Table
    max_temperature_c: float
    max_branch_ratio: float = 0.5
    allowable_branch_moment_knm: float | None = None

    def __post_init__(self) -> None:
        if not self.cutter_diameter_m > 0.0:
            raise ValueError("cutter_diameter_m must be positive")
        if not self.pressure_rating_bar:
            raise ValueError("pressure_rating_bar table is required")
        if not 0.0 < self.max_branch_ratio <= 1.0:
            raise ValueError("max_branch_ratio must be in (0, 1]")


@dataclass(frozen=True)
class HotTapCase:
    """Conditions at the tap location while the line is live."""

    operating_pressure_bar: float
    temperature_c: float
    flow_rate_m3_h: float
    max_cutting_velocity_ms: float | None = None
    hydrate_temperature_c: float | None = None
    min_hydrate_margin_k: float = 3.0
    cutter_feed_mm_min: float | None = None
    branch_weight_kn: float | None = None
    lever_arm_m: float | None = None


@dataclass(frozen=True)
class Check:
    """One screening check: ``pass``, ``fail``, ``info`` or ``data_gap``."""

    name: str
    status: str
    value: float | None
    limit: float | None
    unit: str
    note: str = ""

    @property
    def utilisation(self) -> float | None:
        """Value divided by limit, when both exist and the limit is positive."""
        if self.value is None or self.limit is None or self.limit <= 0.0:
            return None
        return self.value / self.limit


@dataclass(frozen=True)
class HotTapResult:
    """All checks, data gaps and the stated assumptions."""

    checks: dict[str, Check]
    data_gaps: tuple[str, ...]
    assumptions: tuple[str, ...]
    overall: str


def minimum_wall_m(pipe: RunPipe, pressure_bar: float) -> float:
    """Hoop minimum wall ``P D / (2 SMYS F)`` for the operating pressure."""
    return (
        pressure_bar
        * 0.1
        * pipe.outer_diameter_m
        / (2.0 * pipe.smys_mpa * pipe.design_factor)
    )


def line_velocity_ms(pipe: RunPipe, flow_rate_m3_h: float) -> float:
    """Mean velocity at the tap from the actual volumetric flow."""
    area = math.pi / 4.0 * pipe.inner_diameter_m**2
    return flow_rate_m3_h / 3600.0 / area


def _status(passes: bool) -> str:
    return "pass" if passes else "fail"


def screen(pipe: RunPipe, tee: HotTapTee, case: HotTapCase) -> HotTapResult:
    """Run the hot-tap screening checks for one location and condition."""
    checks: dict[str, Check] = {}
    gaps: list[str] = []

    ratio = tee.cutter_diameter_m / pipe.outer_diameter_m
    checks["branch_ratio"] = Check(
        "branch_ratio",
        _status(ratio <= tee.max_branch_ratio),
        ratio,
        tee.max_branch_ratio,
        "-",
        "cutter diameter over run outer diameter",
    )

    rating, extrapolated = interpolate(tee.pressure_rating_bar, case.temperature_c)
    if extrapolated:
        gaps.append(
            "tee pressure rating table does not cover the operating temperature"
        )
    checks["pressure_rating"] = Check(
        "pressure_rating",
        _status(case.operating_pressure_bar <= rating),
        case.operating_pressure_bar,
        rating,
        "bar",
        "operating pressure against the tee rating",
    )
    checks["temperature"] = Check(
        "temperature",
        _status(case.temperature_c <= tee.max_temperature_c),
        case.temperature_c,
        tee.max_temperature_c,
        "C",
    )

    available = pipe.wall_m - pipe.corrosion_allowance_m
    required = minimum_wall_m(pipe, case.operating_pressure_bar)
    checks["remaining_wall"] = Check(
        "remaining_wall",
        _status(available >= required),
        required,
        available,
        "m",
        "hoop minimum wall (value) against wall less corrosion allowance (limit)",
    )

    velocity = line_velocity_ms(pipe, case.flow_rate_m3_h)
    if case.max_cutting_velocity_ms is None:
        gaps.append("maximum flow velocity during cutting not supplied")
        checks["cutting_velocity"] = Check(
            "cutting_velocity", "data_gap", velocity, None, "m/s"
        )
    else:
        checks["cutting_velocity"] = Check(
            "cutting_velocity",
            _status(velocity <= case.max_cutting_velocity_ms),
            velocity,
            case.max_cutting_velocity_ms,
            "m/s",
            "line velocity while cutting",
        )

    if case.hydrate_temperature_c is None:
        gaps.append("hydrate formation temperature at the tap pressure not supplied")
        checks["hydrate_margin"] = Check("hydrate_margin", "data_gap", None, None, "K")
    else:
        margin = case.temperature_c - case.hydrate_temperature_c
        checks["hydrate_margin"] = Check(
            "hydrate_margin",
            _status(margin >= case.min_hydrate_margin_k),
            margin,
            case.min_hydrate_margin_k,
            "K",
            "operating temperature minus hydrate temperature; local cooling at the cutter is not modelled",
        )

    if (
        tee.allowable_branch_moment_knm is None
        or case.branch_weight_kn is None
        or case.lever_arm_m is None
    ):
        gaps.append("branch weight, lever arm or allowable branch moment not supplied")
        checks["branch_moment"] = Check("branch_moment", "data_gap", None, None, "kNm")
    else:
        moment = case.branch_weight_kn * case.lever_arm_m
        checks["branch_moment"] = Check(
            "branch_moment",
            _status(moment <= tee.allowable_branch_moment_knm),
            moment,
            tee.allowable_branch_moment_knm,
            "kNm",
            "submerged weight times lever arm",
        )

    if case.cutter_feed_mm_min is not None and case.cutter_feed_mm_min > 0.0:
        minutes = pipe.wall_m * 1000.0 / case.cutter_feed_mm_min
        checks["cutting_time"] = Check(
            "cutting_time",
            "info",
            minutes,
            None,
            "min",
            "wall thickness over cutter feed rate",
        )

    assumptions = (
        f"branch ratio limit {tee.max_branch_ratio:g} is a screening value; use the clamp vendor limit",
        f"hoop design factor {pipe.design_factor:g} is taken from the run pipe input",
        "operating pressure is the maximum at the tap during the whole operation",
    )
    failed = any(c.status == "fail" for c in checks.values())
    overall = "fail" if failed else ("incomplete" if gaps else "pass")
    return HotTapResult(checks, tuple(dict.fromkeys(gaps)), assumptions, overall)
