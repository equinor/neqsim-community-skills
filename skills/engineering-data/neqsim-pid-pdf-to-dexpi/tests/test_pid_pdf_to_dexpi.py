"""Tests for vector P&ID extraction on a small synthetic sheet (no PDF needed)."""

import pytest

from pid_pdf_to_dexpi.extract import Page, Word, extract_from_page
from pid_pdf_to_dexpi.geometry import LineGraph, Rect, Segment
from pid_pdf_to_dexpi.review import apply_corrections
from pid_pdf_to_dexpi.stitch import stitch_records


def _rect(x0, y0, x1, y1, width):
    return [Segment(x0, y0, x1, y0, width), Segment(x1, y0, x1, y1, width), Segment(x1, y1, x0, y1, width),
            Segment(x0, y1, x0, y0, width)]


def _connector(x0, y, tip_right, width=0.72):
    """Pentagon connector 120 x 16 pt; tip on the right or left."""
    x1 = x0 + 120
    if tip_right:
        return [Segment(x0, y - 8, x1 - 8, y - 8, width), Segment(x1 - 8, y - 8, x1, y, width),
                Segment(x1, y, x1 - 8, y + 8, width), Segment(x1 - 8, y + 8, x0, y + 8, width),
                Segment(x0, y + 8, x0, y - 8, width)]
    return [Segment(x0 + 8, y - 8, x1, y - 8, width), Segment(x1, y - 8, x1, y + 8, width),
            Segment(x1, y + 8, x0 + 8, y + 8, width), Segment(x0 + 8, y + 8, x0, y, width),
            Segment(x0, y, x0 + 8, y - 8, width)]


def _word(text, x, y, w=60):
    return Word(text, Rect(x, y, x + w, y + 8))


def _sheet():
    """A separator with an inlet that tees with a side stream, gas and water outlets and a valve gap."""
    segs = _rect(300, 300, 700, 420, 0.48)  # separator shell
    segs += _connector(20, 150, True) + _connector(20, 230, True)  # inlets (tip toward the line)
    segs += _connector(860, 200, True) + _connector(860, 500, True)  # outlets
    proc = 1.44
    segs += [Segment(140, 150, 340, 150, proc), Segment(340, 150, 340, 300, proc),  # inlet to N01
             Segment(140, 230, 340, 230, proc),  # side stream tees into the inlet line
             Segment(650, 300, 650, 200, proc), Segment(650, 200, 760, 200, proc),  # gas, gap at 760-772
             Segment(772, 200, 860, 200, proc),
             Segment(600, 420, 600, 500, proc), Segment(600, 500, 860, 500, proc)]  # water
    words = [_word("20VA001", 470, 350), _word("DEMO-P-XB-001-01", 30, 146), _word("DEMO-P-XB-002-01", 30, 226),
             _word("DEMO-P-XB-003-01", 870, 196), _word("DEMO-P-XB-004-01", 870, 496),
             _word("WELLSTREAM", 22, 128), _word("FROM", 85, 128, 20), _word("HEATERS", 108, 128, 30),
             _word("CONDENSATE", 22, 208), _word("FROM", 85, 208, 20),
             _word("GAS", 862, 178, 15), _word("TO", 880, 178, 10), _word("COMPRESSOR", 892, 178),
             _word("WATER", 862, 478, 25), _word("TO", 890, 478, 10), _word("TREATMENT", 902, 478),
             _word("N01", 345, 285, 12), _word("N02", 655, 285, 12), _word("N04", 605, 425, 12),
             _word("XV", 760, 170, 10), _word("0100", 758, 179, 14),
             _word("20L00001A-0600PG-BD100", 680, 190, 80)]
    segs += [Segment(760, 195, 772, 205, 0.48), Segment(760, 205, 772, 195, 0.48)]  # open valve bowtie in the gap
    fills = []
    return Page(1000, 700, words, segs, [], fills, {"file": "synthetic.pdf"})


def test_line_graph_bridges_collinear_gap_and_tee():
    g = LineGraph([Segment(0, 0, 50, 0), Segment(62, 0, 100, 0), Segment(30, 0, 30, 40)], gap_max=30)
    assert len(g.bridges) == 1 and round(g.bridges[0].length) == 12
    assert 2 in g.adjacency[0]  # tee: end of the branch touches the run interior


def test_extracts_separator_topology_with_roles_tee_and_valve():
    rec = extract_from_page(_sheet())
    nodes = {n["node_id"]: n for n in rec["nodes"]}
    sep = next(n for n in rec["nodes"] if n["kind"] == "separator")
    assert sep["tag"] == "20VA001"
    roles = {p["label"]: p["role"] for p in sep["ports"]}
    assert roles == {"N01": "Inlet", "N02": "GasOutlet", "N04": "WaterOutlet"}
    assert sep["component_class"] == "ThreePhaseSeparator"
    assert rec["counts"]["tees"] == 1
    tee = next(n["node_id"] for n in rec["nodes"] if n["kind"] == "tee")
    into_tee = sorted(nodes[e["from_node"]]["label"] for e in rec["edges"] if e["to_node"] == tee)
    assert into_tee == ["CONDENSATE FROM", "WELLSTREAM FROM HEATERS"]
    gas = next(e for e in rec["edges"] if nodes[e["to_node"]].get("label", "").startswith("GAS"))
    assert gas["line_number"] == "20L00001A-0600PG-BD100" and gas["fluid_code"] == "PG"
    assert [(i["tag"], i["component_class"], i["normal_position"]) for i in gas["inline_items"]] == [("XV-0100", "GateValve", "open")]
    assert all(e["normal_flow"] for e in rec["edges"])


def test_utility_connector_marks_branch_without_normal_flow():
    page = _sheet()
    page.words = [w if w.text != "TREATMENT" else _word("DRAIN", 902, 478) for w in page.words]
    rec = extract_from_page(page)
    nodes = {n["node_id"]: n for n in rec["nodes"]}
    drain = next(e for e in rec["edges"] if "DRAIN" in nodes[e["to_node"]].get("label", ""))
    assert drain["normal_flow"] is False


def test_filled_valve_is_normally_closed_and_flange_is_found():
    page = _sheet()
    page.segments = [s for s in page.segments if s.width != 0.48 or not (760 <= s.x0 <= 772 and 195 <= s.y0 <= 205)]
    page.fills = [Rect(760, 196, 766, 204), Rect(766, 196, 772, 204)]  # filled bowtie: two triangles on the axis
    page.fill_kinds = ["lll", "lll"]
    page.words.append(_word("NC", 760, 210, 10))
    # Flange in the water line: two short bars across an 8 pt gap.
    page.segments = [s for s in page.segments if not (s.y0 == 500 and s.y1 == 500)]
    page.segments += [Segment(600, 500, 700, 500, 1.44), Segment(708, 500, 860, 500, 1.44),
                      Segment(701, 495, 701, 505, 0.48), Segment(707, 495, 707, 505, 0.48)]
    rec = extract_from_page(page)
    nodes = {n["node_id"]: n for n in rec["nodes"]}
    gas = next(e for e in rec["edges"] if nodes[e["to_node"]].get("label", "").startswith("GAS"))
    valve = gas["inline_items"][0]
    assert (valve["normal_position"], valve.get("locking")) == ("closed", "NC")
    assert gas["normal_flow"] is False
    water = next(e for e in rec["edges"] if nodes[e["to_node"]].get("label", "").startswith("WATER"))
    assert [i["kind"] for i in water["inline_items"]] == ["flange"]


def _one_sheet(number, connector_tag, direction):
    """Hand-made records: one equipment item and one connector to another sheet."""
    eq = {"node_id": "EQ-1", "tag": "T-" + number, "kind": "vessel", "bbox": [0, 0, 10, 10], "ports": []}
    opc = {"node_id": "OPC-1", "tag": connector_tag, "kind": "off_page_connector", "direction": direction,
           "service": "process", "label": "OIL", "bbox": [50, 0, 60, 10]}
    a, b = ("EQ-1", "OPC-1") if direction == "out" else ("OPC-1", "EQ-1")
    edge = {"edge_id": "E-1", "from_node": a, "to_node": b, "normal_flow": True, "line_number": "L-100",
            "fluid_code": "PL", "path": [[10, 5], [50, 5]], "inline_items": []}
    return {"source": {"file": number + ".pdf", "drawingNumber": number, "pageWidth": 100, "pageHeight": 50},
            "nodes": [eq, opc], "edges": [edge], "instruments": [], "warnings": []}


def test_stitch_links_matching_connectors_of_two_sheets():
    out = stitch_records([_one_sheet("A-01", "B-01", "out"), _one_sheet("B-01", "A-01", "in")])
    assert out["counts"]["sheetLinks"] == 1
    link = next(e for e in out["edges"] if e.get("kind") == "sheet_link")
    assert (link["from_node"], link["to_node"], link["normal_flow"]) == ("S1-OPC-1", "S2-OPC-1", True)
    assert out["reviewStatus"] == "REVIEW_REQUIRED"


def test_corrections_need_a_reviewer_and_record_approval():
    rec = extract_from_page(_sheet())
    gas = next(e["edge_id"] for e in rec["edges"] if e["inline_items"])
    with pytest.raises(ValueError):
        apply_corrections(rec, {"corrections": []})
    out = apply_corrections(rec, {"reviewer": "A. Reviewer", "approved": True, "corrections": [
        {"op": "set_valve", "edge": gas, "index": 0, "normal_position": "closed", "reason": "checked"},
        {"op": "set_normal_flow", "edge": gas, "value": False}]})
    item = next(e for e in out["edges"] if e["edge_id"] == gas)["inline_items"][0]
    assert (item["normal_position"], item["position_source"]) == ("closed", "reviewer")
    assert out["reviewStatus"] == "APPROVED" and out["review"]["correctionCount"] == 2
