"""Run the NeqSim umbilical design and load saved results."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .spec import UmbilicalSpec

REQUIRED_KEYS = (
    "configuration",
    "calculatedResults",
    "elementResults",
    "crossSection",
    "designChecks",
    "weight",
)


@dataclass
class DesignResult:
    """Parsed output of ``UmbilicalMechanicalDesign.toJson()``."""

    data: Dict[str, Any]

    @property
    def checks(self) -> Dict[str, bool]:
        return dict(self.data["designChecks"])

    @property
    def accepted(self) -> bool:
        checks = self.data["designChecks"]
        return bool(checks) and all(checks.values())

    @property
    def elements(self) -> List[Dict[str, Any]]:
        return list(self.data["elementResults"])

    @property
    def fluid_lines(self) -> List[Dict[str, Any]]:
        return [e for e in self.elements if e.get("type") in ("hydraulic", "chemical")]

    @property
    def length_m(self) -> float:
        return float(self.data["configuration"]["lengthM"])

    @property
    def water_depth_m(self) -> float:
        return float(self.data["configuration"]["waterDepthM"])

    def result(self, key: str) -> float:
        return float(self.data["calculatedResults"][key])

    def save(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        return path


def load_result(source: Union[str, Path, Dict[str, Any]]) -> DesignResult:
    """Load a saved design JSON (path or dict) and check that it has the expected sections."""
    if isinstance(source, dict):
        data = source
    else:
        data = json.loads(Path(source).read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        raise ValueError(
            "not an umbilical design result, missing sections: %s (was it written by a NeqSim "
            "release with the umbilical physics?)" % ", ".join(missing)
        )
    return DesignResult(data)


def _umbilical_class(ns: Optional[Any]):
    if ns is not None:
        cls = ns.JClass("neqsim.process.equipment.subsea.Umbilical")
    else:
        from neqsim import jneqsim  # imported lazily: needs a JVM

        cls = jneqsim.process.equipment.subsea.Umbilical
    if not hasattr(cls, "setInjectionRate"):
        raise RuntimeError(
            "The NeqSim on the classpath predates the umbilical physics "
            "(Umbilical.setInjectionRate is missing). Use a newer NeqSim release or build, "
            "or load a saved result with load_result()."
        )
    return cls


def run_design(spec: UmbilicalSpec, ns: Optional[Any] = None) -> DesignResult:
    """Build the NeqSim ``Umbilical`` for ``spec``, run the mechanical design and parse the result.

    ``ns`` is an optional namespace with a ``JClass`` helper (the NeqSim dev setup); without
    it the installed ``neqsim`` Python package is used.
    """
    cls = _umbilical_class(ns)
    u = cls(spec.name)
    u.setLength(float(spec.length_m))
    u.setWaterDepth(float(spec.water_depth_m))
    u.setSeawaterTemperatureC(float(spec.seawater_temperature_c))
    u.setDynamicService(bool(spec.dynamic_service))
    if spec.touchdown_offset_m is not None:
        u.setTouchdownOffsetM(float(spec.touchdown_offset_m))
    if spec.max_installation_tension_kn is not None:
        u.setMaxInstallationTensionKN(float(spec.max_installation_tension_kn))
    for line in spec.lines:
        if line.kind == "hydraulic":
            u.addHydraulicLine(line.name, line.inner_diameter_mm, line.design_pressure_bar)
        else:
            u.addChemicalLine(line.name, line.inner_diameter_mm, line.design_pressure_bar)
        if line.design_flow_m3_per_hr > 0:
            u.setInjectionRate(line.name, line.design_flow_m3_per_hr, "m3/hr")
    for cable in spec.cables:
        if cable.conductor_area_mm2:
            u.addElectricalCable(cable.name, cable.cores, cable.voltage_v, cable.conductor_area_mm2)
        else:
            u.addElectricalCable(cable.name, cable.cores, cable.voltage_v)
    for fiber in spec.fibers:
        u.addFiberOptic(fiber["name"], int(fiber.get("count", 12)))
    if spec.power_load_mw > 0:
        u.setPowerLoad(spec.power_load_mw)
        u.setPowerFactor(spec.power_factor)
    design = u.getMechanicalDesign()
    design.calcDesign()
    return load_result(json.loads(str(design.toJson())))
