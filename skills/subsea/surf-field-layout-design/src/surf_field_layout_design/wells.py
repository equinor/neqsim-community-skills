"""Screening well trajectories from a subsea drill centre down to a reservoir target.

Each well is drawn as a vertical section from the tree to a kick-off point, a
build section that lands at the top of the reservoir, and a horizontal drain
inside it. The build rate that geometry implies is reported, because a shallow
reservoir under deep water forces a high dogleg severity and that is often what
decides whether the architecture is drillable at all.

This is illustration and screening geometry, not a well plan: no torque and drag,
no anti-collision, no casing or completion design, no geosteering.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, ceil, cos, degrees, hypot, radians, sin
from typing import Sequence

from .geo import LocalFrame
from .layout import SurfLayout, _place

#: Build rate above which a screening trajectory should be flagged, deg per 30 m.
MAX_SCREENING_DOGLEG_DEG_PER_30M = 6.0


@dataclass(frozen=True)
class WellPath:
    """A screening trajectory for one well."""

    well_tag: str
    service: str
    drill_centre: str
    points: tuple[tuple[float, float, float], ...]
    geographic: tuple[tuple[float, float, float], ...]
    kick_off_tvd_m: float
    landing_tvd_m: float
    reservoir_target_tvd_m: float
    horizontal_step_out_m: float
    horizontal_section_m: float
    measured_depth_m: float
    build_rate_deg_per_30m: float
    drillable: bool

    def to_dict(self) -> dict:
        return {
            "well": self.well_tag,
            "service": self.service,
            "drill_centre": self.drill_centre,
            "kick_off_tvd_m": round(self.kick_off_tvd_m, 1),
            "landing_tvd_m": round(self.landing_tvd_m, 1),
            "reservoir_target_tvd_m": round(self.reservoir_target_tvd_m, 1),
            "horizontal_step_out_m": round(self.horizontal_step_out_m, 1),
            "horizontal_section_m": round(self.horizontal_section_m, 1),
            "measured_depth_m": round(self.measured_depth_m, 1),
            "build_rate_deg_per_30m": round(self.build_rate_deg_per_30m, 2),
            "drillable": self.drillable,
        }


def _arc(
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    segments: int = 12,
) -> list[tuple[float, float, float]]:
    """Smooth build section: vertical at the kick-off, horizontal at the landing."""
    points = []
    for index in range(1, segments + 1):
        fraction = index / segments
        # sine easing keeps the tangent vertical at the start and flat at the end
        horizontal = sin(fraction * radians(90.0))
        vertical = 1.0 - cos(fraction * radians(90.0))
        points.append(
            (
                start[0] + (end[0] - start[0]) * horizontal,
                start[1] + (end[1] - start[1]) * horizontal,
                start[2] + (end[2] - start[2]) * vertical,
            )
        )
    return points


def build_well_paths(
    layout: SurfLayout,
    *,
    reservoir_depth_m_tvdmsl: float,
    net_pay_m: float = 45.0,
    kick_off_below_seabed_m: float = 80.0,
    horizontal_section_m: float = 1500.0,
    target_spread_fraction: float = 0.85,
    field_axis_bearing_deg: float = 0.0,
    injector_offset_km: float = 1.2,
    reservoir_length_km: float | None = None,
) -> list[WellPath]:
    """Lay out one screening trajectory per well in ``layout``.

    Wells of each service fan out from their drill centres onto targets spread
    along the field axis, in the across-axis band their service occupies.
    """
    if reservoir_depth_m_tvdmsl <= 0.0:
        raise ValueError("reservoir_depth_m_tvdmsl must be positive")
    if net_pay_m <= 0.0:
        raise ValueError("net_pay_m must be positive")

    frame: LocalFrame = layout.frame
    length_km = reservoir_length_km or layout.summary.get("reservoir_length_km") or 6.0
    usable_m = length_km * 1000.0 * target_spread_fraction
    # the toe must stay inside the footprint, so the heels only spread over what is
    # left once the horizontal drain is subtracted
    drain_m = min(horizontal_section_m, 0.8 * usable_m)
    heel_span = max(usable_m - drain_m, 0.0)
    heel_start = -usable_m / 2.0

    bands = {
        "production": 0.0,
        "water_injection": -injector_offset_km * 1000.0,
        "gas_injection": +injector_offset_km * 1000.0,
    }

    wells = [node for node in layout.nodes if node.kind == "well"]
    by_service: dict[str, list] = {}
    for well in wells:
        by_service.setdefault(well.attributes.get("service", "production"), []).append(well)

    paths: list[WellPath] = []
    for service, service_wells in by_service.items():
        across = bands.get(service, 0.0)
        count = len(service_wells)
        for index, well in enumerate(sorted(service_wells, key=lambda node: node.tag)):
            fraction = 0.5 if count == 1 else index / (count - 1)
            along = heel_start + fraction * heel_span
            heel_east, heel_north = _place(along, across, field_axis_bearing_deg)
            toe_east, toe_north = _place(along + drain_m, across, field_axis_bearing_deg)

            seabed_tvd = well.water_depth_m
            kick_off_tvd = seabed_tvd + kick_off_below_seabed_m
            landing_tvd = reservoir_depth_m_tvdmsl
            drain_tvd = reservoir_depth_m_tvdmsl + net_pay_m * 0.5

            tree = (well.east_m, well.north_m, seabed_tvd)
            kick_off = (well.east_m, well.north_m, kick_off_tvd)
            heel = (heel_east, heel_north, landing_tvd)
            toe = (toe_east, toe_north, drain_tvd)

            points = [tree, kick_off] + _arc(kick_off, heel) + [toe]
            geographic = tuple(
                frame.to_geographic(east, north) + (tvd,) for east, north, tvd in points
            )

            step_out = hypot(heel_east - well.east_m, heel_north - well.north_m)
            build_tvd = max(landing_tvd - kick_off_tvd, 1.0)
            # 90 deg of inclination gained over the build section's course length
            course_length = hypot(step_out, build_tvd) * 1.15
            build_rate = 90.0 / max(course_length, 1.0) * 30.0

            measured_depth = kick_off_tvd + course_length + drain_m

            paths.append(
                WellPath(
                    well_tag=well.tag,
                    service=service,
                    drill_centre=well.parent,
                    points=tuple(points),
                    geographic=geographic,
                    kick_off_tvd_m=kick_off_tvd,
                    landing_tvd_m=landing_tvd,
                    reservoir_target_tvd_m=drain_tvd,
                    horizontal_step_out_m=step_out,
                    horizontal_section_m=drain_m,
                    measured_depth_m=measured_depth,
                    build_rate_deg_per_30m=build_rate,
                    drillable=build_rate <= MAX_SCREENING_DOGLEG_DEG_PER_30M,
                )
            )
    return paths


def trajectory_warnings(paths: Sequence[WellPath]) -> list[str]:
    """Screening flags a well engineer should see before the layout is carried forward."""
    warnings: list[str] = []
    undrillable = [path for path in paths if not path.drillable]
    if undrillable:
        worst = max(undrillable, key=lambda path: path.build_rate_deg_per_30m)
        warnings.append(
            "%d of %d wells need more than %.0f deg/30 m to land in the reservoir "
            "(worst %s at %.1f deg/30 m): move the drill centres further from the "
            "targets, kick off shallower, or accept a higher dogleg severity"
            % (
                len(undrillable),
                len(paths),
                MAX_SCREENING_DOGLEG_DEG_PER_30M,
                worst.well_tag,
                worst.build_rate_deg_per_30m,
            )
        )
    if paths:
        shallowest = min(path.landing_tvd_m - path.kick_off_tvd_m for path in paths)
        if shallowest < 150.0:
            warnings.append(
                "only %.0f m of true vertical depth is available between the kick-off "
                "point and the reservoir; a shallow reservoir under deep water is a "
                "drilling constraint, not a geometry detail" % shallowest
            )
    return warnings
