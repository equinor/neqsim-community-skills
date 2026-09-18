from __future__ import annotations

from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite

KNOWN_KINDS = ("well", "manifold", "host", "riser_base", "template", "tie_in")


@dataclass(frozen=True)
class ImportedNode:
    name: str
    x: float
    y: float
    water_depth_m: float
    kind: str


@dataclass(frozen=True)
class LayoutImportResult:
    node_count: int
    nodes: tuple[ImportedNode, ...]
    issues: tuple[str, ...]
    neqsim_available: bool
    assumptions: tuple[str, ...]


class FieldLayoutImporter:
    """Educational subsea field-layout import and normalization placeholder."""

    def from_geojson(self, obj) -> LayoutImportResult:
        if not isinstance(obj, dict):
            raise ValueError("geojson must be an already-parsed dict")
        features = obj.get("features")
        if not isinstance(features, list):
            raise ValueError("geojson must contain a 'features' list")

        nodes: list[ImportedNode] = []
        issues: list[str] = []
        for index, feature in enumerate(features):
            node = self._node_from_feature(index, feature, issues)
            if node is not None:
                nodes.append(node)
        return self._finalize(nodes, issues)

    def from_rows(self, rows) -> LayoutImportResult:
        if not isinstance(rows, list):
            raise ValueError("rows must be a list of dicts")

        nodes: list[ImportedNode] = []
        issues: list[str] = []
        for index, row in enumerate(rows):
            node = self._node_from_row(index, row, issues)
            if node is not None:
                nodes.append(node)
        return self._finalize(nodes, issues)

    def _node_from_feature(self, index, feature, issues) -> ImportedNode | None:
        try:
            geometry = feature["geometry"]
            if geometry.get("type") != "Point":
                issues.append(f"feature {index} skipped: geometry is not a Point")
                return None
            coordinates = geometry["coordinates"]
            x = float(coordinates[0])
            y = float(coordinates[1])
            properties = feature.get("properties") or {}
        except (KeyError, TypeError, IndexError, ValueError):
            issues.append(f"feature {index} skipped: could not parse geometry")
            return None
        return self._build_node(index, properties, x, y, issues)

    def _node_from_row(self, index, row, issues) -> ImportedNode | None:
        if not isinstance(row, dict):
            issues.append(f"row {index} skipped: not a dict")
            return None
        x_raw = row.get("x", row.get("longitude"))
        y_raw = row.get("y", row.get("latitude"))
        try:
            x = float(x_raw)
            y = float(y_raw)
        except (TypeError, ValueError):
            issues.append(f"row {index} skipped: missing or invalid coordinates")
            return None
        return self._build_node(index, row, x, y, issues)

    def _build_node(self, index, properties, x, y, issues) -> ImportedNode | None:
        name = str(properties.get("name", "")).strip()
        if not name:
            issues.append(f"record {index} skipped: missing name")
            return None
        if not (isfinite(x) and isfinite(y)):
            issues.append(f"record {index} ({name}) skipped: non-finite coordinates")
            return None

        depth_raw = properties.get("water_depth_m")
        if depth_raw is None:
            water_depth_m = 0.0
            issues.append(f"record {name}: missing water_depth_m defaulted to 0.0")
        else:
            try:
                water_depth_m = float(depth_raw)
            except (TypeError, ValueError):
                water_depth_m = 0.0
                issues.append(f"record {name}: invalid water_depth_m defaulted to 0.0")
            else:
                if water_depth_m < 0.0:
                    water_depth_m = 0.0
                    issues.append(f"record {name}: negative water_depth_m clamped to 0.0")

        kind = str(properties.get("kind", "well")).strip().lower()
        if kind not in KNOWN_KINDS:
            issues.append(f"record {name}: unknown kind '{kind}' normalized to 'well'")
            kind = "well"

        return ImportedNode(
            name=name,
            x=round(x, 6),
            y=round(y, 6),
            water_depth_m=round(water_depth_m, 3),
            kind=kind,
        )

    def _finalize(self, nodes, issues) -> LayoutImportResult:
        seen: set[str] = set()
        for node in nodes:
            if node.name in seen:
                issues.append(f"duplicate node name '{node.name}'")
            seen.add(node.name)

        return LayoutImportResult(
            node_count=len(nodes),
            nodes=tuple(nodes),
            issues=tuple(issues),
            neqsim_available=find_spec("neqsim") is not None,
            assumptions=(
                "Educational layout import placeholder only.",
                "No file reading, URL fetching, or coordinate transformation is performed.",
                "GeoJSON support is limited to Point features.",
                "Missing water depths are defaulted to 0.0 and flagged as issues.",
                "Unknown kinds are normalized to 'well' and flagged as issues.",
                "Feed the normalized nodes into validated geometry and NeqSim hydraulic workflows.",
            ),
        )
