"""Screening design of a subsea (SURF) field layout and its host placement.

Given how many wells of each service are needed, the reservoir footprint and the
water depth, this module places drill centres, wells and Xmas trees, manifolds,
PLEMs, riser bases and the host, routes every flowline, riser and umbilical
between them, and sizes each line on velocity.

Everything is deterministic and geometric. There is no field-development
optimisation, no seabed obstacle avoidance, no on-bottom-stability or
free-span check and no mooring analysis; those belong to the validated NeqSim
mechanical-design workflows and to a qualified subsea engineering review.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil, cos, hypot, pi, radians, sin
from typing import Sequence

from .geo import LocalFrame, feature_collection, line_feature, point_feature, polygon_feature

#: Nominal line sizes commonly available for subsea flowlines and risers, inches.
NOMINAL_SIZES_INCH = (4.0, 6.0, 8.0, 10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 24.0, 28.0, 30.0)

#: Screening diameter-to-wall-thickness ratio for a subsea flowline.
DIAMETER_TO_WALL_RATIO = 20.0

#: API RP 14E erosional-velocity constant for continuous service.
EROSIONAL_C_FACTOR = 100.0

SERVICES = ("production", "water_injection", "gas_injection", "service", "umbilical")
ARCHITECTURES = ("dual_loop", "single_line", "daisy_chain")


def erosional_velocity_m_per_s(mixture_density_kg_m3: float, c_factor: float = EROSIONAL_C_FACTOR) -> float:
    """API RP 14E erosional velocity in SI units."""
    if mixture_density_kg_m3 <= 0.0:
        raise ValueError("mixture_density_kg_m3 must be positive")
    return 1.22 * c_factor / mixture_density_kg_m3**0.5


def inner_diameter_m(nominal_inch: float) -> float:
    """Screening inner diameter from a nominal size at a fixed D/t ratio."""
    outer_diameter_m = nominal_inch * 0.0254
    return outer_diameter_m * (1.0 - 2.0 / DIAMETER_TO_WALL_RATIO)


@dataclass(frozen=True)
class LineSize:
    """The selected size for one line and the checks behind it."""

    nominal_inch: float
    inner_diameter_m: float
    wall_thickness_mm: float
    velocity_m_per_s: float
    erosional_velocity_m_per_s: float
    erosional_ratio: float
    flow_m3_per_s: float
    verdict: str

    def to_dict(self) -> dict:
        return {
            "nominal_inch": self.nominal_inch,
            "inner_diameter_m": round(self.inner_diameter_m, 4),
            "wall_thickness_mm": round(self.wall_thickness_mm, 1),
            "velocity_m_per_s": round(self.velocity_m_per_s, 3),
            "erosional_velocity_m_per_s": round(self.erosional_velocity_m_per_s, 3),
            "erosional_ratio": round(self.erosional_ratio, 3),
            "flow_m3_per_s": round(self.flow_m3_per_s, 5),
            "verdict": self.verdict,
        }


def select_line_size(
    flow_m3_per_s: float,
    mixture_density_kg_m3: float,
    target_velocity_m_per_s: float = 3.0,
    c_factor: float = EROSIONAL_C_FACTOR,
) -> LineSize:
    """Smallest standard size that keeps the velocity under the target and the erosional limit."""
    if flow_m3_per_s <= 0.0:
        raise ValueError("flow_m3_per_s must be positive")
    erosional = erosional_velocity_m_per_s(mixture_density_kg_m3, c_factor)
    limit = min(target_velocity_m_per_s, erosional)

    chosen = NOMINAL_SIZES_INCH[-1]
    for nominal in NOMINAL_SIZES_INCH:
        area = pi / 4.0 * inner_diameter_m(nominal) ** 2
        if flow_m3_per_s / area <= limit:
            chosen = nominal
            break

    diameter = inner_diameter_m(chosen)
    velocity = flow_m3_per_s / (pi / 4.0 * diameter**2)
    ratio = velocity / erosional
    if velocity > erosional:
        verdict = "above the API RP 14E erosional velocity"
    elif velocity > target_velocity_m_per_s:
        verdict = "above the target velocity but below the erosional limit"
    else:
        verdict = "ok"
    return LineSize(
        nominal_inch=chosen,
        inner_diameter_m=diameter,
        wall_thickness_mm=chosen * 25.4 / DIAMETER_TO_WALL_RATIO,
        velocity_m_per_s=velocity,
        erosional_velocity_m_per_s=erosional,
        erosional_ratio=ratio,
        flow_m3_per_s=flow_m3_per_s,
        verdict=verdict,
    )


@dataclass(frozen=True)
class Node:
    """One located item of subsea hardware, or the host."""

    tag: str
    name: str
    kind: str
    east_m: float
    north_m: float
    latitude_deg: float
    longitude_deg: float
    water_depth_m: float
    parent: str = ""
    attributes: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "tag": self.tag,
            "name": self.name,
            "kind": self.kind,
            "east_m": round(self.east_m, 1),
            "north_m": round(self.north_m, 1),
            "latitude_deg": round(self.latitude_deg, 7),
            "longitude_deg": round(self.longitude_deg, 7),
            "water_depth_m": round(self.water_depth_m, 1),
            "parent": self.parent,
            **self.attributes,
        }


@dataclass(frozen=True)
class Line:
    """A flowline, riser or umbilical between two nodes."""

    tag: str
    service: str
    line_type: str
    from_tag: str
    to_tag: str
    length_m: float
    route: tuple[tuple[float, float], ...]
    size: LineSize | None
    attributes: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        payload = {
            "tag": self.tag,
            "service": self.service,
            "type": self.line_type,
            "from": self.from_tag,
            "to": self.to_tag,
            "length_m": round(self.length_m, 1),
            "length_km": round(self.length_m / 1000.0, 3),
            **self.attributes,
        }
        if self.size is not None:
            payload["size"] = self.size.to_dict()
        return payload


@dataclass
class SurfLayout:
    """A placed and routed subsea layout with its host."""

    field_name: str
    frame: LocalFrame
    nodes: list[Node]
    lines: list[Line]
    summary: dict
    warnings: list[str]
    assumptions: list[str]
    data_sources: list[str] = field(default_factory=list)

    def node(self, tag: str) -> Node:
        for item in self.nodes:
            if item.tag == tag:
                return item
        raise KeyError(tag)

    def nodes_of_kind(self, kind: str) -> list[Node]:
        return [item for item in self.nodes if item.kind == kind]

    def lines_of_service(self, service: str) -> list[Line]:
        return [item for item in self.lines if item.service == service]

    def total_line_length_km(self, service: str | None = None) -> float:
        selected = self.lines if service is None else self.lines_of_service(service)
        return round(sum(item.length_m for item in selected) / 1000.0, 3)

    def to_geojson(self) -> dict:
        features = [
            point_feature(
                item.latitude_deg,
                item.longitude_deg,
                {"tag": item.tag, "name": item.name, "kind": item.kind,
                 "water_depth_m": round(item.water_depth_m, 1), "parent": item.parent},
            )
            for item in self.nodes
        ]
        features.extend(
            line_feature(
                item.route,
                {
                    "tag": item.tag,
                    "service": item.service,
                    "type": item.line_type,
                    "length_km": round(item.length_m / 1000.0, 3),
                    "nominal_inch": item.size.nominal_inch if item.size else None,
                },
            )
            for item in self.lines
        )
        if "reservoir_outline" in self.summary:
            features.append(
                polygon_feature(
                    self.summary["reservoir_outline"],
                    {"name": "%s reservoir outline" % self.field_name, "kind": "reservoir_outline"},
                )
            )
        return feature_collection(features, name="%s SURF layout" % self.field_name)

    def to_dict(self) -> dict:
        return {
            "schemaVersion": "1.0",
            "field_name": self.field_name,
            "origin": {
                "latitude_deg": self.frame.origin_latitude_deg,
                "longitude_deg": self.frame.origin_longitude_deg,
            },
            "summary": self.summary,
            "nodes": [item.to_dict() for item in self.nodes],
            "lines": [item.to_dict() for item in self.lines],
            "warnings": list(self.warnings),
            "assumptions": list(self.assumptions),
            "data_sources": list(self.data_sources),
        }


def _place(along_m: float, across_m: float, axis_bearing_deg: float) -> tuple[float, float]:
    """Along-axis / across-axis offsets in metres -> local east, north."""
    angle = radians(axis_bearing_deg)
    east = along_m * sin(angle) + across_m * cos(angle)
    north = along_m * cos(angle) - across_m * sin(angle)
    return east, north


def _along_axis(east_m: float, north_m: float, axis_bearing_deg: float) -> float:
    """Projection of a local east/north position onto the field axis."""
    angle = radians(axis_bearing_deg)
    return east_m * sin(angle) + north_m * cos(angle)


def design_surf_layout(
    *,
    field_name: str,
    centre_latitude_deg: float,
    centre_longitude_deg: float,
    water_depth_m: float,
    producers: int,
    water_injectors: int = 0,
    gas_injectors: int = 0,
    slots_per_template: int = 4,
    slot_spacing_m: float = 12.0,
    reservoir_length_km: float = 6.0,
    reservoir_width_km: float = 3.0,
    field_axis_bearing_deg: float = 0.0,
    injector_offset_km: float = 1.2,
    host_type: str = "FPSO",
    host_offset_km: float = 2.5,
    host_bearing_deg: float = 270.0,
    riser_base_offset_m: float = 350.0,
    production_architecture: str = "dual_loop",
    design_liquid_rate_m3_per_s: float = 0.0,
    design_water_injection_rate_m3_per_s: float = 0.0,
    design_gas_injection_rate_am3_per_s: float = 0.0,
    liquid_density_kg_m3: float = 850.0,
    injection_water_density_kg_m3: float = 1025.0,
    injection_gas_density_kg_m3: float = 90.0,
    target_liquid_velocity_m_per_s: float = 3.0,
    target_gas_velocity_m_per_s: float = 12.0,
    seabed_slope_deg: float = 0.0,
    data_sources: Sequence[str] = (),
) -> SurfLayout:
    """Place and route a screening SURF layout around a host.

    Wells are grouped into drill centres of ``slots_per_template`` slots.
    Production drill centres sit on the field axis, water injectors are offset
    down one flank, gas injectors up the other. The host sits ``host_offset_km``
    from the field centre on ``host_bearing_deg``, with a riser-base PLEM
    ``riser_base_offset_m`` short of it.
    """
    if producers < 1:
        raise ValueError("at least one producer is required")
    if slots_per_template < 1:
        raise ValueError("slots_per_template must be at least 1")
    if production_architecture not in ARCHITECTURES:
        raise ValueError("production_architecture must be one of %s" % (ARCHITECTURES,))
    if water_depth_m <= 0.0:
        raise ValueError("water_depth_m must be positive")

    frame = LocalFrame(centre_latitude_deg, centre_longitude_deg)
    nodes: list[Node] = []
    lines: list[Line] = []
    warnings: list[str] = []

    def add_node(tag, name, kind, east, north, depth, parent="", **attributes) -> Node:
        latitude, longitude = frame.to_geographic(east, north)
        node = Node(tag, name, kind, east, north, latitude, longitude, depth, parent, attributes)
        nodes.append(node)
        return node

    def depth_at(east: float, north: float) -> float:
        """Water depth on a uniform seabed slope dipping along the field axis."""
        along = _along_axis(east, north, field_axis_bearing_deg)
        return water_depth_m - along * (seabed_slope_deg / 100.0)

    def place(along_m: float, across_m: float) -> tuple[float, float]:
        return _place(along_m, across_m, field_axis_bearing_deg)

    # --- drill centres -----------------------------------------------------
    groups = [
        ("production", "P", producers, 0.0),
        ("water_injection", "WI", water_injectors, -injector_offset_km * 1000.0),
        ("gas_injection", "GI", gas_injectors, +injector_offset_km * 1000.0),
    ]

    drill_centres: dict[str, list[Node]] = {service: [] for service, _, _, _ in groups}
    well_counter = 0
    for service, prefix, count, across in groups:
        if count <= 0:
            continue
        centre_count = ceil(count / slots_per_template)
        span = reservoir_length_km * 1000.0 * 0.7
        for index in range(centre_count):
            fraction = 0.5 if centre_count == 1 else index / (centre_count - 1)
            along = (fraction - 0.5) * span
            east, north = place(along, across)
            depth = depth_at(east, north)
            template_tag = "%s-DC%02d" % (prefix, index + 1)
            template = add_node(
                template_tag,
                "%s drill centre %d" % (service.replace("_", " "), index + 1),
                "template",
                east,
                north,
                depth,
                service=service,
                slots=slots_per_template,
                manifold="integrated %d-slot manifold" % slots_per_template,
            )
            drill_centres[service].append(template)

            add_node(
                "%s-PLEM" % template_tag,
                "%s flowline PLEM" % template_tag,
                "plem",
                east + slot_spacing_m * 2.0,
                north - slot_spacing_m * 2.0,
                depth,
                parent=template_tag,
                service=service,
            )

            remaining = count - index * slots_per_template
            for slot in range(min(slots_per_template, remaining)):
                well_counter += 1
                offset = (slot - (slots_per_template - 1) / 2.0) * slot_spacing_m
                slot_east, slot_north = east + offset, north
                well_tag = "%s-%02d" % (prefix, index * slots_per_template + slot + 1)
                add_node(
                    well_tag,
                    "%s well %s" % (service.replace("_", " "), well_tag),
                    "well",
                    slot_east,
                    slot_north,
                    depth_at(slot_east, slot_north),
                    parent=template_tag,
                    service=service,
                    slot=slot + 1,
                )
                add_node(
                    "%s-XT" % well_tag,
                    "Xmas tree %s" % well_tag,
                    "xmas_tree",
                    slot_east,
                    slot_north,
                    depth_at(slot_east, slot_north),
                    parent=well_tag,
                    service=service,
                    tree_type="horizontal subsea tree",
                )

    # --- host and riser base ----------------------------------------------
    host_east = host_offset_km * 1000.0 * sin(radians(host_bearing_deg))
    host_north = host_offset_km * 1000.0 * cos(radians(host_bearing_deg))
    host = add_node(
        "HOST",
        "%s %s" % (field_name, host_type),
        "host",
        host_east,
        host_north,
        depth_at(host_east, host_north),
        host_type=host_type,
        station_keeping="internal turret mooring, weathervaning" if host_type == "FPSO" else "fixed",
    )

    back_bearing = (host_bearing_deg + 180.0) % 360.0
    riser_east = host_east + riser_base_offset_m * sin(radians(back_bearing))
    riser_north = host_north + riser_base_offset_m * cos(radians(back_bearing))
    riser_base = add_node(
        "RB-PLEM",
        "riser base PLEM",
        "plem",
        riser_east,
        riser_north,
        depth_at(riser_east, riser_north),
        parent="HOST",
        function="riser base manifold, flowline and riser tie-in",
    )

    # --- lines -------------------------------------------------------------
    def route_length(a: Node, b: Node) -> float:
        return hypot(b.east_m - a.east_m, b.north_m - a.north_m)

    def add_line(tag, service, line_type, a: Node, b: Node, size: LineSize | None, **attributes):
        lines.append(
            Line(
                tag=tag,
                service=service,
                line_type=line_type,
                from_tag=a.tag,
                to_tag=b.tag,
                length_m=route_length(a, b),
                route=((a.latitude_deg, a.longitude_deg), (b.latitude_deg, b.longitude_deg)),
                size=size,
                attributes=attributes,
            )
        )

    production_centres = drill_centres["production"]
    if design_liquid_rate_m3_per_s > 0.0 and production_centres:
        parallel = 2 if production_architecture == "dual_loop" else len(production_centres)
        per_line = design_liquid_rate_m3_per_s / max(parallel, 1)
        production_size = select_line_size(
            per_line, liquid_density_kg_m3, target_liquid_velocity_m_per_s
        )
    else:
        production_size = None
        if design_liquid_rate_m3_per_s <= 0.0:
            warnings.append(
                "no design liquid rate was supplied, so the production flowlines are routed but not sized"
            )

    if production_architecture == "dual_loop":
        for leg, label in ((0, "A"), (1, "B")):
            previous = riser_base
            ordered = production_centres if leg == 0 else list(reversed(production_centres))
            for centre in ordered:
                plem = next(item for item in nodes if item.tag == "%s-PLEM" % centre.tag)
                add_line(
                    "FL-PROD-%s-%s" % (label, centre.tag),
                    "production",
                    "insulated rigid flowline",
                    previous,
                    plem,
                    production_size,
                    insulation="pipe-in-pipe or wet insulation, set by the cooldown requirement",
                    pigging="round-trip pigging loop %s" % label,
                )
                previous = plem
    elif production_architecture == "daisy_chain":
        previous = riser_base
        for centre in production_centres:
            plem = next(item for item in nodes if item.tag == "%s-PLEM" % centre.tag)
            add_line(
                "FL-PROD-%s" % centre.tag,
                "production",
                "insulated rigid flowline",
                previous,
                plem,
                production_size,
                pigging="not round-trip piggable without a dedicated return",
            )
            previous = plem
    else:
        for centre in production_centres:
            plem = next(item for item in nodes if item.tag == "%s-PLEM" % centre.tag)
            add_line(
                "FL-PROD-%s" % centre.tag,
                "production",
                "insulated rigid flowline",
                riser_base,
                plem,
                production_size,
                pigging="dedicated line per drill centre",
            )

    injection_specs = (
        ("water_injection", "FL-WI", design_water_injection_rate_m3_per_s,
         injection_water_density_kg_m3, target_liquid_velocity_m_per_s, "carbon steel injection flowline"),
        ("gas_injection", "FL-GI", design_gas_injection_rate_am3_per_s,
         injection_gas_density_kg_m3, target_gas_velocity_m_per_s, "carbon steel injection flowline"),
    )
    for service, prefix, rate, density, target, line_type in injection_specs:
        centres = drill_centres[service]
        if not centres:
            continue
        size = (
            select_line_size(rate / len(centres), density, target) if rate > 0.0 else None
        )
        if rate <= 0.0:
            warnings.append("no design rate supplied for %s, lines routed but not sized" % service)
        for centre in centres:
            plem = next(item for item in nodes if item.tag == "%s-PLEM" % centre.tag)
            add_line(
                "%s-%s" % (prefix, centre.tag),
                service,
                line_type,
                riser_base,
                plem,
                size,
                function="pressure support",
            )

    for service in ("production", "water_injection", "gas_injection"):
        for centre in drill_centres[service]:
            add_line(
                "UMB-%s" % centre.tag,
                "umbilical",
                "steel tube umbilical",
                host,
                centre,
                None,
                content="hydraulic supply, electrical power, fibre, chemical injection",
            )

    riser_services = [
        ("production", "PR", len([item for item in lines if item.service == "production"])),
        ("water_injection", "WIR", 1 if drill_centres["water_injection"] else 0),
        ("gas_injection", "GIR", 1 if drill_centres["gas_injection"] else 0),
    ]
    riser_length = (water_depth_m**2 + riser_base_offset_m**2) ** 0.5 * 1.25
    for service, prefix, count in riser_services:
        for index in range(count):
            lines.append(
                Line(
                    tag="%s-%02d" % (prefix, index + 1),
                    service=service,
                    line_type="flexible riser, lazy-wave configuration",
                    from_tag="RB-PLEM",
                    to_tag="HOST",
                    length_m=riser_length,
                    route=(
                        (riser_base.latitude_deg, riser_base.longitude_deg),
                        (host.latitude_deg, host.longitude_deg),
                    ),
                    size=production_size if service == "production" else None,
                    attributes={
                        "water_depth_m": round(water_depth_m, 1),
                        "note": "length includes a 25 % allowance for the lazy-wave shape",
                    },
                )
            )

    # --- outline, summary and caveats -------------------------------------
    outline = []
    for along_sign, across_sign in ((1, 1), (1, -1), (-1, -1), (-1, 1)):
        east, north = place(
            along_sign * reservoir_length_km * 500.0, across_sign * reservoir_width_km * 500.0
        )
        outline.append(frame.to_geographic(east, north))

    max_step_out_km = max(
        hypot(item.east_m - host.east_m, item.north_m - host.north_m) for item in nodes
    ) / 1000.0

    summary = {
        "host_type": host_type,
        "water_depth_m": water_depth_m,
        "reservoir_length_km": reservoir_length_km,
        "reservoir_width_km": reservoir_width_km,
        "field_axis_bearing_deg": field_axis_bearing_deg,
        "injector_offset_km": injector_offset_km,
        "wells": {
            "producers": producers,
            "water_injectors": water_injectors,
            "gas_injectors": gas_injectors,
            "total": producers + water_injectors + gas_injectors,
        },
        "xmas_trees": producers + water_injectors + gas_injectors,
        "drill_centres": {service: len(items) for service, items in drill_centres.items()},
        "templates": sum(len(items) for items in drill_centres.values()),
        "plems": len([item for item in nodes if item.kind == "plem"]),
        "production_architecture": production_architecture,
        "max_step_out_km": round(max_step_out_km, 3),
        "flowline_length_km": round(
            sum(
                item.length_m
                for item in lines
                if item.line_type.endswith("flowline")
            )
            / 1000.0,
            3,
        ),
        "umbilical_length_km": round(
            sum(item.length_m for item in lines if item.service == "umbilical") / 1000.0, 3
        ),
        "riser_length_km": round(
            sum(item.length_m for item in lines if "riser" in item.line_type) / 1000.0, 3
        ),
        "reservoir_outline": outline,
    }

    if production_size is not None and production_size.verdict != "ok":
        warnings.append("production flowline sizing: %s" % production_size.verdict)
    if seabed_slope_deg == 0.0:
        warnings.append(
            "a flat seabed was assumed; replace it with an open bathymetry grid before routing"
        )

    assumptions = [
        "Screening layout only: straight-line routes, no obstacle avoidance, no crossing design.",
        "Drill centres are spaced evenly over 70 % of the reservoir length on the field axis.",
        "Water injectors are offset down one flank and gas injectors up the other by the "
        "supplied offset; no sweep or voidage study lies behind that choice.",
        "Line sizes are the smallest standard size that meets the velocity target and the "
        "API RP 14E erosional limit at the supplied design rate and density.",
        "Wall thickness follows a fixed diameter-to-thickness ratio and is not a pressure design.",
        "Riser length is the straight riser-base-to-host distance with a lazy-wave allowance.",
        "No on-bottom stability, free-span, expansion, mooring or installation analysis.",
        "A qualified subsea engineering review is required before any decision.",
    ]

    return SurfLayout(
        field_name=field_name,
        frame=frame,
        nodes=nodes,
        lines=lines,
        summary=summary,
        warnings=warnings,
        assumptions=assumptions,
        data_sources=list(data_sources),
    )
