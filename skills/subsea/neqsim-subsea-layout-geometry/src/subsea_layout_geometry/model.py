from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import asin, cos, isfinite, radians, sin, sqrt

EARTH_RADIUS_M = 6_371_000.0
_VALID_KINDS = ("well", "manifold", "host", "riser_base", "template", "tie_in")
_VALID_SYSTEMS = ("cartesian", "geographic")


@dataclass(frozen=True)
class LayoutNode:
    name: str
    x: float
    y: float
    water_depth_m: float
    kind: str


@dataclass(frozen=True)
class NodeDistance:
    from_name: str
    to_name: str
    horizontal_km: float
    straight_line_km: float
    depth_difference_m: float


@dataclass(frozen=True)
class SubseaLayoutResult:
    node_count: int
    host_name: str
    coordinate_system: str
    step_out_km: dict[str, float]
    straight_line_km: dict[str, float]
    pairwise_distances: tuple[NodeDistance, ...]
    max_step_out_km: float
    step_out_warning: str
    neqsim_available: bool
    assumptions: tuple[str, ...]


class SubseaLayoutModel:
    """Educational subsea field-layout geometry screening placeholder."""

    def __init__(self, max_step_out_km: float = 50.0) -> None:
        self._require_positive("max_step_out_km", max_step_out_km)
        self.max_step_out_km = max_step_out_km

    def evaluate(
        self,
        *,
        nodes,
        host_name: str,
        coordinate_system: str = "cartesian",
    ) -> SubseaLayoutResult:
        system = self._normalize_system(coordinate_system)
        layout = self._normalize_nodes(nodes)

        if len(layout) < 2:
            raise ValueError("at least two nodes are required")

        names = [node.name for node in layout]
        if len(set(names)) != len(names):
            raise ValueError("node names must be unique")
        if host_name not in names:
            raise ValueError(f"host_name {host_name!r} not found in nodes")

        host = next(node for node in layout if node.name == host_name)

        pairwise: list[NodeDistance] = []
        for index_a in range(len(layout)):
            for index_b in range(index_a + 1, len(layout)):
                node_a = layout[index_a]
                node_b = layout[index_b]
                horizontal_m = self._horizontal_distance_m(node_a, node_b, system)
                depth_difference = node_b.water_depth_m - node_a.water_depth_m
                straight_m = sqrt(horizontal_m**2 + depth_difference**2)
                pairwise.append(
                    NodeDistance(
                        from_name=node_a.name,
                        to_name=node_b.name,
                        horizontal_km=round(horizontal_m / 1000.0, 4),
                        straight_line_km=round(straight_m / 1000.0, 4),
                        depth_difference_m=round(depth_difference, 2),
                    )
                )

        step_out_km: dict[str, float] = {}
        straight_line_km: dict[str, float] = {}
        for node in layout:
            if node.name == host_name:
                continue
            horizontal_m = self._horizontal_distance_m(host, node, system)
            depth_difference = node.water_depth_m - host.water_depth_m
            straight_m = sqrt(horizontal_m**2 + depth_difference**2)
            step_out_km[node.name] = round(horizontal_m / 1000.0, 4)
            straight_line_km[node.name] = round(straight_m / 1000.0, 4)

        max_step_out = max(step_out_km.values()) if step_out_km else 0.0

        return SubseaLayoutResult(
            node_count=len(layout),
            host_name=host_name,
            coordinate_system=system,
            step_out_km=step_out_km,
            straight_line_km=straight_line_km,
            pairwise_distances=tuple(pairwise),
            max_step_out_km=round(max_step_out, 4),
            step_out_warning=self._step_out_warning(max_step_out),
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational geometry screening placeholder only.",
                "Horizontal distance is planar Euclidean (cartesian) or great-circle haversine (geographic).",
                "Straight-line tie-back length uses the water-depth difference, not a bathymetric profile.",
                "Straight-line lengths are a lower bound on routed flowline length.",
                "The step-out guideline is a configurable public guideline, not a feasibility limit.",
                "Move to validated NeqSim routing and hydraulic workflows and qualified subsea review.",
            ),
        )

    def _step_out_warning(self, max_step_out_km: float) -> str:
        if max_step_out_km >= self.max_step_out_km:
            return "high"
        if max_step_out_km >= 0.8 * self.max_step_out_km:
            return "watch"
        return "ok"

    def _horizontal_distance_m(
        self, node_a: LayoutNode, node_b: LayoutNode, system: str
    ) -> float:
        if system == "geographic":
            return self._haversine_m(node_a.x, node_a.y, node_b.x, node_b.y)
        delta_x = node_b.x - node_a.x
        delta_y = node_b.y - node_a.y
        return sqrt(delta_x**2 + delta_y**2)

    def _normalize_nodes(self, nodes) -> list[LayoutNode]:
        if nodes is None:
            raise ValueError("nodes must be provided")
        normalized: list[LayoutNode] = []
        for raw in nodes:
            name = str(raw["name"]).strip()
            if not name:
                raise ValueError("each node must have a non-empty name")
            x = float(raw["x"])
            y = float(raw["y"])
            water_depth = float(raw.get("water_depth_m", 0.0))
            kind = str(raw.get("kind", "well")).strip().lower()
            self._require_finite(f"{name}.x", x)
            self._require_finite(f"{name}.y", y)
            self._require_finite(f"{name}.water_depth_m", water_depth)
            if water_depth < 0.0:
                raise ValueError(f"{name}.water_depth_m must be non-negative")
            if kind not in _VALID_KINDS:
                kind = "well"
            normalized.append(
                LayoutNode(
                    name=name,
                    x=x,
                    y=y,
                    water_depth_m=water_depth,
                    kind=kind,
                )
            )
        return normalized

    @staticmethod
    def _normalize_system(coordinate_system: str) -> str:
        system = str(coordinate_system).strip().lower()
        if system not in _VALID_SYSTEMS:
            raise ValueError(
                f"coordinate_system must be one of {_VALID_SYSTEMS}, got {coordinate_system!r}"
            )
        return system

    @staticmethod
    def _haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
        phi1 = radians(lat1)
        phi2 = radians(lat2)
        delta_phi = radians(lat2 - lat1)
        delta_lambda = radians(lon2 - lon1)
        haversine = (
            sin(delta_phi / 2.0) ** 2
            + cos(phi1) * cos(phi2) * sin(delta_lambda / 2.0) ** 2
        )
        return 2.0 * EARTH_RADIUS_M * asin(sqrt(haversine))

    @staticmethod
    def _require_finite(name: str, value: float) -> None:
        if not isfinite(value):
            raise ValueError(f"{name} must be finite")

    @classmethod
    def _require_positive(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value <= 0.0:
            raise ValueError(f"{name} must be positive")
