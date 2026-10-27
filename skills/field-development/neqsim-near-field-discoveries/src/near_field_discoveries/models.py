"""Common record for a discovery, field or evaluation area, and the stage ladder.

The same ``Discovery`` record is produced from Sodir (Norway) and ANP (Brazil)
so that the inventory, tables and map code do not depend on the country.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

STAGES = (
    "producing",
    "in_development",
    "in_clarification",
    "not_evaluated",
    "unlikely",
    "unknown",
)
"""Normalised development stage, most mature first."""

STAGE_LABELS = {
    "producing": "Producing field",
    "in_development": "Approved / in development",
    "in_clarification": "Planned or in evaluation",
    "not_evaluated": "No public plan",
    "unlikely": "Development unlikely / relinquished",
    "unknown": "Unknown",
}

STAGE_COLOURS = {
    "producing": "#1b7837",
    "in_development": "#7fbf7b",
    "in_clarification": "#f1a340",
    "not_evaluated": "#998ec3",
    "unlikely": "#8c8c8c",
    "unknown": "#d9d9d9",
}

POSITION_BASES = (
    "polygon-centroid",
    "wellhead",
    "approximate-derived-from-ANP-wells",
    "facility-point",
    "user-supplied",
)


@dataclass
class Discovery:
    """One discovery, field or evaluation area with its provenance and gaps.

    Attributes:
        country: ``"NO"`` or ``"BR"``.
        id: Stable identifier within the country (Sodir NPDID or an ANP-derived key).
        name: Public name; for Brazil often the discovery well, because ANP publishes no discovery names.
        kind: ``"discovery"``, ``"field"``, ``"evaluation_area"`` or ``"prospect"`` (a user-supplied or enterprise
            record such as a GeoX prospect; it carries its own volumes and chance, and is listed apart from discoveries).
        stage: One of :data:`STAGES`.
        status_raw: The source status text, unmodified.
        hc_type: Hydrocarbon type as published (``OIL``, ``GAS``, ``OIL/GAS``, ``oil``, ``gas`` ...).
        discovery_year: Year of the discovery well, when known.
        operator: Operator as published, when known.
        lat: Latitude (WGS84/SIRGAS 2000, degrees).
        lon: Longitude (degrees).
        position_basis: How the position was derived (see :data:`POSITION_BASES`).
        rings: Outline rings as (lon, lat) lists; empty when only a point is known.
        volumes: Public volumes with units and basis; empty when not published.
        plan_note: Source text about the plan (Sodir description excerpt, ANP evaluation-plan summary).
        plan_flags: Machine-readable hints extracted from the plan text (unverified).
        linked: Related objects: field, evaluation plan, block, basin, resource class.
        water_depth_m: Water depth in metres, when published.
        n_wells: Number of wells behind the record (Brazil clusters).
        source: Source system and layer.
        source_url: Public page for the record, when one exists.
        gaps: What is not public or could not be established for this record.
        distance_km: Distance from the study target (set by the inventory).
        bearing: 16-point compass bearing from the target (set by the inventory).
        nearest_hosts: Nearest hosts with distances (set by the inventory).
    """

    country: str
    id: str
    name: str
    kind: str = "discovery"
    stage: str = "unknown"
    status_raw: str | None = None
    hc_type: str | None = None
    discovery_year: int | None = None
    operator: str | None = None
    lat: float = 0.0
    lon: float = 0.0
    position_basis: str = "polygon-centroid"
    rings: list = field(default_factory=list)
    volumes: dict[str, Any] = field(default_factory=dict)
    plan_note: str | None = None
    plan_flags: list[str] = field(default_factory=list)
    linked: dict[str, Any] = field(default_factory=dict)
    water_depth_m: float | None = None
    n_wells: int = 0
    source: str = ""
    source_url: str | None = None
    gaps: list[str] = field(default_factory=list)
    distance_km: float | None = None
    bearing: str | None = None
    nearest_hosts: list[dict[str, Any]] = field(default_factory=list)

    def oe_msm3(self) -> float | None:
        """Recoverable oil-equivalent in million Sm3 when the source publishes it, else ``None``."""
        value = self.volumes.get("oe_msm3")
        return float(value) if isinstance(value, (int, float)) else None

    def to_dict(self, include_geometry: bool = False) -> dict[str, Any]:
        """Plain-dict form for JSON/CSV; outline rings only when ``include_geometry`` is true."""
        out = {k: v for k, v in self.__dict__.items() if k != "rings"}
        out["stage_label"] = STAGE_LABELS.get(self.stage, self.stage)
        if include_geometry:
            out["rings"] = self.rings
        return out
