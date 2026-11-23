"""Instrumentation and safety-system studies from P&ID drawing records.

Three steps, each usable alone:

1. :func:`safety_register` classifies every instrument bubble and tagged inline valve on the drawing. Roles are
   trip initiator, final element (shutdown or blowdown valve), relief device, controller, control valve,
   transmitter, indicator or sensor element. Each item is bound to the equipment or pipe run it sits on, grouped
   into loops by loop number, and collected into per-equipment safeguards. Missing safeguards are listed as gaps.
2. :func:`run_safety_scenarios` simulates the demand cases a separator's safeguards protect against. The cases
   are blocked gas outlet to PAHH, blocked oil outlet to LAHH, loss of inlet to LALL, and blowdown to flare. The
   native NeqSim SIS, ESD logic and depressurization models are used. Acceptance is checked against the design
   data printed on the sheet.
3. :func:`hazop_worksheet` drafts a guide-word worksheet per equipment node. Causes come from the drawn topology,
   safeguards from the register, and consequences from the simulations. Recommendations come from the gaps.

Trip set points and cause-and-effect links are not on a P&ID. Pass them from the cause-and-effect chart or safety
requirement specification; otherwise each assumed value is recorded as an assumption. Results are screening
evidence for review, not a SIL verification, relief study or chaired HAZOP.
"""

from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path
from typing import Any, Optional

INITIATOR = "trip_initiator"
FINAL = "final_element"
RELIEF = "relief_device"
CONTROLLER = "controller"
CONTROL_VALVE = "control_valve"
TRANSMITTER = "transmitter"
INDICATOR = "indicator"
ELEMENT = "sensor_element"
OTHER = "other"

_FINAL_PREFIXES = ("ESV", "ESDV", "SDV", "XV", "BDV", "XSV", "HIPPS")
_RELIEF_PREFIXES = ("PSV", "PRV", "PSE", "TSV", "RD")
_VARIABLES = {"P": "pressure", "L": "level", "T": "temperature", "F": "flow", "A": "analysis", "D": "density",
              "S": "speed", "V": "vibration", "Z": "position"}

DEFAULT_SETPOINTS = {
    "PAHH": {"fraction_of_design_gauge": 0.93},
    "LAHH": {"level_fraction": 0.80},
    "LALL": {"level_fraction": 0.10},
}


def classify_function(function: str) -> tuple[str, str]:
    """Returns ``(role, measured variable)`` for ISA-style function letters (``PST``, ``LIC``, ``ESV`` ...)."""
    fn = function.upper()
    variable = _VARIABLES.get(fn[0], "")
    if fn.startswith("PD"):
        variable = "differential_pressure"
    if fn.startswith(_RELIEF_PREFIXES):
        return RELIEF, "pressure"
    if fn.startswith(_FINAL_PREFIXES):
        return FINAL, ""
    if len(fn) >= 2 and fn[1] in "SZ" and fn not in ("LS", "PS") or "HH" in fn or "LL" in fn:
        return INITIATOR, variable
    if fn.endswith("IC") or fn.endswith("C") and len(fn) <= 3:
        return CONTROLLER, variable
    if fn.endswith("V") and len(fn) == 2:
        return CONTROL_VALVE, variable
    if fn.endswith("T"):
        return TRANSMITTER, variable
    if fn.endswith(("I", "G")) or fn in ("PDI", "LI", "PI", "TI", "FI"):
        return INDICATOR, variable
    if fn.endswith(("E", "W", "X")):
        return ELEMENT, variable
    return OTHER, variable


def _dist_point_polyline(p: tuple[float, float], path: list[list[float]]) -> float:
    best = math.inf
    for (x0, y0), (x1, y1) in zip(path, path[1:]):
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy
        t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - x0) * dx + (p[1] - y0) * dy) / L2))
        best = min(best, math.hypot(p[0] - (x0 + t * dx), p[1] - (y0 + t * dy)))
    return best


def _equipment(records: dict[str, Any]) -> list[dict[str, Any]]:
    return [n for n in records["nodes"] if n["kind"] not in ("off_page_connector", "tee")]


def _node_name(node: dict[str, Any]) -> str:
    if node["kind"] == "off_page_connector":
        return (node.get("label") or node.get("tag") or node["node_id"]).strip()
    return node.get("tag") or node["node_id"]


def _loop(number: str) -> str:
    return re.sub(r"[A-Z]$", "", number or "")


def safety_register(records: dict[str, Any], equipment_margin: float = 60.0,
                    line_reach: float = 60.0) -> dict[str, Any]:
    """Classifies and binds instruments and shutdown valves on the drawing; returns the safeguard register."""
    nodes = {n["node_id"]: n for n in records["nodes"]}
    equipment = _equipment(records)
    edges = [e for e in records["edges"] if e.get("path")]

    items: dict[str, dict[str, Any]] = {}
    for inst in records.get("instruments", []):
        tag = inst["tag"]
        if tag in items:
            items[tag]["occurrences"] += 1
            continue
        role, variable = classify_function(inst["function"])
        item = {"tag": tag, "function": inst["function"], "role": role, "variable": variable,
                "loop": inst["function"][0] + "-" + _loop(inst.get("number", "")), "x": inst["x"], "y": inst["y"],
                "occurrences": 1, "bound_to": "", "bound_kind": "", "equipment": "", "sheet": inst.get("sheet", "")}
        p = (inst["x"], inst["y"])
        host = next((n for n in equipment if n["bbox"][0] - equipment_margin <= p[0] <= n["bbox"][2] + equipment_margin
                     and n["bbox"][1] - equipment_margin <= p[1] <= n["bbox"][3] + equipment_margin), None)
        if host is not None:
            item.update(bound_to=host["node_id"], bound_kind="equipment", equipment=host.get("tag", ""))
        elif edges:
            edge, d = min(((e, _dist_point_polyline(p, e["path"])) for e in edges), key=lambda t: t[1])
            if d <= line_reach:
                item.update(bound_to=edge["edge_id"], bound_kind="line", line_number=edge.get("line_number", ""),
                            equipment=_edge_equipment(edge, nodes))
        items[tag] = item

    # Tagged valves drawn in the pipe runs carry their run, normal position and the equipment side they isolate.
    for edge in records["edges"]:
        for k, inline in enumerate(edge.get("inline_items", [])):
            tag = inline.get("tag", "")
            if not tag:
                continue
            role = classify_function(tag.split("-")[0])[0]
            item = items.setdefault(tag, {"tag": tag, "function": tag.split("-")[0], "role": role, "variable": "",
                                          "loop": "", "x": inline["x"], "y": inline["y"], "occurrences": 1})
            frm, to = nodes.get(edge["from_node"], {}), nodes.get(edge["to_node"], {})
            side, eq, port = "line", "", ""
            if frm.get("kind") not in (None, "off_page_connector", "tee"):
                side, eq, port = "outlet", frm.get("tag", ""), _port_role(frm, edge.get("from_port"))
            elif to.get("kind") not in (None, "off_page_connector", "tee"):
                side, eq, port = "inlet", to.get("tag", ""), _port_role(to, edge.get("to_port"))
            item.update(bound_to=edge["edge_id"], bound_kind="valve", inline_index=k, equipment=eq, side=side,
                        port_role=port, normal_position=inline.get("normal_position", ""),
                        locking=inline.get("locking", ""), valve_class=inline.get("component_class", ""),
                        line_number=edge.get("line_number", ""), normal_flow=bool(edge.get("normal_flow")),
                        run=_node_name(frm) + " -> " + _node_name(to) if frm and to else "")

    loops: dict[str, list[str]] = {}
    for item in items.values():
        if item.get("loop"):
            loops.setdefault(item["loop"], []).append(item["tag"])

    # Shutdown valves further along a normal-flow line (through tees and sheet links) isolate the vessel as well.
    for eq in equipment:
        for downstream in (True, False):
            for tag_, role_, edge_id in _isolation_valves(eq, records["edges"], nodes, items, downstream):
                item = items[tag_]
                if not item.get("equipment") or not item.get("normal_flow"):
                    item.update(equipment=eq.get("tag", ""), side="outlet" if downstream else "inlet",
                                port_role=role_, isolation_path=edge_id, normal_flow=True)

    safeguards: dict[str, dict[str, Any]] = {}
    gaps: list[dict[str, Any]] = []
    for eq in equipment:
        tag = eq.get("tag") or eq["node_id"]
        mine = [i for i in items.values() if i.get("equipment") == tag]
        initiators: dict[str, list[str]] = {}
        for i in mine:
            if i["role"] == INITIATOR:
                initiators.setdefault(i["variable"] or "other", []).append(i["tag"])
        flare, drains, relief_refs = [], [], []
        for start_edge, other, nozzle in _connectors_reached(eq, records["edges"], nodes):
            label = (other.get("label") or "").upper()
            entry_c = {"edge": start_edge, "nozzle": nozzle, "connector": _node_name(other),
                       "sheet": other.get("tag", "")}
            psv = _RELIEF_TAG.findall(label)
            if psv:
                relief_refs.append(dict(entry_c, devices=psv))
            if "FLARE" in label or "VENT" in label or psv:
                flare.append(entry_c)
            elif "DRAIN" in label:
                drains.append(entry_c)
        entry = {"equipment": tag, "kind": eq["kind"], "initiators": initiators,
                 "finalElements": [{k: i.get(k, "") for k in ("tag", "side", "port_role", "normal_position", "locking",
                                                                "normal_flow", "bound_to")}
                                   for i in mine if i["role"] == FINAL],
                 "relief": [i["tag"] for i in mine if i["role"] == RELIEF],
                 "reliefReferences": relief_refs,
                 "controllers": [i["tag"] for i in mine if i["role"] == CONTROLLER],
                 "transmitters": [i["tag"] for i in mine if i["role"] == TRANSMITTER],
                 "flareConnections": flare, "drainConnections": drains}
        safeguards[tag] = entry
        if eq["kind"] in ("separator", "vessel", "tank"):
            if not entry["relief"] and not relief_refs:
                gaps.append({"equipment": tag, "gap": "No relief device (PSV/rupture disc) read on this sheet",
                             "detail": "Flare nozzles: %s" % (", ".join(f["nozzle"] or f["edge"] for f in flare)
                                                              or "none traced"),
                             "action": "Confirm the PSV tag, set pressure and size on the relief sheet or datasheet"})
            elif not entry["relief"]:
                gaps.append({"equipment": tag, "gap": "Relief devices are on another sheet; set pressure and size "
                                                      "not read",
                             "detail": "; ".join("%s via nozzle %s to %s" % ("/".join(r["devices"]), r["nozzle"] or "?",
                                                                            r["sheet"]) for r in relief_refs),
                             "action": "Read the PSV set pressure and orifice from the referenced sheet or datasheet"})
            level_init = initiators.get("level", [])
            if len(level_init) >= 2:
                gaps.append({"equipment": tag, "gap": "%d level trip initiators (%s); their HH/LL function and voting "
                                                      "are not on the P&ID" % (len(level_init), ", ".join(level_init)),
                             "detail": "", "action": "Take LAHH/LALL assignment and voting from the C&E chart"})
            if "pressure" not in initiators:
                gaps.append({"equipment": tag, "gap": "No pressure trip initiator (PSHH/PAHH) bound to the vessel",
                             "detail": "Transmitters: %s" % ", ".join(entry["transmitters"]),
                             "action": "Identify the PAHH initiator in the cause-and-effect chart"})
            if "level" not in initiators:
                gaps.append({"equipment": tag, "gap": "No level trip initiator (LSHH/LSLL) bound to the vessel",
                             "detail": "", "action": "Identify the LAHH/LALL initiators in the cause-and-effect chart"})
            if not any(f["side"] == "inlet" and f["normal_flow"] for f in entry["finalElements"]):
                gaps.append({"equipment": tag, "gap": "No inlet shutdown valve on the normal-flow inlet on this sheet",
                             "detail": "The inlet ESV is probably on the upstream sheet",
                             "action": "Stitch the upstream sheet or name the inlet ESV in the cause-and-effect input"})

    counts: dict[str, int] = {}
    for item in items.values():
        counts[item["role"]] = counts.get(item["role"], 0) + 1
    return {"schemaVersion": "neqsim_pid_safety_register.v1", "source": records.get("source", {}).get("file", ""),
            "items": sorted(items.values(), key=lambda i: (i["role"], i["tag"])), "loops": loops,
            "equipment": safeguards, "gaps": gaps, "counts": counts,
            "note": "Roles come from ISA function letters and bindings from drawing proximity. Trip set points, "
                    "voting and cause-and-effect links are not on a P&ID; confirm them in the C&E chart and SRS."}


def _port_role(node: dict[str, Any], port_id: Optional[str]) -> str:
    return next((p.get("role", "") for p in node.get("ports", []) if p["port_id"] == port_id), "")


_RELIEF_TAG = re.compile(r"\b\d*(?:PSV|PRV|PSE|TSV)-?\d{3,5}[A-Z]?(?:/[A-Z])*")


def _isolation_valves(eq: dict[str, Any], edges: list[dict[str, Any]], nodes: dict[str, Any],
                      items: dict[str, dict[str, Any]], downstream: bool) -> list[tuple[str, str, str]]:
    """Tagged final elements on normal-flow lines leaving (or entering) the vessel, followed through tees,
    off-page connectors and sheet links up to the next equipment item."""
    found = []
    for e in edges:
        if not e.get("normal_flow") or (e["from_node"] if downstream else e["to_node"]) != eq["node_id"]:
            continue
        role = _port_role(eq, e.get("from_port") if downstream else e.get("to_port"))
        stack, seen = [e], set()
        while stack:
            edge = stack.pop()
            if edge["edge_id"] in seen:
                continue
            seen.add(edge["edge_id"])
            for inline in edge.get("inline_items", []):
                tag = inline.get("tag", "")
                if tag in items and items[tag]["role"] == FINAL:
                    found.append((tag, role, edge["edge_id"]))
            nxt = edge["to_node"] if downstream else edge["from_node"]
            if nodes.get(nxt, {}).get("kind") not in ("tee", "off_page_connector"):
                continue
            for f in edges:
                if f.get("normal_flow") and (f["from_node"] if downstream else f["to_node"]) == nxt:
                    stack.append(f)
    return found


def _connectors_reached(eq: dict[str, Any], edges: list[dict[str, Any]],
                        nodes: dict[str, Any]) -> list[tuple[str, dict[str, Any], str]]:
    """Connectors reachable from an equipment item through tees only, with the first edge and the vessel nozzle."""
    adj: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for e in edges:
        adj.setdefault(e["from_node"], []).append((e["to_node"], e))
        adj.setdefault(e["to_node"], []).append((e["from_node"], e))
    found = []
    for first_node, first in adj.get(eq["node_id"], []):
        port = first.get("from_port") if first["from_node"] == eq["node_id"] else first.get("to_port")
        nozzle = _port_label(eq, port)
        seen = {eq["node_id"]}
        stack = [first_node]
        while stack:
            nid = stack.pop()
            if nid in seen:
                continue
            seen.add(nid)
            node = nodes.get(nid, {})
            if node.get("kind") == "off_page_connector":
                found.append((first["edge_id"], node, nozzle))
            elif node.get("kind") == "tee":
                stack.extend(n for n, _ in adj.get(nid, []))
    unique, keys = [], set()
    for item in found:
        key = (item[0], item[1]["node_id"])
        if key not in keys:
            keys.add(key)
            unique.append(item)
    return unique


def _port_label(node: dict[str, Any], port_id: Optional[str]) -> str:
    return next((p.get("label", "") for p in node.get("ports", []) if p["port_id"] == port_id), "")


def _edge_equipment(edge: dict[str, Any], nodes: dict[str, Any]) -> str:
    for key in ("from_node", "to_node"):
        n = nodes.get(edge[key], {})
        if n.get("kind") not in (None, "off_page_connector", "tee"):
            return n.get("tag", "")
    return ""


# --------------------------------------------------------------------------------------------- simulations
def _parse_range(text: Any) -> list[float]:
    if isinstance(text, dict):
        return [float(text["value"])]
    return [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", str(text or ""))]


def _setpoint(name: str, setpoints: dict[str, Any], design_barg: float, assumptions: list[str]) -> dict[str, Any]:
    given = setpoints.get(name)
    if given:
        return dict(given, source=given.get("source", "user input / cause-and-effect"))
    d = DEFAULT_SETPOINTS[name]
    if name == "PAHH":
        value = round(d["fraction_of_design_gauge"] * design_barg, 2)
        assumptions.append("PAHH set point %.2f barg assumed at %.0f %% of the %.1f barg design pressure (not on the "
                           "P&ID)." % (value, 100 * d["fraction_of_design_gauge"], design_barg))
        return {"value": value, "unit": "barg", "source": "assumed"}
    assumptions.append("%s set point assumed at %.0f %% of vessel height (not on the P&ID)." % (
        name, 100 * d["level_fraction"]))
    return {"value": d["level_fraction"], "unit": "fraction", "source": "assumed"}


def _vessel_volume(diameter: float, length: float) -> float:
    """Cylinder plus two 2:1 ellipsoidal heads, m3."""
    return math.pi / 4.0 * diameter ** 2 * length + math.pi * diameter ** 3 / 12.0


def run_safety_scenarios(records: dict[str, Any], fluid: dict[str, Any], feed_flow: float, out_dir: str | Path,
                         feed_flow_unit: str = "kg/hr", jar: Optional[str | Path] = None,
                         setpoints: Optional[dict[str, Any]] = None, cause_effect: Optional[dict[str, Any]] = None,
                         stroke_time_s: float = 15.0, normal_level: float = 0.5, gas_nozzle_level: float = 0.95,
                         dt: float = 2.0, horizon_s: float = 3600.0, blowdown: bool = True,
                         flare_back_pressure_bara: float = 1.5, register: Optional[dict[str, Any]] = None,
                         equipment_tag: Optional[str] = None) -> dict[str, Any]:
    """Simulates the demand cases for the first separator (or ``equipment_tag``) on the drawing.

    ``setpoints`` maps ``PAHH``, ``LAHH`` and ``LALL`` to ``{"value", "unit" ("barg" or "fraction"), "tag"}``.
    ``cause_effect`` maps a trip (``PAHH``...) to ``{"initiators": [tags], "final_elements": [tags],
    "voting": "1oo1"|"2oo3"...}``; missing entries fall back to the register and are reported. Writes
    ``safety_scenarios.json`` and trend plots to ``out_dir``.
    """
    from .pipeline import make_fluid, start_jvm

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    setpoints = setpoints or {}
    cause_effect = cause_effect or {}
    register = register or safety_register(records)
    sep = next((n for n in records["nodes"] if n["kind"] == "separator"
                and (equipment_tag is None or n.get("tag") == equipment_tag)), None)
    if sep is None:
        raise ValueError("No separator %s in the records" % (equipment_tag or ""))
    attrs = sep.get("attributes", {})
    assumptions: list[str] = []
    diameter = attrs.get("insideDiameter_mm", 0.0) / 1000.0
    length = attrs.get("tanTanLength_mm", 0.0) / 1000.0
    if not diameter or not length:
        raise ValueError("Separator %s has no diameter/length in its data block; pass them in the records"
                         % sep.get("tag"))
    design = _parse_range(attrs.get("designPressure"))
    design_barg = max(design) if design else None
    dtemp = _parse_range(attrs.get("designTemperature"))
    design_min_c = min(dtemp) if dtemp else None
    op_p = _parse_range(attrs.get("operatingPressure"))
    op_t = _parse_range(attrs.get("operatingTemperature"))
    if design_barg is None or not op_p or not op_t:
        raise ValueError("Design and operating pressure/temperature are needed from the data block")
    p_op = op_p[0] + 1.01325
    t_op = op_t[0]
    safeguards = register["equipment"].get(sep.get("tag"), {})

    J = start_jvm(jar)
    pahh = _setpoint("PAHH", setpoints, design_barg, assumptions)
    lahh = _setpoint("LAHH", setpoints, design_barg, assumptions)
    lall = _setpoint("LALL", setpoints, design_barg, assumptions)
    assumptions.append("Normal liquid level %.0f %% of height and gas outlet nozzle at %.0f %% (not on the P&ID)."
                       % (100 * normal_level, 100 * gas_nozzle_level))
    assumptions.append("Shutdown valve stroke time %.0f s (valve datasheet not read)." % stroke_time_s)
    assumptions.append("Gas pressure control is a proportional controller on the gas outlet holding the operating "
                       "pressure (controller tuning not on the P&ID); it is disabled in the blocked gas outlet case.")

    def trip(name: str, variable: str, side: str) -> dict[str, Any]:
        ce = cause_effect.get(name, {})
        initiators = ce.get("initiators") or safeguards.get("initiators", {}).get(variable, [])
        finals = ce.get("final_elements") or [f["tag"] for f in safeguards.get("finalElements", [])
                                               if f["side"] == side and f["normal_flow"]]
        source = "cause-and-effect input" if ce else "drawing register"
        if not initiators:
            initiators = ["%s (initiator not on drawing)" % name]
            source = "placeholder"
        if not finals:
            finals = ["%s isolation (final element not on this sheet)" % side]
            source += "; final element placeholder"
        return {"trip": name, "initiators": initiators, "finalElements": finals, "voting": ce.get("voting", "1oo1"),
                "linkSource": source}

    cases = [
        ("blocked_gas_outlet", "Gas outlet blocked (e.g. downstream valve closes)", trip("PAHH", "pressure", "inlet")),
        ("blocked_oil_outlet", "Oil outlet blocked (e.g. LV fails closed)", trip("LAHH", "level", "inlet")),
        ("loss_of_inlet", "Inlet flow lost; outlets keep draining", trip("LALL", "level", "outlet")),
    ]
    results = {"equipment": sep.get("tag"), "vessel": {"insideDiameter_m": diameter, "tanTanLength_m": length,
                                                       "volume_m3": round(_vessel_volume(diameter, length), 2),
                                                       "designPressure_barg": design_barg,
                                                       "designMinTemperature_C": design_min_c,
                                                       "operatingPressure_bara": round(p_op, 3),
                                                       "operatingTemperature_C": t_op},
               "setpoints": {"PAHH": pahh, "LAHH": lahh, "LALL": lall}, "scenarios": [], "assumptions": assumptions}
    for case, cause, link in cases:
        results["scenarios"].append(_simulate_case(J, fluid, feed_flow, feed_flow_unit, case, cause, link, results,
                                                   p_op, t_op, normal_level, gas_nozzle_level, stroke_time_s, dt,
                                                   horizon_s, out))
    if blowdown:
        results["scenarios"].append(_blowdown(J, fluid, feed_flow, feed_flow_unit, results, p_op, t_op, normal_level,
                                              flare_back_pressure_bara, safeguards, out))
    results["passed"] = all(s.get("verdict") != "FAIL" for s in results["scenarios"])
    (out / "safety_scenarios.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    return results


def _build_vessel(J, fluid_spec, feed_flow, unit, p_op, t_op, diameter, length, level, tag):
    from .pipeline import make_fluid

    fluid = make_fluid(J, fluid_spec)
    fluid.setTemperature(273.15 + t_op)
    fluid.setPressure(p_op)
    feed = J("neqsim.process.equipment.stream.Stream")(tag + " feed", fluid)
    feed.setFlowRate(float(feed_flow), unit)
    feed.run()
    vessel = J("neqsim.process.equipment.separator.ThreePhaseSeparator")(tag, feed)
    vessel.setOrientation("horizontal")
    vessel.setInternalDiameter(diameter)
    vessel.setSeparatorLength(length)
    vessel.setLiquidLevel(level)
    vessel.run()
    vessel.setCalculateSteadyState(False)
    vessel.initializeTransientCalculation()
    return feed, vessel


def _esd_valve(J, feed, name, p_op, stroke):
    valve = J("neqsim.process.equipment.valve.ESDValve")(name, feed.clone(name + " carrier"))
    valve.setOutletPressure(p_op)
    valve.setStrokeTime(stroke)
    valve.setPhysicalStepIdempotencyEnabled(True)
    valve.run()
    return valve


def _simulate_case(J, fluid, feed_flow, unit, case, cause, link, results, p_op, t_op, level0, gas_nozzle, stroke, dt,
                   horizon, out):
    v = results["vessel"]
    feed, vessel = _build_vessel(J, fluid, feed_flow, unit, p_op, t_op, v["insideDiameter_m"], v["tanTanLength_m"],
                                 level0, results["equipment"] + " " + case)
    base = float(feed.getFlowRate("kg/sec"))
    valve = _esd_valve(J, feed, link["finalElements"][0], p_op, stroke)
    D = J("neqsim.process.logic.sis.Detector")
    voting = {"1oo1": "ONE_OUT_OF_ONE", "1oo2": "ONE_OUT_OF_TWO", "2oo2": "TWO_OUT_OF_TWO",
              "2oo3": "TWO_OUT_OF_THREE"}.get(link["voting"], "ONE_OUT_OF_ONE")
    sif = J("neqsim.process.logic.sis.SafetyInstrumentedFunction")(link["trip"] + " " + results["equipment"],
                                                                   getattr(J("neqsim.process.logic.sis.VotingLogic"),
                                                                           voting))
    sp = results["setpoints"][link["trip"]]
    if link["trip"] == "PAHH":
        limit = sp["value"] + 1.01325 if sp.get("unit", "barg") == "barg" else sp["value"]
        dtype, level_kind, unit_txt = D.DetectorType.PRESSURE, D.AlarmLevel.HIGH_HIGH, "bara"
    else:
        limit = sp["value"]
        dtype, unit_txt = D.DetectorType.LEVEL, "fraction"
        level_kind = D.AlarmLevel.HIGH_HIGH if link["trip"] == "LAHH" else D.AlarmLevel.LOW_LOW
    n_sensors = {"ONE_OUT_OF_ONE": 1, "ONE_OUT_OF_TWO": 2, "TWO_OUT_OF_TWO": 2, "TWO_OUT_OF_THREE": 3}[voting]
    tags = (link["initiators"] * n_sensors)[:n_sensors]
    for tag in tags:
        sif.addDetector(D(tag, dtype, level_kind, float(limit), unit_txt))
    esd = J("neqsim.process.logic.esd.ESDLogic")("ESD " + link["trip"])
    esd.addAction(J("neqsim.process.logic.action.TripValveAction")(valve), 0.0)
    sif.linkToLogic(esd)
    ident = J("neqsim.process.dynamics.TransientStepIdentifier")

    upset_at = 10.0
    rows, trip_t, closed_t = [], None, None
    after_close = 0.0
    for i in range(int(horizon / dt)):
        t = i * dt
        p = float(vessel.getThermoSystem().getPressure("bara"))
        lvl = float(vessel.getLiquidLevel())
        measured = p if link["trip"] == "PAHH" else lvl
        sif.update(*([measured] * n_sensors))
        if sif.isTripped() and trip_t is None:
            trip_t = t
        opening = float(valve.getPercentValveOpening()) / 100.0
        upset = t >= upset_at
        if case != "blocked_gas_outlet":
            # Gas pressure control (the PIC on the gas outlet) holds the operating pressure.
            vessel.setGasOutletFlowFraction(max(0.0, min(1.0, 1.0 + 8.0 * (p - p_op) / p_op)))
        if case == "blocked_gas_outlet":
            vessel.setGasOutletFlowFraction(0.0 if upset else 1.0)
            feed.setFlowRate(max(1e-6, base * opening), "kg/sec")
        elif case == "blocked_oil_outlet":
            vessel.setOilOutletFlowFraction(0.0 if upset else 1.0)
            feed.setFlowRate(max(1e-6, base * opening), "kg/sec")
        else:
            ramp = min(1.0, max(0.0, (t - upset_at) / 30.0)) if upset else 0.0
            feed.setFlowRate(base * (1.0 - 0.99 * ramp), "kg/sec")
            vessel.setOilOutletFlowFraction(opening)
            vessel.setWaterOutletFlowFraction(opening)
        feed.run()
        sid = ident.deterministicPhysicalStep("pid-safety-" + case, i)
        esd.execute(dt)
        valve.runTransient(dt, sid)
        _advance(vessel, ident, case, i, dt, sid)
        if opening <= 1e-9 and closed_t is None and trip_t is not None:
            closed_t = t
        rows.append({"time_s": t, "pressure_bara": p, "level_fraction": lvl, "valve_open_pct": 100.0 * opening})
        if closed_t is not None:
            after_close += dt
            if after_close >= 120.0:
                break

    peak_p = max(r["pressure_bara"] for r in rows)
    peak_l = max(r["level_fraction"] for r in rows)
    min_l = min(r["level_fraction"] for r in rows)
    design_bara = v["designPressure_barg"] + 1.01325
    if case == "blocked_gas_outlet":
        criterion = "peak pressure %.2f bara <= design %.2f bara" % (peak_p, design_bara)
        ok = peak_p <= design_bara
        margin = design_bara - peak_p
        rate = _initial_rate([r["pressure_bara"] for r in rows], upset_at, dt)
        unprotected = (design_bara - p_op) / rate if rate > 0 else None
        quantity = {"peakPressure_bara": round(peak_p, 3), "marginToDesign_bar": round(margin, 3),
                    "pressureRiseRate_bar_s": round(rate, 5),
                    "timeToDesignPressureWithoutTrip_s": None if unprotected is None else round(unprotected, 1)}
    elif case == "blocked_oil_outlet":
        criterion = "peak level %.3f < gas outlet nozzle %.2f" % (peak_l, gas_nozzle)
        ok = peak_l < gas_nozzle
        rate = _initial_rate([r["level_fraction"] for r in rows], upset_at, dt)
        unprotected = (gas_nozzle - level0) / rate if rate > 0 else None
        quantity = {"peakLevel_fraction": round(peak_l, 4), "levelRiseRate_per_s": round(rate, 7),
                    "timeToGasNozzleWithoutTrip_s": None if unprotected is None else round(unprotected, 1)}
    else:
        criterion = "minimum level %.3f > 0 (no gas blow-by to the liquid outlets)" % min_l
        ok = min_l > 0.02
        rate = -_initial_rate([r["level_fraction"] for r in rows], upset_at, dt)
        unprotected = level0 / rate if rate > 0 else None
        quantity = {"minimumLevel_fraction": round(min_l, 4), "levelFallRate_per_s": round(rate, 7),
                    "timeToEmptyWithoutTrip_s": None if unprotected is None else round(unprotected, 1)}
    verdict = "PASS" if ok and trip_t is not None else "FAIL"
    if trip_t is None:
        criterion += "; trip not reached within %.0f s" % horizon
    _plot(rows, case, out)
    return {"case": case, "cause": cause, "trip": link["trip"], "setpoint": results["setpoints"][link["trip"]],
            "initiators": link["initiators"], "finalElements": link["finalElements"], "voting": link["voting"],
            "linkSource": link["linkSource"], "upsetAt_s": upset_at,
            "tripAt_s": trip_t, "tripDelayAfterUpset_s": None if trip_t is None else trip_t - upset_at,
            "valveClosedAt_s": closed_t, **quantity, "criterion": criterion, "verdict": verdict,
            "trend": "trend_%s.png" % case, "samples": len(rows)}


def _advance(vessel, ident, case: str, index: int, dt: float, sid) -> None:
    """Advances the vessel one step; on a rejected explicit step, retries with finer sub-steps."""
    try:
        vessel.runTransient(dt, sid)
        return
    except Exception:  # noqa: BLE001 - the Java solver rejects non-physical states with IllegalStateException
        pass
    for n in (4, 16, 64):
        try:
            for k in range(n):
                vessel.runTransient(dt / n, ident.deterministicPhysicalStep("pid-safety-%s-%d-%d" % (case, index, n), k))
            return
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError("Transient separator step %d of case %s did not converge even with 64 sub-steps" % (index, case))


def _initial_rate(values: list[float], upset_at: float, dt: float, window_s: float = 60.0) -> float:
    i0 = int(upset_at / dt) + 1
    i1 = min(len(values) - 1, i0 + int(window_s / dt))
    return (values[i1] - values[i0]) / ((i1 - i0) * dt) if i1 > i0 else 0.0


def _blowdown(J, fluid_spec, feed_flow, unit, results, p_op, t_op, level0, back_bara, safeguards, out,
              allowable_stress_mpa=200.0):
    """Sizes a blowdown orifice to 6.9 barg in 15 min from the PAHH trip pressure and reports flare load and MDMT."""
    v = results["vessel"]
    feed, vessel = _build_vessel(J, fluid_spec, feed_flow, unit, p_op, t_op, v["insideDiameter_m"],
                                 v["tanTanLength_m"], level0, results["equipment"] + " blowdown")
    pahh = results["setpoints"]["PAHH"]
    p_start = pahh["value"] + 1.01325 if pahh.get("unit", "barg") == "barg" else pahh["value"]
    inventory = vessel.getThermoSystem().clone()
    inventory.setPressure(p_start)
    ops = J("neqsim.thermodynamicoperations.ThermodynamicOperations")(inventory)
    ops.TPflash()
    inventory.initProperties()
    gas_volume = v["volume_m3"] * (1.0 - level0)
    gas = J("neqsim.thermo.system.SystemInterface")
    vapour = inventory.phaseToSystem(0)
    vapour.setPressure(p_start)
    sim_cls = J("neqsim.process.safety.depressurization.DepressurizationSimulator")
    target_s = 900.0

    def run(d, max_time=target_s + 60.0):
        sim = sim_cls(vapour.clone(), gas_volume, d, 0.84, back_bara * 1.0e5)
        sim.setTimeStep(5.0).setMaxTime(max_time).setStopPressure(max(back_bara, 1.2) * 1.0e5)
        return sim.run()

    lo, hi = 0.005, 0.30
    res_hi = run(hi)
    if math.isnan(res_hi.timeTo7BargS) or res_hi.timeTo7BargS > target_s:
        return {"case": "blowdown", "verdict": "FAIL", "criterion": "no orifice up to 300 mm reaches 6.9 barg in 15 min"}
    for _ in range(9):
        mid = 0.5 * (lo + hi)
        res = run(mid)
        if not math.isnan(res.timeTo7BargS) and res.timeTo7BargS <= target_s:
            hi, res_hi = mid, res
        else:
            lo = mid
    res = run(hi, 4.0 * 3600.0)  # complete blowdown to the stop pressure for the minimum temperature
    # Metal temperature with heat from the gas-wetted shell; thickness estimated from the design pressure.
    design_mpa = v["designPressure_barg"] / 10.0
    radius_mm = 500.0 * v["insideDiameter_m"]
    thickness_m = design_mpa * radius_mm / (allowable_stress_mpa - 0.6 * design_mpa) / 1000.0
    area = (1.0 - level0) * (math.pi * v["insideDiameter_m"] * v["tanTanLength_m"]
                             + 2.0 * 1.084 * v["insideDiameter_m"] ** 2)
    wall_mass = area * thickness_m * 7800.0
    sim = sim_cls(vapour.clone(), gas_volume, hi, 0.84, back_bara * 1.0e5)
    sim.setTimeStep(5.0).setMaxTime(4.0 * 3600.0).setStopPressure(max(back_bara, 1.2) * 1.0e5)
    sim.setWall(wall_mass, area, 480.0, 30.0)
    walled = sim.run()
    min_wall_c = float(walled.minWallTemperatureK) - 273.15
    min_gas_wall_case_c = float(walled.minFluidTemperatureK) - 273.15
    results["assumptions"].append(
        "Blowdown wall model: shell thickness %.0f mm from the design pressure (allowable stress %.0f MPa assumed), "
        "gas-wetted area %.0f m2, wall mass %.0f kg, cp 480 J/kgK, inside film coefficient 30 W/m2K." % (
            1000 * thickness_m, allowable_stress_mpa, area, wall_mass))
    flows = [float(x) for x in res.massFlowKgPerS]
    min_t_c = float(res.minFluidTemperatureK) - 273.15
    design_min = v["designMinTemperature_C"]
    mdmt_ok = design_min is None or min_wall_c >= design_min
    rows = [{"time_s": float(t), "pressure_bara": float(p), "flow_kg_s": float(m), "temperature_C": float(T) - 273.15}
            for t, p, m, T in zip(res.time, res.pressureBara, res.massFlowKgPerS, res.temperatureK)]
    _plot_blowdown(rows, out)
    results["assumptions"].append("Blowdown of the gas cap only (%.1f m3 at %.0f %% level), from the PAHH set point, "
                                  "Cd 0.84, flare header %.1f bara, no fire. The gas temperature bound is adiabatic; a second run adds the shell wall." % (
                                      gas_volume, 100 * level0, back_bara))
    return {"case": "blowdown", "cause": "ESD with depressurization to flare (BDV not read on this sheet)"
            if not any(f["tag"].startswith("BDV") for f in safeguards.get("finalElements", [])) else "ESD with BDV",
            "flareConnections": safeguards.get("flareConnections", []),
            "orificeDiameter_mm": round(1000 * hi, 1), "startPressure_bara": round(p_start, 2),
            "timeTo6p9barg_s": round(float(res.timeTo7BargS), 1), "peakFlareRate_kg_s": round(max(flows), 2),
            "peakFlareRate_kg_h": round(3600 * max(flows), 0), "minimumFluidTemperature_C": round(min_t_c, 1),
            "minimumWallTemperature_C": round(min_wall_c, 1),
            "minimumGasTemperatureWithWall_C": round(min_gas_wall_case_c, 1),
            "designMinTemperature_C": design_min,
            "endPressure_bara": round(float(res.pressureBara[len(res.pressureBara) - 1]), 2),
            "duration_s": round(float(res.time[len(res.time) - 1]), 0),
            "basis": "minimum gas temperature: conservative bound (gas cap only, adiabatic); minimum wall temperature: "
                     "lumped wall with estimated thickness, no liquid heat",
            "criterion": "6.9 barg within 15 min (API 521 / NORSOK S-001 guideline) and minimum wall temperature "
                         "%.1f C >= design minimum %s C over the full blowdown (adiabatic gas bound %.1f C)" % (
                             min_wall_c, design_min, min_t_c),
            "verdict": "PASS" if mdmt_ok else "FAIL", "trend": "trend_blowdown.png"}


def _plot(rows, case, out):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:  # pragma: no cover
        return
    t = [r["time_s"] for r in rows]
    fig, ax = plt.subplots(3, 1, figsize=(7, 6), sharex=True)
    ax[0].plot(t, [r["pressure_bara"] for r in rows])
    ax[0].set_ylabel("Pressure, bara")
    ax[1].plot(t, [r["level_fraction"] for r in rows])
    ax[1].set_ylabel("Level, fraction")
    ax[2].plot(t, [r["valve_open_pct"] for r in rows])
    ax[2].set_ylabel("ESD valve, % open")
    ax[2].set_xlabel("Time, s")
    ax[0].set_title(case.replace("_", " "))
    fig.tight_layout()
    fig.savefig(Path(out) / ("trend_%s.png" % case), dpi=110)
    plt.close(fig)


def _plot_blowdown(rows, out):
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:  # pragma: no cover
        return
    t = [r["time_s"] for r in rows]
    fig, ax = plt.subplots(3, 1, figsize=(7, 6), sharex=True)
    ax[0].plot(t, [r["pressure_bara"] for r in rows])
    ax[0].set_ylabel("Pressure, bara")
    ax[1].plot(t, [r["flow_kg_s"] for r in rows])
    ax[1].set_ylabel("Flare rate, kg/s")
    ax[2].plot(t, [r["temperature_C"] for r in rows])
    ax[2].set_ylabel("Gas temperature, C")
    ax[2].set_xlabel("Time, s")
    ax[0].set_title("blowdown to flare")
    fig.tight_layout()
    fig.savefig(Path(out) / "trend_blowdown.png", dpi=110)
    plt.close(fig)


# ------------------------------------------------------------------------------------------------- HAZOP
_QUANT_LABELS = [
    ("tripDelayAfterUpset_s", "trip after %.0f s"), ("peakPressure_bara", "peak %.2f bara"),
    ("marginToDesign_bar", "%.2f bar below design"), ("timeToDesignPressureWithoutTrip_s",
                                                       "design pressure in %.0f s without trip"),
    ("peakLevel_fraction", "peak level %.2f"), ("timeToGasNozzleWithoutTrip_s", "liquid at gas nozzle in %.0f s "
                                                                                "without trip"),
    ("minimumLevel_fraction", "minimum level %.2f"), ("timeToEmptyWithoutTrip_s", "empty in %.0f s without trip"),
    ("orificeDiameter_mm", "orifice %.1f mm"), ("timeTo6p9barg_s", "6.9 barg in %.0f s"),
    ("peakFlareRate_kg_h", "peak flare %.0f kg/h"), ("minimumWallTemperature_C", "minimum wall %.1f C"), ("minimumFluidTemperature_C", "adiabatic gas bound %.1f C"),
]


def _flow_ends(eq: dict[str, Any], edges: list[dict[str, Any]], nodes: dict[str, Any],
               downstream: bool) -> dict[str, list[str]]:
    """Normal-flow destinations (or sources) of each vessel nozzle role, followed through tees to connectors or
    equipment."""
    out: dict[str, list[str]] = {}
    for e in edges:
        if not e.get("normal_flow"):
            continue
        start = e["from_node"] if downstream else e["to_node"]
        if start != eq["node_id"]:
            continue
        role = _port_role(eq, e.get("from_port") if downstream else e.get("to_port")) or (
            "Outlet" if downstream else "Inlet")
        stack, seen = [e["to_node"] if downstream else e["from_node"]], {eq["node_id"]}
        while stack:
            nid = stack.pop()
            if nid in seen:
                continue
            seen.add(nid)
            node = nodes.get(nid, {})
            if node.get("kind") == "tee":
                for f in edges:
                    if f.get("normal_flow") and f["from_node" if downstream else "to_node"] == nid:
                        stack.append(f["to_node"] if downstream else f["from_node"])
            elif node:
                name = _node_name(node)
                if name not in out.setdefault(role, []):
                    out[role].append(name)
    return out


def _unique(values: list[str]) -> list[str]:
    seen: list[str] = []
    for v in values:
        if v and v not in seen:
            seen.append(v)
    return seen


def hazop_worksheet(records: dict[str, Any], register: dict[str, Any],
                    scenarios: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """Drafts guide-word rows per vessel node: causes from topology, safeguards from the drawing, consequences
    from the simulations. Rows are a preparation aid for a chaired HAZOP."""
    nodes = {n["node_id"]: n for n in records["nodes"]}
    sims = {s["case"]: s for s in (scenarios or {}).get("scenarios", [])}
    rows: list[dict[str, Any]] = []
    for tag, sg in register["equipment"].items():
        eq = next((n for n in records["nodes"] if n.get("tag") == tag), None)
        if eq is None or eq["kind"] not in ("separator", "vessel", "tank"):
            continue
        outlets = _flow_ends(eq, records["edges"], nodes, True)
        inlets = sum(_flow_ends(eq, records["edges"], nodes, False).values(), [])
        init = sg.get("initiators", {})
        finals = _unique([f["tag"] for f in sg.get("finalElements", []) if f.get("normal_flow")])
        relief_list = _unique(list(sg.get("relief", [])) + ["%s (sheet %s)" % ("/".join(r["devices"]), r["sheet"])
                                                            for r in sg.get("reliefReferences", [])])
        node = "%s (%s)" % (tag, eq.get("attributes", {}).get("service", eq["kind"]))
        level_ctrl = [c for c in sg.get("controllers", []) if c.startswith("L")]
        press_ctrl = [c for c in sg.get("controllers", []) if c.startswith("P")]
        flare = _unique([f["nozzle"] for f in sg.get("flareConnections", []) if f["nozzle"]])

        def guard(*parts: str) -> str:
            return "; ".join(p for p in parts if p)

        def trip(name: str, tags: list[str]) -> str:
            final = ", ".join(finals) if finals else "final element not on this sheet"
            return "%s %s -> %s" % (name, ", ".join(tags), final) if tags else "%s not read on sheet" % name

        def add(guide, param, cause, consequence, safeguards, case=None, recommendation=""):
            sim = sims.get(case or "", {})
            quant = "; ".join(fmt % sim[key] for key, fmt in _QUANT_LABELS if sim.get(key) is not None)
            if sim.get("verdict") == "FAIL" and not recommendation:
                recommendation = "Simulated protection does not meet: %s" % sim.get("criterion", "")
            rows.append({"node": node, "guideword": guide, "parameter": param, "deviation": "%s %s" % (guide, param),
                         "cause": cause, "consequence": consequence, "quantified": quant,
                         "verdict": sim.get("verdict", ""), "safeguards": safeguards,
                         "recommendation": recommendation, "evidence": sim.get("trend", "")})

        gas_to = ", ".join(outlets.get("GasOutlet", [])) or "the gas outlet"
        oil_to = ", ".join(outlets.get("OilOutlet", [])) or "the oil outlet"
        water_to = ", ".join(outlets.get("WaterOutlet", [])) or "the water outlet"
        psv = "PSV %s" % ", ".join(relief_list) if relief_list else "no PSV read on sheet"
        psv_action = ("Confirm PSV set pressure and capacity for the blocked-outlet relief load (set pressure not on "
                      "this sheet)" if relief_list else "Confirm the relief device and set pressure for blocked outlet")
        pahh = trip("PAHH", init.get("pressure", []))
        add("NO", "FLOW", "Gas outlet to %s blocked (downstream valve closes, compressor trip)" % gas_to,
            "Pressure rises towards design pressure; overpressure of %s" % tag,
            guard(pahh, psv, ", ".join(press_ctrl)), "blocked_gas_outlet",
            psv_action + ("" if init.get("pressure") else "; identify the PAHH initiator in the C&E chart"))
        add("MORE", "PRESSURE", "As NO FLOW gas; high pressure from upstream", "Overpressure; relief to flare",
            guard(pahh, psv), "blocked_gas_outlet", psv_action)
        add("MORE", "LEVEL", "Oil outlet to %s blocked; level control %s fails closed" % (
            oil_to, ", ".join(level_ctrl) or "(not read)"), "Liquid carry-over to %s" % gas_to,
            guard(trip("LAHH", init.get("level", [])), ", ".join(level_ctrl)), "blocked_oil_outlet")
        add("LESS", "LEVEL", "Loss of inlet with the liquid outlets still open; level valve fails open",
            "Gas blow-by to %s and %s" % (oil_to, water_to),
            guard(trip("LALL", init.get("level", [])), ", ".join(level_ctrl)), "loss_of_inlet")
        add("NO", "FLOW", "Inlet from %s isolated or lost" % (", ".join(inlets) or "upstream"),
            "Level falls; see LESS LEVEL", trip("LALL", init.get("level", [])), "loss_of_inlet")
        add("LESS", "TEMPERATURE", "Depressurization (blowdown) to flare after ESD",
            "Low metal temperature; brittle fracture if below the design minimum",
            "Design minimum temperature %s C" % results_design_min(scenarios), "blowdown")
        add("MORE", "TEMPERATURE", "External fire", "Overpressure and wall weakening",
            guard("Flare/relief nozzles %s" % ", ".join(flare) if flare else "no flare nozzle traced", psv), None,
            "Run a fire-case blowdown with a wall model (not part of this screening)")
        jetting = _unique([i["tag"] for i in register["items"] if i.get("equipment") == tag
                           and i.get("role") == FINAL and not i.get("normal_flow", True)])
        add("OTHER THAN", "COMPOSITION", "Sand accumulation", "Reduced liquid volume, erosion",
            "Sand jetting/drain valves %s (normally closed)" % ", ".join(jetting) if jetting else "none read", None,
            "" if sg.get("drainConnections") else "No drain connection traced to the vessel")
        add("REVERSE", "FLOW", "Back-flow from %s when the vessel is depressurized" % ", ".join(
            _unique(sum(outlets.values(), []))), "Back-flow into the vessel", "Check valves not read from the drawing",
            None, "Confirm non-return valves on the outlet lines")
    return rows


def results_design_min(scenarios: Optional[dict[str, Any]]) -> str:
    if not scenarios:
        return "n/a"
    return str(scenarios.get("vessel", {}).get("designMinTemperature_C"))


def write_hazop(rows: list[dict[str, Any]], out_dir: str | Path) -> dict[str, str]:
    """Writes the worksheet as JSON, CSV and Markdown."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "hazop_worksheet.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    cols = ["node", "deviation", "cause", "consequence", "quantified", "verdict", "safeguards", "recommendation"]
    with open(out / "hazop_worksheet.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    md = ["# HAZOP preparation worksheet (draft)", "",
          "Causes come from the drawn topology, safeguards from the P&ID safeguard register and quantified "
          "consequences from NeqSim simulations. This is preparation for a chaired HAZOP, not its result.", "",
          "| Node | Deviation | Cause | Consequence | Quantified (NeqSim) | Safeguards (P&ID) | Recommendation |",
          "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        md.append("| %s |" % " | ".join(str(r[c]).replace("|", "/") for c in
                                         ("node", "deviation", "cause", "consequence", "quantified", "safeguards",
                                          "recommendation")))
    (out / "hazop_worksheet.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return {"json": "hazop_worksheet.json", "csv": "hazop_worksheet.csv", "markdown": "hazop_worksheet.md"}


def run_safety_study(records: dict[str, Any] | str | Path, out_dir: str | Path, fluid: dict[str, Any],
                     feed_flow: float, **kwargs: Any) -> dict[str, Any]:
    """Register, demand-case simulations and HAZOP draft in one call; writes everything to ``out_dir``."""
    if not isinstance(records, dict):
        records = json.loads(Path(records).read_text(encoding="utf-8"))
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    register = safety_register(records)
    (out / "safety_register.json").write_text(json.dumps(register, indent=1), encoding="utf-8")
    scenarios = run_safety_scenarios(records, fluid, feed_flow, out, register=register, **kwargs)
    rows = hazop_worksheet(records, register, scenarios)
    files = write_hazop(rows, out)
    summary = {"register": "safety_register.json", "scenarios": "safety_scenarios.json", "hazop": files,
               "counts": register["counts"], "gaps": register["gaps"], "passed": scenarios["passed"],
               "verdicts": {s["case"]: s.get("verdict") for s in scenarios["scenarios"]},
               "reviewStatus": "REVIEW_REQUIRED"}
    (out / "safety_study_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary
