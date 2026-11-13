"""Umbilical design inputs: a plain-Python specification that maps onto the NeqSim Umbilical."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

STATUS_USER = "user"
STATUS_DEFAULT = "screening default"


@dataclass
class FluidLine:
    """Liquid-filled hydraulic or chemical injection tube."""

    name: str
    kind: str
    inner_diameter_mm: float
    design_pressure_bar: float
    design_flow_m3_per_hr: float = 0.0

    def __post_init__(self) -> None:
        if self.kind not in ("hydraulic", "chemical"):
            raise ValueError("kind must be 'hydraulic' or 'chemical', got %r" % self.kind)
        if self.inner_diameter_mm <= 0 or self.design_pressure_bar <= 0:
            raise ValueError("inner diameter and design pressure must be positive for %s" % self.name)


@dataclass
class PowerCable:
    """Electrical cable. Conductor area None uses the NeqSim voltage-class default."""

    name: str
    cores: int
    voltage_v: float
    conductor_area_mm2: Optional[float] = None


@dataclass
class UmbilicalSpec:
    """Everything needed to size an umbilical."""

    name: str
    length_m: float
    water_depth_m: float
    lines: List[FluidLine] = field(default_factory=list)
    cables: List[PowerCable] = field(default_factory=list)
    fibers: List[Dict[str, Any]] = field(default_factory=list)
    power_load_mw: float = 0.0
    power_factor: float = 0.9
    seawater_temperature_c: float = 4.0
    dynamic_service: bool = False
    touchdown_offset_m: Optional[float] = None
    max_installation_tension_kn: Optional[float] = None
    evidence: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.length_m <= 0 or self.water_depth_m <= 0:
            raise ValueError("length_m and water_depth_m must be positive")
        if not (self.lines or self.cables or self.fibers):
            raise ValueError("an umbilical needs at least one functional element")

    def status(self, key: str) -> str:
        """Evidence status of an input (``user`` unless recorded otherwise)."""
        return self.evidence.get(key, STATUS_USER)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UmbilicalSpec":
        """Build from a plain dictionary (JSON friendly, lengths in km or m)."""
        length_m = data.get("length_m")
        if length_m is None and data.get("length_km") is not None:
            length_m = float(data["length_km"]) * 1000.0
        if length_m is None:
            raise ValueError("umbilical length_m or length_km is required")
        depth = data.get("water_depth_m")
        if depth is None:
            raise ValueError("umbilical water_depth_m is required")
        lines = [
            FluidLine(
                name=l["name"],
                kind=l.get("kind", "chemical"),
                inner_diameter_mm=float(l["inner_diameter_mm"]),
                design_pressure_bar=float(l["design_pressure_bar"]),
                design_flow_m3_per_hr=float(l.get("design_flow_m3_per_hr", 0.0)),
            )
            for l in data.get("lines", [])
        ]
        cables = [
            PowerCable(
                name=c["name"],
                cores=int(c["cores"]),
                voltage_v=float(c["voltage_v"]),
                conductor_area_mm2=c.get("conductor_area_mm2"),
            )
            for c in data.get("cables", [])
        ]
        return cls(
            name=data.get("name", "Umbilical"),
            length_m=float(length_m),
            water_depth_m=float(depth),
            lines=lines,
            cables=cables,
            fibers=list(data.get("fibers", [])),
            power_load_mw=float(data.get("power_load_mw", 0.0)),
            power_factor=float(data.get("power_factor", 0.9)),
            seawater_temperature_c=float(data.get("seawater_temperature_c", 4.0)),
            dynamic_service=bool(data.get("dynamic_service", False)),
            touchdown_offset_m=data.get("touchdown_offset_m"),
            max_installation_tension_kn=data.get("max_installation_tension_kn"),
            evidence=dict(data.get("evidence", {})),
        )

    @classmethod
    def from_common_basis(cls, basis: Dict[str, Any]) -> "UmbilicalSpec":
        """Read the ``umbilical`` block of a study COMMON_BASIS style dictionary.

        The block uses the same keys as :meth:`from_dict`. Missing keys raise a
        ``ValueError`` that names them, so that the study basis is completed rather than
        silently defaulted.
        """
        block = basis.get("umbilical")
        if not isinstance(block, dict):
            raise ValueError("common basis has no 'umbilical' block")
        missing = [k for k in ("water_depth_m",) if block.get(k) is None]
        if block.get("length_m") is None and block.get("length_km") is None:
            missing.append("length_m|length_km")
        if missing:
            raise ValueError("umbilical block is missing: " + ", ".join(missing))
        return cls.from_dict(block)
