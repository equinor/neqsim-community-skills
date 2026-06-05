from __future__ import annotations

from dataclasses import dataclass, field
from importlib.util import find_spec
from typing import Any


# Crane TP-410 equivalent-length L/D ratios (kept local so this skill is standalone).
FITTING_LD: dict[str, float] = {
    "elbow_90": 20.0,
    "elbow_90_LR": 20.0,
    "elbow_90_short": 30.0,
    "elbow_45": 16.0,
    "tee_run": 20.0,
    "tee_branch": 60.0,
    "ball_valve": 3.0,
    "gate_valve": 8.0,
    "check_valve": 50.0,
    "reducer": 0.0,
}

_VESSEL_TYPES = ("three_phase_separator", "gas_scrubber")


@dataclass
class UnitOp:
    """A planned NeqSim unit operation."""

    kind: str
    name: str
    params: dict[str, Any] = field(default_factory=dict)


def _fitting_equiv_length(fittings: list[dict[str, Any]], diameter: float) -> float:
    extra = 0.0
    for fitting in fittings:
        ld = FITTING_LD.get(fitting.get("type", ""), 0.0)
        extra += ld * diameter * fitting.get("count", 1)
    return extra


def _plan_items(items: list[dict[str, Any]], prefix: str, plan: list[UnitOp]) -> None:
    for item in items:
        kind = item.get("type")
        if kind == "node":
            continue
        if kind == "segment":
            diameter = float(item["inner_diameter_m"])
            physical = float(item["length_m"])
            extra = _fitting_equiv_length(item.get("fittings", []), diameter)
            plan.append(UnitOp(
                kind="pipe",
                name=f"{prefix} {item.get('id', 'pipe')}",
                params={
                    "length_m": physical,
                    "fitting_equiv_length_m": round(extra, 6),
                    "effective_length_m": round(physical + extra, 6),
                    "inner_diameter_m": diameter,
                    "elevation_m": float(item.get("elevation_m", 0.0)),
                    "wall_roughness_m": item.get("wall_roughness_m"),
                },
            ))
        elif kind == "equipment":
            eq_type = item.get("equipment_type", "")
            name = f"{prefix} {item.get('id', '')}".rstrip()
            if eq_type in _VESSEL_TYPES:
                plan.append(UnitOp(kind=eq_type, name=name, params={
                    "inner_diameter_m": item.get("inner_diameter_m"),
                    "orientation": item.get("orientation", "vertical"),
                }))
            elif eq_type == "cooler":
                plan.append(UnitOp(kind="cooler", name=name, params={
                    "outlet_temperature_C": item.get("outlet_temperature_C", 35.0),
                }))
                if item.get("Cv"):
                    plan.append(UnitOp(kind="valve", name=f"{name} dP", params={
                        "Cv": float(item["Cv"]),
                    }))
            elif eq_type in ("valve", "tuning_valve"):
                # Pass-through: choke/control dP validated separately, not simulated.
                continue
            else:
                raise ValueError(f"Unknown equipment_type '{eq_type}' for '{name}'")
        elif kind == "parallel":
            plan.append(UnitOp(kind="splitter", name=f"{prefix} Splitter", params={
                "branches": len(item.get("branches", [])),
                "split_factors": item.get("split_factors"),
            }))
            for branch in item.get("branches", []):
                _plan_items(branch, prefix, plan)
            plan.append(UnitOp(kind="mixer", name=f"{prefix} Mixer", params={}))
        else:
            raise ValueError(f"Unknown flow_path item type '{kind}'")


def build_plan(section: dict[str, Any], prefix: str | None = None) -> list[UnitOp]:
    """Return an ordered list of planned unit operations for a section.

    This is deterministic and does not require NeqSim.
    """
    if "section_id" not in section:
        raise ValueError("section missing 'section_id'")
    if not isinstance(section.get("flow_path"), list) or not section["flow_path"]:
        raise ValueError("section 'flow_path' must be a non-empty list")
    pfx = prefix or section["section_id"]
    plan: list[UnitOp] = []
    _plan_items(section["flow_path"], pfx, plan)
    return plan


def neqsim_available() -> bool:
    """Return True if the optional NeqSim Python package is importable."""
    return find_spec("neqsim") is not None


def build_process_system(
    section: dict[str, Any],
    inlet_stream: Any,
    process_system: Any,
    prefix: str | None = None,
) -> Any:
    """Build the flow path on a NeqSim ``ProcessSystem``; return the outlet stream.

    Requires the optional ``neqsim`` package. The traversal mirrors
    :func:`build_plan` but instantiates real units. Raises ``RuntimeError`` when
    NeqSim is not installed.
    """
    if not neqsim_available():
        raise RuntimeError(
            "neqsim is not installed; use build_plan() to inspect the plan, "
            "or install the optional 'neqsim' dependency to construct a ProcessSystem."
        )

    from neqsim import jneqsim  # noqa: WPS433 (local import by design)

    PipeBeggsAndBrills = jneqsim.process.equipment.pipeline.PipeBeggsAndBrills
    ThreePhaseSeparator = jneqsim.process.equipment.separator.ThreePhaseSeparator
    GasScrubber = jneqsim.process.equipment.separator.GasScrubber
    Cooler = jneqsim.process.equipment.heatexchanger.Cooler
    ThrottlingValve = jneqsim.process.equipment.valve.ThrottlingValve
    Splitter = jneqsim.process.equipment.splitter.Splitter
    Mixer = jneqsim.process.equipment.mixer.Mixer

    current = inlet_stream

    def _build(items: list[dict[str, Any]], pfx: str) -> None:
        nonlocal current
        for item in items:
            kind = item.get("type")
            if kind == "node":
                continue
            if kind == "segment":
                diameter = float(item["inner_diameter_m"])
                extra = _fitting_equiv_length(item.get("fittings", []), diameter)
                pipe = PipeBeggsAndBrills(f"{pfx} {item.get('id', 'pipe')}", current)
                pipe.setLength(float(item["length_m"]) + extra)
                pipe.setDiameter(diameter)
                pipe.setElevation(float(item.get("elevation_m", 0.0)))
                if item.get("wall_roughness_m") is not None:
                    pipe.setPipeWallRoughness(float(item["wall_roughness_m"]))
                pipe.run()
                process_system.add(pipe)
                current = pipe.getOutletStream()
            elif kind == "equipment":
                eq_type = item.get("equipment_type", "")
                name = f"{pfx} {item.get('id', '')}".rstrip()
                if eq_type == "three_phase_separator":
                    sep = ThreePhaseSeparator(name)
                    sep.addStream(current)
                    if item.get("inner_diameter_m") is not None:
                        sep.setInternalDiameter(float(item["inner_diameter_m"]))
                    sep.run()
                    process_system.add(sep)
                    current = sep.getGasOutStream()
                elif eq_type == "gas_scrubber":
                    scrub = GasScrubber(name)
                    scrub.addStream(current)
                    if item.get("inner_diameter_m") is not None:
                        scrub.setInternalDiameter(float(item["inner_diameter_m"]))
                    scrub.run()
                    process_system.add(scrub)
                    current = scrub.getGasOutStream()
                elif eq_type == "cooler":
                    clr = Cooler(name, current)
                    clr.setOutTemperature(float(item.get("outlet_temperature_C", 35.0)), "C")
                    clr.run()
                    process_system.add(clr)
                    current = clr.getOutletStream()
                    if item.get("Cv"):
                        tv = ThrottlingValve(f"{name} dP", current)
                        tv.setCv(float(item["Cv"]))
                        tv.setPercentValveOpening(100.0)
                        tv.setIsCalcOutPressure(True)
                        tv.run()
                        process_system.add(tv)
                        current = tv.getOutletStream()
                elif eq_type in ("valve", "tuning_valve"):
                    continue
                else:
                    raise ValueError(f"Unknown equipment_type '{eq_type}'")
            elif kind == "parallel":
                branches = item.get("branches", [])
                splitter = Splitter(f"{pfx} Splitter", current)
                splitter.setSplitNumber(len(branches))
                if item.get("split_factors"):
                    splitter.setSplitFactors(list(item["split_factors"]))
                splitter.run()
                process_system.add(splitter)
                mixer = Mixer(f"{pfx} Mixer")
                for i, branch in enumerate(branches):
                    current = splitter.getSplitStream(i)
                    _build(branch, pfx)
                    mixer.addStream(current)
                mixer.run()
                process_system.add(mixer)
                current = mixer.getOutletStream()
            else:
                raise ValueError(f"Unknown flow_path item type '{kind}'")

    pfx = prefix or section["section_id"]
    _build(section["flow_path"], pfx)
    return current
