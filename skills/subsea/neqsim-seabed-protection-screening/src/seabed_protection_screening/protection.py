"""Trenching, burial and rock-dump screening for subsea pipelines.

The screener turns route segments (hazards and soil sampled from map layers or
supplied by the caller) into a protection strategy per segment - none, existing
cover adequate, trench, trench plus rock, or rock dump - with trench depth, rock
volume and tonnage, crossing and free-span support quantities, indicative
durations and a burial/thermal hand-off for flow-assurance models.

Every numeric default is a **screening placeholder** that is recorded in the
result ``assumptions`` list. Replace them with the project design basis, a trawl
interference assessment (for example DNV-RP-F111), a pipeline upheaval-buckling
assessment (DNV-RP-F110) and contractor capability data before quoting a result.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from .mapdata import LineCrossing, RouteSegment

SOIL_ALIASES: dict[str, str] = {
    "mud": "soft_clay",
    "mud_to_sandy_mud": "soft_clay",
    "soft_clay": "soft_clay",
    "firm_clay": "firm_clay",
    "stiff_clay": "stiff_clay",
    "very_stiff_clay": "very_stiff_clay",
    "clay": "firm_clay",
    "sand": "sand",
    "coarse_sediment": "gravel",
    "mixed_sediment": "gravel",
    "gravel": "gravel",
    "gravel_cobbles": "gravel",
    "boulders": "gravel",
    "rock": "rock",
    "hard": "rock",
    "hardpan": "rock",
    "rock_or_hard_substrate": "rock",
}
CLAY_CLASSES = ("soft_clay", "firm_clay", "stiff_clay", "very_stiff_clay")
#: Representative strengths used only when no measured value is supplied.
PLACEHOLDER_SU_KPA = {"soft_clay": 15.0, "firm_clay": 50.0, "stiff_clay": 100.0, "very_stiff_clay": 200.0}
FISHING_ORDER = ("none", "low", "medium", "high")
RECOGNISED_ATTRIBUTES = {
    "fishing_intensity",
    "soil_class",
    "undrained_shear_strength_kpa",
    "ice_scour_depth_m",
    "anchor_penetration_m",
    "dropped_object_cover_m",
    "stabilisation_cover_m",
    "uplift_force_n_per_m",
    "cover_required_m",
    "no_rock",
}


@dataclass(frozen=True)
class TrencherCapability:
    """Placeholder capability envelope of a trenching method."""

    max_su_kpa: float
    max_depth_m: float
    rate_m_per_day: float
    sand_ok: bool
    gravel_ok: bool


DEFAULT_TRENCHERS: dict[str, TrencherCapability] = {
    "jetting": TrencherCapability(40.0, 2.0, 3000.0, True, False),
    "plough": TrencherCapability(100.0, 1.5, 4000.0, True, False),
    "mechanical_cutter": TrencherCapability(300.0, 3.0, 1200.0, True, True),
}


@dataclass(frozen=True)
class PipeBasis:
    """The pipeline being protected."""

    outer_diameter_m: float
    name: str = "pipeline"


@dataclass(frozen=True)
class ScreeningAssumptions:
    """Screening placeholders. Every value used is echoed into the result."""

    cover_by_fishing_m: Mapping[str, float] = field(
        default_factory=lambda: {"none": 0.0, "low": 0.3, "medium": 0.6, "high": 1.0}
    )
    ice_scour_margin_m: float = 0.5
    trench_allowance_m: float = 0.1
    trench_bottom_clearance_m: float = 0.3
    trench_side_slope: float = 1.0
    rock_crest_width_m: float = 1.5
    rock_side_slope: float = 3.0
    rock_solid_density_kg_m3: float = 2650.0
    rock_porosity: float = 0.35
    rock_spillage_factor: float = 1.2
    seawater_density_kg_m3: float = 1025.0
    uplift_safety_factor: float = 1.5
    crossing_separation_m: float = 0.3
    crossing_length_m: float = 20.0
    crossed_outer_diameter_default_m: float = 0.3
    span_support_length_m: float = 5.0
    trenchers: Mapping[str, TrencherCapability] = field(default_factory=lambda: dict(DEFAULT_TRENCHERS))
    method_preference: Sequence[str] = ("jetting", "plough", "mechanical_cutter")
    rock_rate_tonnes_per_day: float | None = None
    soil_conductivity_w_mk: float = 1.5
    rock_conductivity_w_mk: float = 2.0

    @property
    def rock_bulk_density_kg_m3(self) -> float:
        """Placed bulk density of rock including voids."""
        return self.rock_solid_density_kg_m3 * (1.0 - self.rock_porosity)

    @property
    def rock_submerged_unit_weight_n_m3(self) -> float:
        """Submerged unit weight of placed rock in N/m3."""
        return (1.0 - self.rock_porosity) * (self.rock_solid_density_kg_m3 - self.seawater_density_kg_m3) * 9.81


@dataclass(frozen=True)
class SegmentProtection:
    """Protection result for one route segment."""

    start_kp_m: float
    end_kp_m: float
    length_m: float
    controlling_hazard: str
    required_cover_m: float
    rock_only_thickness_m: float
    existing_cover_m: float
    strategy: str
    trench_method: str | None
    trench_depth_m: float
    achieved_soil_cover_m: float
    rock_thickness_m: float
    rock_volume_m3: float
    rock_tonnes: float
    trench_days: float
    final_cover_m: float
    thermal_condition: str
    burial_depth_to_centre_m: float | None
    thermal_resistance_k_m_per_w: float | None
    notes: tuple[str, ...]


@dataclass(frozen=True)
class CrossingProtection:
    """Rock quantities for one crossing of an existing asset."""

    kp_m: float
    feature_id: str
    berm_height_m: float
    berm_length_m: float
    rock_volume_m3: float
    rock_tonnes: float


@dataclass(frozen=True)
class SpanSupportProtection:
    """Rock support quantities for one free-span candidate."""

    start_kp_m: float
    end_kp_m: float
    supports: int
    support_height_m: float
    rock_volume_m3: float
    rock_tonnes: float


@dataclass(frozen=True)
class ProtectionPlan:
    """Roll-up of the screening."""

    segments: tuple[SegmentProtection, ...]
    crossings: tuple[CrossingProtection, ...]
    span_supports: tuple[SpanSupportProtection, ...]
    route_length_m: float
    trench_length_m_by_method: dict[str, float]
    rock_dump_length_m: float
    rock_volume_m3: float
    rock_tonnes: float
    trench_days: float
    rock_days: float | None
    buried_length_fraction: float
    exposed_length_m: float
    assumptions: tuple[str, ...]
    data_gaps: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return the plan as a JSON-serialisable dictionary."""
        return asdict(self)


def required_uplift_rock_thickness_m(
    uplift_n_per_m: float, outer_diameter_m: float, assumptions: ScreeningAssumptions
) -> float:
    """Rock thickness above pipe top whose submerged weight resists an uplift force.

    The berm sits on the seabed with the given crest width and side slope, and the
    resisting weight is the rock above the pipe top. The factor of safety applies to
    the force. Solves ``n*H**2 + w*H = C`` for the berm height ``H`` above the seabed.

    Args:
        uplift_n_per_m: Characteristic uplift force per metre, in N/m.
        outer_diameter_m: Pipe outer diameter including coating, in m.
        assumptions: Screening assumptions supplying crest, slope and rock weight.

    Returns:
        Required rock thickness above the pipe top in metres.

    Raises:
        ValueError: If the uplift force is negative.
    """
    if uplift_n_per_m < 0.0:
        raise ValueError("uplift force must not be negative")
    if uplift_n_per_m == 0.0:
        return 0.0
    w, n, od = assumptions.rock_crest_width_m, assumptions.rock_side_slope, outer_diameter_m
    target = (w + n * od) * od + uplift_n_per_m * assumptions.uplift_safety_factor / assumptions.rock_submerged_unit_weight_n_m3
    height = (-w + math.sqrt(w * w + 4.0 * n * target)) / (2.0 * n)
    return max(0.0, height - od)


def rock_section_area_m2(
    outer_diameter_m: float,
    rock_above_pipe_m: float,
    trench_depth_m: float,
    fill_trench: bool,
    assumptions: ScreeningAssumptions,
) -> float:
    """Cross-sectional rock area per metre of pipe.

    A mound of crest width and side slope from the assumptions sits on the seabed.
    When the pipe is in a trench the mound only covers what the trench does not, and
    the trench void is filled with rock when ``fill_trench`` is true. The pipe cross
    section is deducted where the pipe sits inside the rock.

    Args:
        outer_diameter_m: Pipe outer diameter including coating, in m.
        rock_above_pipe_m: Rock thickness above the pipe top, in m.
        trench_depth_m: Depth from seabed to the pipe invert, in m (zero when surface laid).
        fill_trench: Whether rock replaces the natural trench backfill.
        assumptions: Screening assumptions.

    Returns:
        Rock area in m2 per metre of pipe.
    """
    od = outer_diameter_m
    top = od + rock_above_pipe_m
    mound_h = max(0.0, top - trench_depth_m)
    area = (assumptions.rock_crest_width_m + assumptions.rock_side_slope * mound_h) * mound_h
    pipe_in_rock = trench_depth_m <= 0.0
    if fill_trench and trench_depth_m > 0.0:
        bottom = od + 2.0 * assumptions.trench_bottom_clearance_m
        fill = min(trench_depth_m, top)
        area += (bottom + assumptions.trench_side_slope * fill) * fill
        pipe_in_rock = True
    if pipe_in_rock:
        area -= math.pi * od * od / 4.0
    return max(0.0, area)


def buried_thermal_resistance_k_m_per_w(cover_m: float, outer_diameter_m: float, conductivity_w_mk: float) -> float:
    """Shape-factor thermal resistance of a buried pipe, per metre.

    Matches ``PipeSurroundingEnvironment.calcBuriedPipeThermalResistance`` in NeqSim.

    Args:
        cover_m: Cover above the pipe top, in m (must be positive).
        outer_diameter_m: Pipe outer diameter including coating, in m.
        conductivity_w_mk: Thermal conductivity of the covering medium, in W/(m K).

    Returns:
        Thermal resistance in K m/W.

    Raises:
        ValueError: If the pipe is not buried or the conductivity is not positive.
    """
    radius = outer_diameter_m / 2.0
    depth = cover_m + radius
    if depth <= radius:
        raise ValueError("cover must be positive for a buried-pipe resistance")
    if conductivity_w_mk <= 0.0:
        raise ValueError("conductivity must be positive")
    ratio = depth / radius
    return math.log(2.0 * ratio + math.sqrt(4.0 * ratio * ratio - 1.0)) / (2.0 * math.pi * conductivity_w_mk)


def _get(obj: Any, name: str) -> Any:
    return obj[name] if isinstance(obj, Mapping) else getattr(obj, name)


class SeabedProtectionScreener:
    """Screens trenching, burial and rock-dump scope along a route."""

    def __init__(self, pipe: PipeBasis, assumptions: ScreeningAssumptions | None = None) -> None:
        if pipe.outer_diameter_m <= 0.0:
            raise ValueError("outer_diameter_m must be positive")
        self.pipe = pipe
        self.assumptions = assumptions or ScreeningAssumptions()

    def assess(
        self,
        segments: Sequence[RouteSegment],
        crossings: Sequence[LineCrossing] = (),
        span_candidates: Sequence[Any] = (),
        allowable_span_m: float | None = None,
        existing_cover_intervals: Sequence[Any] | None = None,
    ) -> ProtectionPlan:
        """Assess protection for every segment, crossing and free-span candidate.

        Args:
            segments: Route segments with hazard and soil attributes.
            crossings: Crossings of existing assets from ``find_line_crossings``.
            span_candidates: Free-span candidates (objects or mappings with
                ``start_kp_m``, ``end_kp_m``, ``length_m`` and ``max_gap_m``).
            allowable_span_m: Allowable free-span length from a DNV-RP-F105 assessment.
            existing_cover_intervals: Surveyed burial intervals (objects or mappings with
                ``start_kp_m``, ``end_kp_m`` and ``min_cover_m``).

        Returns:
            The protection plan, including assumptions, data gaps and warnings.

        Raises:
            ValueError: If no segments are supplied.
        """
        if not segments:
            raise ValueError("at least one route segment is required")
        a = self.assumptions
        used: dict[str, str] = {}
        gaps: list[str] = []
        warnings: list[str] = []
        if existing_cover_intervals is None:
            gaps.append("No surveyed cover supplied; existing cover is assumed to be zero everywhere.")
        if a.rock_rate_tonnes_per_day is None:
            gaps.append("No rock placement rate supplied; rock vessel days are not estimated.")
        seen_unknown: set[str] = set()
        results = [
            self._segment(seg, existing_cover_intervals, used, gaps, warnings, seen_unknown) for seg in segments
        ]
        crossing_results = tuple(self._crossing(c, used, gaps) for c in crossings)
        span_results = self._spans(span_candidates, allowable_span_m, gaps)
        return self._plan(results, crossing_results, span_results, used, gaps, warnings)

    def _segment(self, seg, intervals, used, gaps, warnings, seen_unknown) -> SegmentProtection:
        a, od = self.assumptions, self.pipe.outer_diameter_m
        attrs = dict(seg.attributes)
        for name in attrs:
            if name not in RECOGNISED_ATTRIBUTES and name not in seen_unknown:
                seen_unknown.add(name)
                warnings.append("Attribute %r is not used by the screener." % name)
        contributions: dict[str, float] = {}
        intensity = str(attrs.get("fishing_intensity") or "none").lower()
        if intensity not in a.cover_by_fishing_m:
            gaps.append("Fishing intensity %r has no cover rule; treated as none." % intensity)
            intensity = "none"
        if a.cover_by_fishing_m[intensity] > 0.0:
            contributions["trawl (%s fishing intensity)" % intensity] = a.cover_by_fishing_m[intensity]
            used["cover_by_fishing_m"] = "placeholder cover per fishing intensity: %s" % dict(a.cover_by_fishing_m)
        scour = float(attrs.get("ice_scour_depth_m") or 0.0)
        if scour > 0.0:
            contributions["ice scour"] = scour + a.ice_scour_margin_m
            used["ice_scour_margin_m"] = "ice-scour margin %.2f m on top of scour depth" % a.ice_scour_margin_m
        for key, label in (("anchor_penetration_m", "anchor"), ("cover_required_m", "project cover requirement")):
            if attrs.get(key):
                contributions[label] = float(attrs[key])
        required, hazard = (max((v, k) for k, v in contributions.items()) if contributions else (0.0, "none"))

        rock_only: dict[str, float] = {}
        if attrs.get("dropped_object_cover_m"):
            rock_only["dropped objects"] = float(attrs["dropped_object_cover_m"])
        if attrs.get("stabilisation_cover_m"):
            rock_only["on-bottom stabilisation"] = float(attrs["stabilisation_cover_m"])
        if attrs.get("uplift_force_n_per_m"):
            rock_only["upheaval buckling"] = required_uplift_rock_thickness_m(float(attrs["uplift_force_n_per_m"]), od, a)
            used["uplift_safety_factor"] = "uplift factor of safety %.2f on the supplied force" % a.uplift_safety_factor
        rock_only_t, rock_hazard = (max((v, k) for k, v in rock_only.items()) if rock_only else (0.0, "none"))
        if rock_only_t > required:
            hazard = rock_hazard

        existing = self._existing_cover(seg, intervals)
        notes: list[str] = []
        method: str | None = None
        trench_d, rock_t, fill = 0.0, 0.0, False
        achieved = existing
        strategy = "none"
        if rock_only_t > 0.0:
            rock_t = max(rock_only_t, required)
            if existing > 0.0:
                trench_d = od + existing
            else:
                fill = True
            strategy = "rock_dump"
            if required > 0.0:
                notes.append("rock-only requirement governs; burial need is met by the rock cover")
        elif required > 0.0:
            if existing >= required:
                strategy, achieved = "adequate_existing_cover", existing
                notes.append("surveyed cover meets the requirement; verify at the next survey")
            else:
                strategy, method, trench_d, rock_t, fill, achieved = self._burial(
                    seg, attrs, required, existing, used, gaps, notes
                )
        if strategy == "rock_dump" and 0.0 < rock_t <= existing:
            strategy, rock_t, trench_d, fill, achieved = "adequate_existing_cover", 0.0, 0.0, False, existing
            notes.append("surveyed cover already exceeds the rock cover requirement")
        if rock_t > 0.0 and attrs.get("no_rock"):
            warnings.append(
                "KP %.0f-%.0f needs rock but the segment is flagged no_rock; choose another route or method."
                % (seg.start_kp_m, seg.end_kp_m)
            )
            notes.append("rock placement restricted by map layer")

        volume = tonnes = 0.0
        if rock_t > 0.0:
            area = rock_section_area_m2(od, rock_t, trench_d, fill, a)
            volume = area * seg.length_m
            tonnes = volume * a.rock_bulk_density_kg_m3 * a.rock_spillage_factor / 1000.0
            used["rock"] = (
                "rock crest %.2f m, slope 1:%.1f, solid %.0f kg/m3, porosity %.2f, spillage x%.2f"
                % (a.rock_crest_width_m, a.rock_side_slope, a.rock_solid_density_kg_m3, a.rock_porosity, a.rock_spillage_factor)
            )
        days = seg.length_m / a.trenchers[method].rate_m_per_day if method else 0.0
        if method and strategy in ("trench", "trench_and_rock"):
            used["trenchers"] = "placeholder trencher capability and rates: %s" % {
                k: asdict(v) for k, v in a.trenchers.items()
            }
        final_cover = rock_t if rock_t > 0.0 else (achieved if strategy != "none" else existing)
        condition, depth, resistance = self._thermal(final_cover, rock_t > 0.0)
        return SegmentProtection(
            start_kp_m=seg.start_kp_m,
            end_kp_m=seg.end_kp_m,
            length_m=seg.length_m,
            controlling_hazard=hazard,
            required_cover_m=required,
            rock_only_thickness_m=rock_only_t,
            existing_cover_m=existing,
            strategy=strategy,
            trench_method=method,
            trench_depth_m=trench_d if method else 0.0,
            achieved_soil_cover_m=max(0.0, achieved),
            rock_thickness_m=rock_t,
            rock_volume_m3=volume,
            rock_tonnes=tonnes,
            trench_days=days,
            final_cover_m=max(0.0, final_cover),
            thermal_condition=condition,
            burial_depth_to_centre_m=depth,
            thermal_resistance_k_m_per_w=resistance,
            notes=tuple(notes),
        )

    def _burial(self, seg, attrs, required, existing, used, gaps, notes):
        a, od = self.assumptions, self.pipe.outer_diameter_m
        soil = SOIL_ALIASES.get(str(attrs.get("soil_class") or "").lower())
        su = attrs.get("undrained_shear_strength_kpa")
        if soil is None:
            gaps.append("KP %.0f-%.0f has no recognised soil class; trenching is not assumed." % (seg.start_kp_m, seg.end_kp_m))
            notes.append("soil unknown - rock dump assumed")
        elif soil in CLAY_CLASSES and su is None:
            su = PLACEHOLDER_SU_KPA[soil]
            used["undrained_shear_strength_kpa"] = "placeholder strengths used where none measured: %s" % PLACEHOLDER_SU_KPA
            gaps.append(
                "KP %.0f-%.0f uses a placeholder undrained shear strength for %s; supply geotechnical data."
                % (seg.start_kp_m, seg.end_kp_m, soil)
            )
        d_req = od + required + a.trench_allowance_m
        method, d_max = self._select_trencher(soil, su, d_req)
        cover_n = max(0.0, d_max - od)
        if method is None or (d_max < d_req and existing >= cover_n):
            notes.append("not trenchable with the listed methods" if method is None else "trenching adds no cover")
            if existing > 0.0:
                return "rock_dump", None, od + existing, required, False, existing
            return "rock_dump", None, 0.0, required, True, 0.0
        if d_max >= d_req:
            return "trench", method, d_req, 0.0, False, d_req - od
        notes.append("achievable trench depth %.2f m is below the %.2f m needed; rock tops up" % (d_max, d_req))
        return "trench_and_rock", method, d_max, required, d_max < od, cover_n

    def _select_trencher(self, soil, su, d_req):
        a = self.assumptions
        feasible = []
        for name in a.method_preference:
            cap = a.trenchers[name]
            if soil is None or soil == "rock":
                break
            if soil in CLAY_CLASSES and su is not None and su > cap.max_su_kpa:
                continue
            if soil == "sand" and not cap.sand_ok:
                continue
            if soil == "gravel" and not cap.gravel_ok:
                continue
            feasible.append((name, cap.max_depth_m))
        for name, depth in feasible:
            if depth >= d_req:
                return name, depth
        if feasible:
            return max(feasible, key=lambda item: item[1])
        return None, 0.0

    @staticmethod
    def _existing_cover(seg, intervals) -> float:
        if not intervals:
            return 0.0
        spans = sorted(
            (float(_get(i, "start_kp_m")), float(_get(i, "end_kp_m")), float(_get(i, "min_cover_m")))
            for i in intervals
            if float(_get(i, "end_kp_m")) > seg.start_kp_m and float(_get(i, "start_kp_m")) < seg.end_kp_m
        )
        reach, cover = seg.start_kp_m, None
        for start, end, minimum in spans:
            if start > reach + 1e-6:
                return 0.0
            reach = max(reach, end)
            cover = minimum if cover is None else min(cover, minimum)
        return max(0.0, cover) if cover is not None and reach >= seg.end_kp_m - 1e-6 else 0.0

    def _thermal(self, cover, rock):
        a, od = self.assumptions, self.pipe.outer_diameter_m
        if cover <= 0.0:
            return "exposed", None, None
        k = a.rock_conductivity_w_mk if rock else a.soil_conductivity_w_mk
        return (
            "rock_covered" if rock else "buried",
            cover + od / 2.0,
            buried_thermal_resistance_k_m_per_w(cover, od, k),
        )

    def _crossing(self, crossing, used, gaps) -> CrossingProtection:
        a, od = self.assumptions, self.pipe.outer_diameter_m
        crossed = crossing.crossed_outer_diameter_m
        if crossed is None:
            crossed = a.crossed_outer_diameter_default_m
            gaps.append("Crossed outer diameter missing at %s (KP %.0f); %.2f m assumed." % (crossing.feature_id, crossing.kp_m, crossed))
        height = crossed + a.crossing_separation_m + od
        length = a.crossing_length_m + a.rock_side_slope * height
        area = (a.rock_crest_width_m + a.rock_side_slope * height) * height - math.pi * od * od / 4.0
        volume = area * length
        used["crossing"] = "crossing separation %.2f m, berm length %.0f m plus slopes" % (a.crossing_separation_m, a.crossing_length_m)
        return CrossingProtection(
            crossing.kp_m, crossing.feature_id, height, length, volume,
            volume * a.rock_bulk_density_kg_m3 * a.rock_spillage_factor / 1000.0,
        )

    def _spans(self, candidates, allowable, gaps) -> tuple[SpanSupportProtection, ...]:
        if not candidates:
            return ()
        if allowable is None or allowable <= 0.0:
            gaps.append("Free-span candidates were supplied without an allowable span; no supports sized.")
            return ()
        a, od = self.assumptions, self.pipe.outer_diameter_m
        out = []
        for cand in candidates:
            length = float(_get(cand, "length_m"))
            if length <= allowable:
                continue
            supports = int(math.ceil(length / allowable)) - 1
            height = float(_get(cand, "max_gap_m"))
            base_h = max(height, 0.0) + od / 2.0
            area = (a.rock_crest_width_m + a.rock_side_slope * base_h) * base_h
            volume = supports * area * a.span_support_length_m
            out.append(
                SpanSupportProtection(
                    float(_get(cand, "start_kp_m")), float(_get(cand, "end_kp_m")), supports, base_h, volume,
                    volume * a.rock_bulk_density_kg_m3 * a.rock_spillage_factor / 1000.0,
                )
            )
        return tuple(out)

    def _plan(self, segs, crossings, spans, used, gaps, warnings) -> ProtectionPlan:
        a = self.assumptions
        length = sum(s.length_m for s in segs)
        by_method: dict[str, float] = {}
        for s in segs:
            if s.trench_method and s.strategy in ("trench", "trench_and_rock"):
                by_method[s.trench_method] = by_method.get(s.trench_method, 0.0) + s.length_m
        volume = sum(s.rock_volume_m3 for s in segs) + sum(c.rock_volume_m3 for c in crossings) + sum(p.rock_volume_m3 for p in spans)
        tonnes = sum(s.rock_tonnes for s in segs) + sum(c.rock_tonnes for c in crossings) + sum(p.rock_tonnes for p in spans)
        buried = sum(s.length_m for s in segs if s.thermal_condition != "exposed")
        rock_days = tonnes / a.rock_rate_tonnes_per_day if a.rock_rate_tonnes_per_day else None
        warnings.append("Quantities exclude mobilisation, weather downtime, pre-lay clearance and post-works survey.")
        return ProtectionPlan(
            segments=tuple(segs),
            crossings=crossings,
            span_supports=spans,
            route_length_m=length,
            trench_length_m_by_method=by_method,
            rock_dump_length_m=sum(s.length_m for s in segs if s.rock_thickness_m > 0.0),
            rock_volume_m3=volume,
            rock_tonnes=tonnes,
            trench_days=sum(s.trench_days for s in segs),
            rock_days=rock_days,
            buried_length_fraction=buried / length if length else 0.0,
            exposed_length_m=length - buried,
            assumptions=tuple("%s: %s" % item for item in sorted(used.items())),
            data_gaps=tuple(dict.fromkeys(gaps)),
            warnings=tuple(dict.fromkeys(warnings)),
        )


def to_neqsim_burial_segments(plan: ProtectionPlan, outer_diameter_m: float, assumptions: ScreeningAssumptions | None = None) -> list[dict[str, Any]]:
    """Hand the post-protection burial state to a NeqSim thermal or cooldown model.

    Each entry is one pipe section. ``buried`` and ``burial_depth_m`` map to
    ``PipeLineInterface.setBuried`` and ``setBurialDepth`` (depth to pipe centre), and
    ``soil_conductivity_w_mk`` to ``setSoilConductivity``. Exposed sections should use
    the seawater film coefficient instead. Adjacent sections in the same state are merged.

    Args:
        plan: Result from :meth:`SeabedProtectionScreener.assess`.
        outer_diameter_m: Pipe outer diameter including coating, in m.
        assumptions: Assumptions used for the screening, for the conductivities.

    Returns:
        A list of dictionaries ordered by KP.
    """
    a = assumptions or ScreeningAssumptions()
    out: list[dict[str, Any]] = []
    for seg in plan.segments:
        buried = seg.thermal_condition != "exposed"
        depth = None if not buried else round(seg.final_cover_m + outer_diameter_m / 2.0, 4)
        conductivity = None if not buried else (a.rock_conductivity_w_mk if seg.thermal_condition == "rock_covered" else a.soil_conductivity_w_mk)
        entry = {
            "start_kp_m": seg.start_kp_m,
            "end_kp_m": seg.end_kp_m,
            "buried": buried,
            "burial_depth_m": depth,
            "soil_conductivity_w_mk": conductivity,
            "condition": seg.thermal_condition,
        }
        prev = out[-1] if out else None
        if prev and all(prev[k] == entry[k] for k in ("buried", "burial_depth_m", "soil_conductivity_w_mk", "condition")):
            prev["end_kp_m"] = entry["end_kp_m"]
        else:
            out.append(entry)
    return out
