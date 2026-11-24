"""End-to-end: P&ID PDF -> drawing records -> DEXPI -> NeqSim simulation -> regenerated P&IDs.

Needs Java NeqSim with ``neqsim.process.processmodel.dexpi.PidDrawingRecordsDexpiWriter`` on the JVM class
path (pass ``jar=`` or set ``NEQSIM_JAR``). The PDF is read only; every output goes to ``out_dir``.
"""

from __future__ import annotations

import json
import math
import os
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .config import ExtractionConfig
from .extract import extract_pid_records
from .overlay import render_overlay

NS = "http://sandbox.dexpi.org/xml"
_Q = "{%s}" % NS


def start_jvm(jar: Optional[str | Path] = None):
    """Starts the JVM with the given NeqSim jar (or NEQSIM_JAR) and returns ``jpype.JClass``."""
    import jpype

    if not jpype.isJVMStarted():
        jar = jar or os.environ.get("NEQSIM_JAR")
        if jar:
            jpype.startJVM(classpath=[str(jar)])
        else:
            import neqsim  # noqa: F401  # the Python package starts the JVM with its bundled jar
    try:
        jpype.JClass("neqsim.process.processmodel.dexpi.PidDrawingRecordsDexpiWriter")
    except Exception as exc:  # pragma: no cover - depends on installed jar
        raise RuntimeError("The NeqSim jar on the class path has no PidDrawingRecordsDexpiWriter; pass jar= with a "
                           "NeqSim build that includes it") from exc
    return jpype.JClass


def make_fluid(J, spec: dict[str, Any]):
    """Creates a NeqSim fluid from ``{"eos", "components": [{name, moles, molarMass?, density?}], ...}``."""
    classes = {"srk": "neqsim.thermo.system.SystemSrkEos", "pr": "neqsim.thermo.system.SystemPrEos"}
    fluid = J(classes[spec.get("eos", "srk").lower()])(273.15 + 25.0, 10.0)
    for c in spec["components"]:
        if c.get("molarMass"):
            fluid.addTBPfraction(c["name"], float(c["moles"]), float(c["molarMass"]), float(c["density"]))
        else:
            fluid.addComponent(c["name"], float(c["moles"]))
    fluid.setMixingRule(spec.get("mixingRule", "classic"))
    fluid.setMultiPhaseCheck(bool(spec.get("multiPhaseCheck", True)))
    if spec.get("volumeCorrection", True):
        fluid.useVolumeCorrection(True)
    return fluid


def _stream_state(stream) -> dict[str, float]:
    state = {"pressure_bara": float(stream.getPressure("bara")), "temperature_C": float(stream.getTemperature("C")),
             "massFlow_kg_h": float(stream.getFlowRate("kg/hr"))}
    try:
        stream.getFluid().initProperties()
        state["density_kg_m3"] = float(stream.getFluid().getDensity("kg/m3"))
    except Exception:  # pragma: no cover - zero-flow streams
        pass
    return state


def _role_streams(unit) -> dict[str, Any]:
    name = unit.getClass().getSimpleName()
    streams: dict[str, Any] = {}
    if name == "ThreePhaseSeparator":
        streams = {"GasOutlet": unit.getGasOutStream(), "OilOutlet": unit.getOilOutStream(),
                   "WaterOutlet": unit.getWaterOutStream()}
    elif name in ("Separator", "GasScrubber", "GasScrubberSimple", "TwoPhaseSeparator"):
        streams = {"GasOutlet": unit.getGasOutStream(), "LiquidOutlet": unit.getLiquidOutStream()}
    else:
        try:
            streams = {"Outlet": unit.getOutletStream()}
        except Exception:
            streams = {}
    return streams


def run_pipeline(pdf_path: str | Path | list, out_dir: str | Path, fluid: dict[str, Any], feed_flow: float,
                 feed_flow_unit: str = "kg/hr", feed_pressure: Optional[float] = None,
                 feed_pressure_unit: str = "barg", feed_temperature: Optional[float] = None,
                 page: int = 0, jar: Optional[str | Path] = None, config: Optional[ExtractionConfig] = None,
                 dpi: int = 60, boundary_feeds: Optional[dict[str, dict[str, Any]]] = None,
                 corrections: Optional[dict[str, Any] | str | Path] = None, raster_dpi: int = 300) -> dict[str, Any]:
    """Runs sheet(s) -> records -> DEXPI -> simulation -> regenerated P&IDs and checks the round trip.

    ``pdf_path`` may be one sheet or a list of sheets (vector PDF, scanned PDF or image); several sheets are
    stitched through matching off-page connectors. Feed pressure and temperature default to the operating
    values in the equipment data block of the first separator; fluid and feed rate must be given.

    ``boundary_feeds`` maps an inbound connector (tag, label text or node id) to its own feed:
    ``{"flow": 5000, "flow_unit": "kg/hr", "fluid": <fluid spec or omitted>, "pressure": 16,
    "pressure_unit": "barg", "temperature": 55}``. ``corrections`` is a reviewer corrections file
    (see :mod:`pid_pdf_to_dexpi.review`) applied before DEXPI is written.
    """
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = [Path(p) for p in (pdf_path if isinstance(pdf_path, (list, tuple)) else [pdf_path])]
    summary: dict[str, Any] = {"schemaVersion": "neqsim_pid_pdf_pipeline.v1", "pdf": [p.name for p in paths],
                               "files": {}, "checks": {}, "assumptions": [], "warnings": []}

    sheets = []
    for k, p in enumerate(paths):
        rec = extract_pid_records(p, page, config, dpi=raster_dpi)
        sheets.append(rec)
        suffix = "" if len(paths) == 1 else "_sheet%d" % (k + 1)
        render_overlay(p, rec, out / ("extraction_overlay%s.png" % suffix), dpi=dpi, page_index=page)
        summary["files"]["overlay" + suffix] = "extraction_overlay%s.png" % suffix
    if len(sheets) == 1:
        records = sheets[0]
    else:
        from .stitch import stitch_records

        records = stitch_records(sheets)
        summary["links"] = records["links"]
    if corrections is not None:
        from .review import apply_corrections

        records = apply_corrections(records, corrections)
    from .review import review_items, write_review_sheet

    write_review_sheet(records, out / "review_checklist.md")
    summary["review"] = {"status": records.get("reviewStatus"), "items": len(review_items(records)),
                         "highSeverity": len([i for i in review_items(records) if i["severity"] == "high"])}
    rec_file = out / "drawing_records.json"
    rec_file.write_text(json.dumps(records, indent=1), encoding="utf-8")
    summary["files"].update({"records": rec_file.name, "reviewChecklist": "review_checklist.md"})
    summary["extraction"] = records.get("counts", {})
    summary["warnings"].extend(records["warnings"])
    J = start_jvm(jar)
    File = J("java.io.File")
    writer = J("neqsim.process.processmodel.dexpi.PidDrawingRecordsDexpiWriter")
    renderer = J("neqsim.process.processmodel.dexpi.DexpiXmlSvgRenderer")
    extracted = out / "extracted.dexpi.xml"
    write_result = writer.write(File(str(rec_file)), File(str(extracted)))
    summary["dexpiWrite"] = json.loads(str(write_result.toJson()))
    if records.get("review", {}).get("corrections"):
        summary["revisionMarks"] = add_revision_marks(extracted, extracted, records)
    renderer.render(File(str(extracted)), File(str(out / "regenerated_pid.svg")))
    _svg_to_png(out / "regenerated_pid.svg", out / "regenerated_pid.png", dpi)
    summary["files"].update({"dexpi": extracted.name, "regeneratedPid": "regenerated_pid.svg"})

    summary["checks"]["dexpiRoundTrip"] = verify_dexpi_topology(records, extracted)

    separators = [n for n in records["nodes"] if n["kind"] in ("separator", "vessel")]
    data = separators[0].get("attributes", {}) if separators else {}
    if feed_pressure is None:
        op = data.get("operatingPressure")
        if not op:
            raise ValueError("No feed pressure given and none found in an equipment data block")
        feed_pressure, feed_pressure_unit = op["value"], op["unit"]
        summary["assumptions"].append("Feed pressure %.2f %s taken from the %s data block on the sheet."
                                      % (feed_pressure, feed_pressure_unit, separators[0]["tag"]))
    if feed_temperature is None:
        ot = data.get("operatingTemperature")
        if not ot:
            raise ValueError("No feed temperature given and none found in an equipment data block")
        feed_temperature = ot["value"]
        summary["assumptions"].append("Feed temperature %.1f C taken from the %s data block on the sheet."
                                      % (feed_temperature, separators[0]["tag"]))
    summary["assumptions"].append("Fluid composition and feed rate (%.6g %s) are user inputs; a P&ID carries "
                                  "neither." % (feed_flow, feed_flow_unit))

    builder = J("neqsim.process.processmodel.dexpi.DexpiSimulationBuilder")(File(str(extracted)))
    builder.setFluidTemplate(make_fluid(J, fluid)).setFeedPressure(float(feed_pressure), feed_pressure_unit) \
        .setFeedTemperature(float(feed_temperature), "C").setFeedFlowRate(float(feed_flow), feed_flow_unit)
    feeds = resolve_boundary_feeds(records, boundary_feeds or {})
    for node_id, spec in feeds.items():
        builder.addBoundaryFeed(node_id, make_fluid(J, spec["fluid"]) if spec.get("fluid") else None,
                                float(spec["flow"]), spec.get("flow_unit", "kg/hr"),
                                float(spec.get("pressure", feed_pressure)),
                                spec.get("pressure_unit", feed_pressure_unit if "pressure" not in spec else "barg"),
                                float(spec.get("temperature", feed_temperature)), "C")
        summary["assumptions"].append("Boundary feed at %s: %.6g %s (user input)." % (
            spec["label"], float(spec["flow"]), spec.get("flow_unit", "kg/hr")))
    process = builder.build()
    process.run()
    diagnostics = [{"severity": str(d.getSeverity()), "code": str(d.getCode()), "element": str(d.getElementId()),
                    "message": str(d.getMessage())} for d in builder.getDiagnostics()]
    summary["simulation"] = _simulation_results(process, records, feeds)
    summary["simulation"]["diagnostics"] = diagnostics
    summary["checks"]["simulation"] = _simulation_checks(process, records, diagnostics)

    annotated = out / "simulated.dexpi.xml"
    annotate_results(extracted, annotated, records, summary["simulation"])
    renderer.render(File(str(annotated)), File(str(out / "regenerated_pid_with_results.svg")))
    _svg_to_png(out / "regenerated_pid_with_results.svg", out / "regenerated_pid_with_results.png", dpi)
    summary["files"].update({"simulatedDexpi": annotated.name,
                             "regeneratedPidWithResults": "regenerated_pid_with_results.svg"})

    flowsheet = out / "simulated_flowsheet.dexpi201.xml"
    plant = J("neqsim.process.processmodel.dexpi.Dexpi20PlantExportMetadata$PlantProperty")
    metadata = J("neqsim.process.processmodel.dexpi.Dexpi20PlantExportMetadata").builder(
        datetime.now(timezone.utc).isoformat(timespec="seconds"), "NeqSim pid_pdf_to_dexpi", "NeqSim",
        "1.0").plantProperty(plant.PLANT_AREA_IDENTIFICATION_CODE,
                             records["source"].get("drawingNumber") or paths[0].stem).build()
    report = J("neqsim.process.processmodel.dexpi.Dexpi201XmlWriter").writeAndAssess(process, File(str(flowsheet)),
                                                                                     metadata)
    summary["files"]["simulatedFlowsheetDexpi201"] = flowsheet.name
    summary["checks"]["dexpi201Conformance"] = {"conformant": bool(report.isSchemaAndProfileConformant()),
                                               "errors": [str(e) for e in report.getErrors()],
                                               "warnings": [str(w) for w in report.getWarnings()][:20]}
    checks = summary["checks"]
    summary["passed"] = bool(checks["dexpiRoundTrip"]["passed"] and checks["simulation"]["passed"])
    summary["reviewStatus"] = records.get("reviewStatus", "REVIEW_REQUIRED")
    (out / "pipeline_summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    return summary


def resolve_boundary_feeds(records: dict[str, Any], feeds: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Maps boundary-feed references (node id, connector tag or label text) to inbound connector node ids."""
    connectors = [n for n in records["nodes"] if n["kind"] == "off_page_connector" and n["direction"] == "in"]
    out: dict[str, dict[str, Any]] = {}
    for ref, spec in feeds.items():
        exact = [n for n in connectors if ref in (n["node_id"], n["tag"], n.get("label"))]
        partial = [n for n in connectors if ref.upper() in (n.get("label", "") + " " + n["tag"]).upper()]
        match = exact if len(exact) == 1 else partial if not exact and len(partial) == 1 else []
        if not match:
            raise ValueError("Boundary feed %r matches %d inbound connectors; use a node id or a unique label"
                             % (ref, len(exact) or len(partial)))
        node = match[0]
        out[node["node_id"]] = dict(spec, label=node.get("label") or node["tag"])
    return out


def _simulation_results(process, records, feeds: Optional[dict[str, dict[str, Any]]] = None) -> dict[str, Any]:
    units = []
    for unit in process.getUnitOperations():
        units.append({"name": str(unit.getName()), "type": str(unit.getClass().getSimpleName())})
    equipment = {}
    for node in records["nodes"]:
        if node["kind"] in ("off_page_connector", "tee"):
            continue
        unit = process.getUnit(node["tag"])
        if unit is None:
            continue
        roles = {}
        for role, stream in _role_streams(unit).items():
            roles[role] = _stream_state(stream)
        inlets = list(unit.getInletStreams())
        if inlets:
            roles["Inlet"] = _stream_state(inlets[0])
        equipment[node["tag"]] = {"type": str(unit.getClass().getSimpleName()), "streams": roles}
    feed = process.getUnit("DEXPI-Feed")
    boundary = {}
    for node_id, spec in (feeds or {}).items():
        unit = process.getUnit(spec["label"])
        if unit is not None:
            boundary[node_id] = _stream_state(unit)
    return {"units": units, "equipment": equipment, "feed": _stream_state(feed) if feed is not None else {},
            "boundaryFeeds": boundary}


def _simulation_checks(process, records, diagnostics) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    nodes = {n["node_id"]: n for n in records["nodes"]}
    expected = {n["tag"]: n["component_class"] for n in records["nodes"]
                if n["kind"] not in ("off_page_connector", "tee")}
    built = {}
    for tag in expected:
        unit = process.getUnit(tag)
        built[tag] = str(unit.getClass().getSimpleName()) if unit is not None else None
    checks["equipmentBuilt"] = built
    checks["equipmentClassMatches"] = all(
        built[t] is not None and (expected[t] in built[t] or built[t] in expected[t]) for t in expected)
    feed = process.getUnit("DEXPI-Feed")
    balances = {}
    for tag in expected:
        unit = process.getUnit(tag)
        if unit is None:
            continue
        inlet = sum(float(s.getFlowRate("kg/hr")) for s in unit.getInletStreams())
        outlet = sum(float(s.getFlowRate("kg/hr")) for s in unit.getOutletStreams())
        balances[tag] = {"in_kg_h": inlet, "out_kg_h": outlet,
                         "relativeError": abs(outlet - inlet) / inlet if inlet else None}
    checks["massBalance"] = balances
    worst = max((b["relativeError"] for b in balances.values() if b["relativeError"] is not None), default=None)
    checks["massBalanceRelativeError"] = worst
    no_flow_runs = sum(1 for e in records["edges"] if not e["normal_flow"])
    excluded = sum(1 for d in diagnostics if d["code"] == "DEXPI_BUILD_NO_FLOW_BRANCH_EXCLUDED"
                   and d["element"].startswith("Segment-"))
    checks["noFlowRunsExcluded"] = {"records": no_flow_runs, "builder": excluded}
    feeds = [n for n in nodes.values() if n["kind"] == "off_page_connector" and n["direction"] == "in"
             and n.get("service") == "process"]
    checks["processInletsOnSheet"] = [n["label"] or n["tag"] for n in feeds]
    checks["passed"] = bool(checks["equipmentClassMatches"] and checks["massBalanceRelativeError"] is not None
                            and checks["massBalanceRelativeError"] < 1e-3 and excluded == no_flow_runs)
    return checks


def verify_dexpi_topology(records: dict[str, Any], dexpi_file: str | Path) -> dict[str, Any]:
    """Re-reads the written DEXPI independently and compares pipe runs and nozzle roles with the records."""
    root = ET.parse(str(dexpi_file)).getroot()
    equipment = {n["node_id"] for n in records["nodes"] if n["kind"] not in ("off_page_connector", "tee")}
    owner: dict[str, str] = {}
    roles: dict[str, str] = {}
    for el in root.iter():
        tag = el.tag.replace(_Q, "")
        if tag in ("Equipment", "PipeOffPageConnector", "PipingComponent"):
            owner[el.get("ID")] = el.get("ID")
            for nz in el.iter(_Q + "Nozzle"):
                owner[nz.get("ID")] = el.get("ID")
                for ga in nz.iter(_Q + "GenericAttribute"):
                    if ga.get("Name") == "PortRole":
                        roles[nz.get("ID")] = ga.get("Value")
    valves = {el.get("ID") for el in root.iter(_Q + "PipingComponent") if el.get("ComponentClass") != "PipeTee"}
    runs = set()
    for seg in root.iter(_Q + "PipingNetworkSegment"):
        conns = [(c.get("FromID"), c.get("ToID")) for c in seg.findall(_Q + "Connection")]
        if not conns:
            continue
        chain_ok = all(owner.get(conns[k][1]) == owner.get(conns[k + 1][0]) and owner.get(conns[k][1]) in valves
                       for k in range(len(conns) - 1))
        normal = "true"
        for ga in seg.iter(_Q + "GenericAttribute"):
            if ga.get("Name") == "NormalFlow":
                normal = ga.get("Value")
        runs.add((_end(conns[0][0], owner, equipment), _end(conns[-1][1], owner, equipment), normal == "true",
                  chain_ok))
    expected = {(e["from_port"] if e["from_node"] in equipment and e["from_port"] else e["from_node"],
                 e["to_port"] if e["to_node"] in equipment and e["to_port"] else e["to_node"], e["normal_flow"], True)
                for e in records["edges"]}
    port_roles = {p["port_id"]: p["role"] for n in records["nodes"] for p in n.get("ports", []) if p.get("role")}
    role_mismatch = {k: (v, roles.get(k)) for k, v in port_roles.items() if roles.get(k) != v}
    missing = sorted(map(str, expected - runs))
    extra = sorted(map(str, runs - expected))
    return {"pipeRunsRecords": len(expected), "pipeRunsDexpi": len(runs), "missing": missing, "extra": extra,
            "nozzleRoleMismatches": role_mismatch,
            "passed": not missing and not extra and not role_mismatch}


def _end(dexpi_id: str, owner: dict[str, str], equipment: set[str]) -> str:
    """Equipment ends compare at nozzle level; connectors, tees and valves at item level."""
    item = owner.get(dexpi_id, "")
    return dexpi_id if item in equipment else item


def annotate_results(src: str | Path, dst: str | Path, records: dict[str, Any], simulation: dict[str, Any]) -> int:
    """Adds simulated stream conditions to every normal-flow pipe run of the DEXPI file and labels them."""
    ET.register_namespace("", NS)
    tree = ET.parse(str(src))
    root = tree.getroot()
    nodes = {n["node_id"]: n for n in records["nodes"]}
    incoming: dict[str, list[dict[str, Any]]] = {}
    for e in records["edges"]:
        incoming.setdefault(e["to_node"], []).append(e)
    ports = {p["port_id"]: p for n in records["nodes"] for p in n.get("ports", [])}

    def source_state(edge: dict[str, Any], depth: int = 0) -> Optional[dict[str, float]]:
        target = nodes[edge["to_node"]]
        if target["kind"] not in ("off_page_connector", "tee") and \
                ports.get(edge["to_port"], {}).get("role") == "Inlet":
            return simulation.get("equipment", {}).get(target["tag"], {}).get("streams", {}).get("Inlet")
        node = nodes[edge["from_node"]]
        if node["kind"] == "off_page_connector":
            if node["node_id"] in simulation.get("boundaryFeeds", {}):
                return simulation["boundaryFeeds"][node["node_id"]]
            if not incoming.get(node["node_id"]):
                return None  # side-stream rates entering the sheet are not known from the drawing
        if node["kind"] in ("tee", "off_page_connector"):
            if depth > 50:
                return None
            for e in incoming.get(node["node_id"], []):
                if e["normal_flow"]:
                    state = source_state(e, depth + 1)
                    if state:
                        return state
            return None
        role = ports.get(edge["from_port"], {}).get("role", "")
        streams = simulation.get("equipment", {}).get(node["tag"], {}).get("streams", {})
        return streams.get(role) or (streams.get("LiquidOutlet") if role == "OilOutlet" else None)

    segments = {seg.get("ID"): seg for seg in root.iter(_Q + "PipingNetworkSegment")}
    count = 0
    for e in records["edges"]:
        if not e["normal_flow"]:
            continue
        state = source_state(e)
        seg = segments.get("Segment-" + e["edge_id"])
        if not state or seg is None:
            continue
        attrs = ET.SubElement(seg, _Q + "GenericAttributes", {"Set": "NeqSimSimulationResults"})
        for name, value, unit in (("OperatingPressureValue", state["pressure_bara"], "bara"),
                                  ("OperatingTemperatureValue", state["temperature_C"], "C"),
                                  ("OperatingFlowValue", state["massFlow_kg_h"], "kg/h")):
            ET.SubElement(attrs, _Q + "GenericAttribute", {"Name": name, "Value": "%.6g" % value, "Unit": unit,
                                                            "Format": "double"})
        if not e.get("path"):
            count += 1
            continue
        x, y = _label_anchor(e["path"], records["source"]["pageHeight"])
        node = nodes[e["from_node"]]
        role = ports.get(e["from_port"], {}).get("role", "")
        shared = node["kind"] not in ("off_page_connector", "tee") and role and \
            sum(1 for p in node.get("ports", []) if p.get("role") == role) > 1
        text = ET.SubElement(seg, _Q + "Text", {"String": "%.1f bara  %.0f C  %.1f t/h%s" % (
            state["pressure_bara"], state["temperature_C"], state["massFlow_kg_h"] / 1000.0,
            " (total, all %s nozzles)" % role if shared else ""), "Font": "Arial",
            "Height": "2.6", "Width": "0", "Justification": "LeftBottom"})
        ET.SubElement(text, _Q + "Presentation", {"R": "0", "G": "0.2", "B": "0.8"})
        pos = ET.SubElement(text, _Q + "Position")
        ET.SubElement(pos, _Q + "Location", {"X": "%.3f" % x, "Y": "%.3f" % (y - 4.0), "Z": "0"})
        ET.SubElement(pos, _Q + "Axis", {"X": "0", "Y": "0", "Z": "1"})
        ET.SubElement(pos, _Q + "Reference", {"X": "1", "Y": "0", "Z": "0"})
        count += 1
    tree.write(str(dst), xml_declaration=True, encoding="utf-8")
    return count


def add_revision_marks(src: str | Path, dst: str | Path, records: dict[str, Any]) -> int:
    """Draws a revision cloud and numbered triangle at every reviewer correction, plus a revision table, so the
    regenerated P&ID shows what was changed from the extracted drawing. Returns the number of marks."""
    review = records.get("review") or {}
    marks = [c for c in review.get("corrections", []) if c.get("at")]
    ET.register_namespace("", NS)
    tree = ET.parse(str(src))
    root = tree.getroot()
    k = 25.4 / 72.0
    height = float(records["source"]["pageHeight"])
    red = {"R": "0.85", "G": "0", "B": "0"}

    def text(parent, string, x, y, size=3.0, just="LeftBottom"):
        t = ET.SubElement(parent, _Q + "Text", {"String": string, "Font": "Arial", "Height": "%.1f" % size,
                                                "Width": "0", "Justification": just})
        ET.SubElement(t, _Q + "Presentation", red)
        pos = ET.SubElement(t, _Q + "Position")
        ET.SubElement(pos, _Q + "Location", {"X": "%.3f" % x, "Y": "%.3f" % y, "Z": "0"})
        ET.SubElement(pos, _Q + "Axis", {"X": "0", "Y": "0", "Z": "1"})
        ET.SubElement(pos, _Q + "Reference", {"X": "1", "Y": "0", "Z": "0"})

    for c in marks:
        x, y = c["at"][0] * k, (height - c["at"][1]) * k
        label = ET.SubElement(root, _Q + "Label", {"ID": "REV-%d" % c["revision"], "ComponentClass": "RevisionMark"})
        cloud = ET.SubElement(label, _Q + "PolyLine", {"NumPoints": "37"})
        ET.SubElement(cloud, _Q + "Presentation", dict(red, LineType="0", LineWeight="0.5"))
        for i in range(37):
            a = 2 * math.pi * i / 36
            r = 9.0 + 1.2 * math.sin(6 * a)  # scalloped outline
            ET.SubElement(cloud, _Q + "Coordinate", {"X": "%.3f" % (x + 1.3 * r * math.cos(a)),
                                                    "Y": "%.3f" % (y + r * math.sin(a)), "Z": "0"})
        tx, ty = x + 13.0, y + 9.0
        tri = ET.SubElement(label, _Q + "PolyLine", {"NumPoints": "4"})
        ET.SubElement(tri, _Q + "Presentation", dict(red, LineType="0", LineWeight="0.4"))
        for px, py in ((tx - 3.5, ty - 2.5), (tx + 3.5, ty - 2.5), (tx, ty + 3.8), (tx - 3.5, ty - 2.5)):
            ET.SubElement(tri, _Q + "Coordinate", {"X": "%.3f" % px, "Y": "%.3f" % py, "Z": "0"})
        text(label, str(c["revision"]), tx, ty - 2.0, 2.6, "CenterBottom")
    if marks:
        table = ET.SubElement(root, _Q + "Label", {"ID": "REV-TABLE", "ComponentClass": "RevisionTable"})
        x0, y0 = 10.0, 14.0 + 4.0 * len(marks)
        text(table, "Corrections by %s, %s (%s)" % (review.get("reviewer", ""), review.get("date", ""),
                                                   "approved" if review.get("approved") else "not yet approved"),
             x0, y0 + 4.0, 3.2)
        for i, c in enumerate(marks):
            text(table, "%d  %s %s  %s" % (c["revision"], c["op"], c["ref"], c.get("reason", "")), x0, y0 - 4.0 * i)
    tree.write(str(dst), xml_declaration=True, encoding="utf-8")
    return len(marks)


def _label_anchor(path: list[list[float]], page_height: float) -> tuple[float, float]:
    best, anchor = -1.0, path[0]
    for p, q in zip(path, path[1:]):
        length = abs(q[0] - p[0]) + abs(q[1] - p[1])
        if length > best and abs(q[1] - p[1]) < 1.0:
            best, anchor = length, [(p[0] + q[0]) / 2.0 - 40.0, p[1]]
    if best < 0:
        anchor = path[0]
    k = 25.4 / 72.0
    return anchor[0] * k, (page_height - anchor[1]) * k


def _svg_to_png(svg: Path, png: Path, dpi: int) -> None:
    try:
        import fitz

        doc = fitz.open(str(svg))
        pdf = fitz.open("pdf", doc.convert_to_pdf())
        pdf[0].get_pixmap(dpi=dpi).save(str(png))
    except Exception:  # pragma: no cover - optional rendering
        pass
