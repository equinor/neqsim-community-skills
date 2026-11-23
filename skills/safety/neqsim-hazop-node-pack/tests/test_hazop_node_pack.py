"""Tests for the HAZOP node-pack generator on small synthetic drawings."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest
from hazop_node_pack.node_pack import (
    EXTRA_DEVIATION_SEEDS,
    build_node_pack,
    infer_equipment_types,
    list_rows_for_node,
    norm_tag,
    read_csv_rows,
    render_markup,
    seed_deviations,
    select_items,
    select_pipes,
    sheet_from_connectivity,
    sheet_from_layout,
    unmatched_requests,
    write_node_pack,
)
from PIL import Image, ImageDraw

SHEET = "SYN-PID-001"
CANVAS = (800, 600)
IMAGE = (1600, 1200)  # rendered at twice the canvas size


def _node(key, kind, x, y, tag=None, w=40, h=40):
    return {"id": key, "kind": kind, "tag": tag, "bbox": [x, y, w, h]}


def _edge(key, a, b, pts, fluid="gas"):
    return {"id": key, "from": a, "to": b, "points": pts, "fluid": fluid}


def _layout():
    nodes = [
        _node("B-IN", "boundary", 20, 280, None, 60, 40),
        _node("EV1", "esdv", 120, 280, "EV-9101*"),
        _node("J1", "junction", 200, 295, None, 10, 10),
        _node("J2", "junction", 260, 295, None, 10, 10),
        _node("CH1", "choke", 320, 280, "CH-9101"),
        _node("PT1", "instrument", 190, 200, "PT-9101"),
        _node("RCV", "pig_receiver", 420, 270, "PR-9101", 80, 60),
        _node("PSV1", "psv", 440, 160, "PSV-9101"),
        _node("B-OUT", "boundary", 700, 280, None, 60, 40),
        _node("PMP", "pump", 500, 450, "P-9201"),
    ]
    edges = [
        _edge("L1", "B-IN", "EV1", [[80, 300], [120, 300]]),
        _edge("L2", "EV1", "J1", [[160, 300], [200, 300]]),
        _edge("L3", "J1", "J2", [[210, 300], [260, 300]]),
        _edge("L4", "J2", "CH1", [[270, 300], [320, 300]]),
        _edge("L5", "J1", "PT1", [[205, 295], [205, 240]]),
        _edge("L6", "CH1", "RCV", [[360, 300], [420, 300]]),
        _edge("L7", "RCV", "B-OUT", [[500, 300], [700, 300]]),
        _edge("L8", "RCV", "PSV1", [[460, 270], [460, 200]]),
    ]
    return {
        "schema": "neqsim.pfd_layout.v1",
        "name": SHEET,
        "canvas": {"width": CANVAS[0], "height": CANVAS[1], "unit": "px"},
        "nodes": nodes,
        "edges": edges,
    }


def _png(path: Path, size=IMAGE) -> Path:
    image = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(image)
    draw.line([(40, 600), (1500, 600)], fill=(0, 0, 0), width=4)
    image.save(path)
    return path


@pytest.fixture()
def drawing(tmp_path):
    layout_path = tmp_path / f"{SHEET}.layout.json"
    layout_path.write_text(json.dumps(_layout()), encoding="utf-8")
    png = _png(tmp_path / f"{SHEET}.png")
    sheet = sheet_from_layout(layout_path, IMAGE, image_path=png)
    return sheet, png


VALVE_CSV = (
    "sheet,tag,type,status,line_numbers,description\n"
    f"{SHEET},GR-EV-9101,esdv,new,L-1,riser ESDV\n"
    f"{SHEET},GR-PT-9101,instrument,new,L-1,pressure transmitter\n"
    f"{SHEET},GR-PSV-9101,psv,new,L-2,receiver relief\n"
    "OTHER-SHEET,GR-EV-9101,esdv,new,L-9,same tag on another sheet\n"
)


def _modes(p_design=120.0):
    return [
        {
            "mode": "normal",
            "p_op_bara": 80,
            "t_op_c": 40,
            "p_design_bara": p_design,
            "t_design_c": 90,
            "source": "synthetic design basis",
            "status": "",
        }
    ]


def _node_def(**overrides):
    node = {
        "node_id": "N1",
        "name": "Receiver inlet",
        "design_intent": "Receive pigs and gas from the riser",
        "boundary": "From B-IN to the receiver inlet",
        "modes": _modes(),
        "drawings": [{"sheet": SHEET, "tags": ["GR-EV-9101", "CH-9101"]}],
    }
    node.update(overrides)
    return node


# ------------------------------------------------------------------ readers
def test_sheet_from_layout_scales_canvas_to_image(drawing):
    sheet, _ = drawing
    ev = sheet.items["EV1"]
    assert ev.tag == "EV-9101"  # proposal asterisk stripped
    assert ev.bbox == (240.0, 560.0, 320.0, 640.0)  # 2x scale
    assert ev.category == "valve"
    assert sheet.items["PT1"].category == "instrument"
    assert sheet.items["B-IN"].category == "boundary"
    assert sheet.items["B-IN"].tag == "B-IN"  # falls back to the layout key
    assert sheet.pipes[0].members == ("B-IN", "EV1")


def test_sheet_from_connectivity_converts_mm_anchors(tmp_path):
    data = {
        "sheet": "SYN-PID-002",
        "nodes": [
            {
                "id": "E1",
                "kind": "connector",
                "tag": "FL-1",
                "new": True,
                "anchor": [100, 100],
            },
            {
                "id": "V1",
                "kind": "ball_valve",
                "tag": "XV-1",
                "anchor": [150, 100],
                "desc": "x",
            },
            {"id": "NOANCHOR", "kind": "valve"},
        ],
        "edges": [{"from_": "E1", "to": "V1", "pipe": "P-1"}],
        "pipes": [
            {
                "name": "P-1",
                "line_no": '12"-L-1',
                "service": "prod",
                "points": [[100, 100], [150, 100]],
            }
        ],
    }
    path = tmp_path / "conn.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    sheet = sheet_from_connectivity(path, (840, 594), canvas_mm=(420.0, 297.0))
    assert "NOANCHOR" not in sheet.items
    e1 = sheet.items["E1"]
    cx, cy = (e1.bbox[0] + e1.bbox[2]) / 2, (e1.bbox[1] + e1.bbox[3]) / 2
    assert (cx, cy) == (200.0, (297 - 100) * 2.0)  # y axis flipped
    assert e1.new is True and sheet.items["V1"].new is None
    pipe = sheet.pipes[0]
    assert pipe.line_no == '12"-L-1' and set(pipe.members) == {"E1", "V1"}
    assert pipe.points[0] == (200.0, 394.0)
    flipped = sheet_from_connectivity(path, (840, 594), y_up=False)
    assert flipped.pipes[0].points[0] == (200.0, 200.0)


# ------------------------------------------------------------------ selection
def test_tag_normalisation_strips_asterisk_and_gr_prefix():
    assert norm_tag("GR-EV-9101*") == "EV-9101"
    assert norm_tag(" gr-PT-1 ") == "PT-1"
    assert norm_tag("EV-9101") == "EV-9101"


def test_select_by_tag_glob_key_and_gr_prefix(drawing):
    sheet, _ = drawing
    by_tag = {i.key for i in select_items(sheet, tags=["GR-EV-9101"])}
    assert by_tag == {"EV1"}
    by_glob = {i.key for i in select_items(sheet, tag_globs=["GR-P*-9101"])}
    assert by_glob == {"PT1", "PSV1", "RCV"}
    by_key = {i.key for i in select_items(sheet, keys=["B-IN", "NOPE"])}
    assert by_key == {"B-IN"}


def test_inline_junction_joins_selection_only_with_two_selected_neighbours(drawing):
    sheet, _ = drawing
    assert {i.key for i in select_items(sheet, tags=["EV-9101"])} == {"EV1"}
    two = {i.key for i in select_items(sheet, tags=["EV-9101", "PT-9101"])}
    assert two == {"EV1", "PT1", "J1"}
    chain = {i.key for i in select_items(sheet, tags=["EV-9101", "PT-9101", "CH-9101"])}
    assert {"J1", "J2"} <= chain  # a chain of junctions is followed


def test_select_pipes_needs_two_selected_members_or_a_line_number(drawing):
    sheet, _ = drawing
    items = select_items(sheet, tags=["EV-9101", "PT-9101", "CH-9101"])
    pipes = {p.key for p in select_pipes(sheet, items)}
    assert pipes == {"L2", "L3", "L4", "L5"}  # L1 touches only EV1 of the selection
    sheet.pipes[0].line_no = "L-1"
    assert "L1" in {p.key for p in select_pipes(sheet, items, line_nos=["L-1"])}


def test_unmatched_requests_name_each_missing_selector(drawing):
    sheet, _ = drawing
    gaps = unmatched_requests(
        sheet,
        tags=["GR-EV-9101", "XV-0000"],
        keys=["EV1", "ZZ"],
        tag_globs=["GR-QQ-*", "PT-*"],
    )
    assert gaps == ["tag XV-0000", "key ZZ", "glob GR-QQ-*"]


# ------------------------------------------------------------------ list rows
def test_list_rows_follow_sheet_and_prefix_normalised_tags(tmp_path):
    path = tmp_path / "valves.csv"
    path.write_text("\ufeff" + VALVE_CSV, encoding="utf-8")
    rows = read_csv_rows(path)
    assert len(rows) == 4  # BOM tolerated
    picked = list_rows_for_node(rows, SHEET, ["EV-9101"], ["PSV-*"])
    assert sorted(r["tag"] for r in picked) == ["GR-EV-9101", "GR-PSV-9101"]
    assert all(r["sheet"] == SHEET for r in picked)
    assert read_csv_rows(tmp_path / "absent.csv") == []
    assert read_csv_rows(None) == []


# ------------------------------------------------------------------ seeds
@pytest.mark.parametrize(
    "equipment_type, expected",
    [
        ("tree", ("OTHER THAN", "CONTAINMENT")),
        ("annulus", ("AS WELL AS", "CONTAMINATION")),
        ("umbilical", ("OTHER THAN", "CONTROL SIGNAL")),
        ("pigreceiver", ("AS WELL AS", "LIQUID")),
        ("pig receiver", ("AS WELL AS", "LIQUID")),
        ("Pig-Receiver", ("AS WELL AS", "LIQUID")),
        ("hipps", ("NO", "CLOSURE")),
        ("riser", ("OTHER THAN", "LEAK")),
        ("manifold", ("REVERSE", "FLOW")),
        ("chemicalstorage", ("OTHER THAN", "FIRE")),
        ("chemical storage", ("OTHER THAN", "FIRE")),
        ("XMT", ("OTHER THAN", "CONTAINMENT")),
    ],
)
def test_new_equipment_types_seed_their_own_deviations(equipment_type, expected):
    pairs = seed_deviations([equipment_type])
    assert expected in pairs
    assert pairs != seed_deviations(["not a known type"])


def test_every_extra_seed_type_is_reachable_and_existing_seeds_still_work():
    for key, seeds in EXTRA_DEVIATION_SEEDS.items():
        assert seed_deviations([key]) == list(seeds)
    assert ("MORE", "LEVEL") in seed_deviations(["separator"])
    assert ("NO", "FLOW") in seed_deviations(["pump"])
    assert ("REVERSE", "FLOW") in seed_deviations(["dry gas seal"])  # base alias path
    assert seed_deviations(["heat exchanger"]) == [
        ("MORE", "TEMPERATURE"),
        ("LESS", "FLOW"),
    ]
    union = seed_deviations(["pump", "valve"])
    assert union == [("NO", "FLOW"), ("MORE", "PRESSURE"), ("MORE", "FLOW")]
    assert seed_deviations([]) == [("MORE", "PRESSURE"), ("MORE", "TEMPERATURE")]


def test_equipment_types_inferred_from_item_kinds(drawing):
    sheet, _ = drawing
    items = select_items(sheet, tags=["EV-9101", "CH-9101", "PR-9101", "P-9201"])
    assert infer_equipment_types(items) == ["valve", "pigreceiver", "pump"]


# ------------------------------------------------------------------ mark-up
def test_markup_png_written_and_source_is_untouched(drawing, tmp_path):
    sheet, png = drawing
    before = hashlib.sha256(png.read_bytes()).hexdigest()
    items = select_items(sheet, tags=["EV-9101", "PT-9101", "CH-9101"])
    pipes = select_pipes(sheet, items)
    out = tmp_path / "out" / "markup.png"
    info = render_markup(sheet, items, pipes, out, title="N1 Test node")
    assert out.is_file()
    assert hashlib.sha256(png.read_bytes()).hexdigest() == before
    marked = Image.open(out)
    assert marked.size == IMAGE
    assert marked.tobytes() != Image.open(png).convert("RGB").tobytes()
    x0, y0, x1, y1 = info["boundary_box_px"]
    assert 0 <= x0 < x1 <= IMAGE[0] and 0 <= y0 < y1 <= IMAGE[1]
    # the box encloses every selected item (pixel coordinates of the source image)
    for item in items:
        assert x0 <= item.bbox[0] and item.bbox[2] <= x1
        assert y0 <= item.bbox[1] and item.bbox[3] <= y1
    assert info["source_size_px"] == list(IMAGE)


def test_markup_box_is_clamped_to_the_image_and_refuses_to_overwrite_source(
    drawing, tmp_path
):
    sheet, png = drawing
    items = select_items(sheet, keys=["B-IN"])  # near the left edge
    info = render_markup(
        sheet, items, [], tmp_path / "edge.png", title="edge", crop=True
    )
    x0, y0, x1, y1 = info["boundary_box_px"]
    assert x0 >= 0 and y0 >= 0 and x1 <= IMAGE[0] and y1 <= IMAGE[1]
    assert info["output_size_px"][0] < IMAGE[0]  # cropped around the node
    with pytest.raises(ValueError, match="overwrite"):
        render_markup(sheet, items, [], png, title="x")


def test_markup_scales_when_the_image_size_differs_from_the_sheet(drawing, tmp_path):
    sheet, _ = drawing
    small = _png(tmp_path / "small.png", (800, 600))
    items = select_items(sheet, tags=["CH-9101"])
    info = render_markup(
        sheet, items, [], tmp_path / "s.png", title="s", image_path=small
    )
    x0, _y0, x1, y1 = info["boundary_box_px"]
    # CH1 spans canvas x 320..360, so 320..360 px on the 800 px image; the margin is 40 * 0.5
    assert (x0, x1) == (300.0, 380.0)
    assert y1 <= 600


# ------------------------------------------------------------------ pack
def test_build_node_pack_complete_node_has_no_gaps_and_writes_files(drawing, tmp_path):
    sheet, png = drawing
    before = png.read_bytes()
    valve_rows = [
        {"sheet": SHEET, "tag": "GR-EV-9101", "type": "esdv"},
        {"sheet": SHEET, "tag": "GR-CH-9101", "type": "choke"},
    ]
    line_rows = [
        {"sheet": SHEET, "line_number": "L-1", "service": "gas"},
        {"sheet": "OTHER", "line_number": "L-1", "service": "other"},
    ]
    sheet.pipes[1].line_no = "L-1"
    out = tmp_path / "pack"
    pack = build_node_pack(
        [
            _node_def(
                drawings=[
                    {"sheet": SHEET, "tags": ["GR-EV-9101", "CH-9101", "PT-9101"]}
                ]
            )
        ],
        {SHEET: sheet},
        valve_rows=valve_rows
        + [{"sheet": SHEET, "tag": "GR-PT-9101", "type": "instrument"}],
        line_rows=line_rows,
        out_dir=out,
    )
    node = pack["nodes"][0]
    assert pack["missing_evidence"] == []
    assert pack["readiness_label"] == "ready_for_hazop_facilitation"
    assert [g["status"] for g in pack["quality_gates"]] == ["pass", "pass"]
    assert {i["tag"] for i in node["items"]} == {
        "EV-9101",
        "CH-9101",
        "PT-9101",
        "J1",
        "J2",
    }
    assert len(node["list_rows"]) == 3
    assert [r["service"] for r in node["line_rows"]] == ["gas"]
    assert node["modes"][0]["status"] == "UNVERIFIED"  # empty status is never a pass
    assert node["equipment_types"] == ["valve"]
    markup = Path(node["drawings"][0]["markup"])
    assert markup.is_file() and markup.parent.name == "markups"
    x0, y0, x1, y1 = node["drawings"][0]["boundary_box_px"]
    assert 0 <= x0 < x1 <= IMAGE[0] and 0 <= y0 < y1 <= IMAGE[1]
    assert png.read_bytes() == before
    for name in (
        "nodes.csv",
        "node_items.csv",
        "node_modes.csv",
        "node_seeds.csv",
        "pack.json",
    ):
        assert (out / name).is_file(), name
    assert (
        (out / "README.md").read_text(encoding="utf-8").startswith("# HAZOP node pack")
    )
    stored = json.loads((out / "pack.json").read_text(encoding="utf-8"))
    assert stored["schema"] == "hazop_node_pack.v1"
    with open(out / "node_seeds.csv", encoding="utf-8-sig", newline="") as handle:
        seeds = list(csv.DictReader(handle))
    assert {"guide_word", "parameter", "hint"} <= set(seeds[0])
    assert seeds[0]["node_id"] == "N1"


def test_node_without_drawing_selection_is_reported_not_passed(drawing, tmp_path):
    sheet, _ = drawing
    nodes = [
        _node_def(),
        _node_def(
            node_id="N2",
            name="Empty node",
            design_intent="",
            modes=[],
            drawings=[{"sheet": SHEET, "tags": ["XX-0000"]}],
        ),
        _node_def(
            node_id="N3", drawings=[{"sheet": "NOT-LOADED", "tags": ["EV-9101"]}]
        ),
        _node_def(node_id="N4", drawings=[]),
    ]
    out = tmp_path / "gaps"
    pack = build_node_pack(nodes, {SHEET: sheet}, out_dir=out)
    gaps = pack["missing_evidence"]
    assert "N2: no item selected on SYN-PID-001" in gaps
    assert "N2: requested tag XX-0000 not found on SYN-PID-001" in gaps
    assert "N2: no drawing item selected" in gaps
    assert "N2: design intent missing" in gaps
    assert "N2: no design pressure per mode" in gaps
    assert "N2: no operating mode defined" in gaps
    assert "N3: drawing NOT-LOADED not loaded" in gaps
    assert "N4: no drawing item selected" in gaps
    assert not any(g.startswith("N1:") for g in gaps)
    assert pack["readiness_label"] == "orientation_only_until_missing_evidence_closed"
    by_id = {n["node_id"]: n for n in pack["nodes"]}
    assert by_id["N2"]["drawings"][0]["markup"] == ""
    assert not (out / "markups" / "N2_SYN-PID-001.png").exists()
    statuses = {g["name"]: g["status"] for g in pack["quality_gates"]}
    assert statuses == {
        "all_nodes_have_drawing_and_items": "missing",
        "all_nodes_have_design_conditions": "missing",
    }
    with open(out / "nodes.csv", encoding="utf-8-sig", newline="") as handle:
        readiness = {r["node_id"]: r["readiness"] for r in csv.DictReader(handle)}
    assert readiness == {"N1": "complete", "N2": "gaps", "N3": "gaps", "N4": "gaps"}


def test_design_pressure_must_be_a_positive_number(drawing):
    sheet, _ = drawing
    for bad in (0, "", None, "tbd"):
        pack = build_node_pack(
            [_node_def(modes=_modes(bad))], {SHEET: sheet}, render=False
        )
        assert "N1: no design pressure per mode" in pack["missing_evidence"], bad
    ok = build_node_pack(
        [_node_def(modes=_modes("345 (assumed)"))], {SHEET: sheet}, render=False
    )
    assert "N1: no design pressure per mode" not in ok["missing_evidence"]


def test_missing_list_rows_unknown_types_and_missing_image_are_gaps(drawing, tmp_path):
    sheet, _ = drawing
    pack = build_node_pack(
        [_node_def(equipment_types=["flux capacitor", "tree"])],
        {SHEET: sheet},
        valve_rows=[{"sheet": SHEET, "tag": "GR-EV-9101"}],
        out_dir=tmp_path / "p",
    )
    gaps = pack["missing_evidence"]
    assert "N1: 1 valve/instrument items without a list row (CH-9101)" in gaps
    assert (
        "N1: equipment type not recognised, default seed used: flux capacitor" in gaps
    )
    sheet.image_path = str(tmp_path / "gone.png")
    again = build_node_pack([_node_def()], {SHEET: sheet}, out_dir=tmp_path / "q")
    assert (
        f"N1: no drawing image for {SHEET}, no mark-up made"
        in again["missing_evidence"]
    )


def test_empty_and_malformed_definitions(drawing):
    sheet, _ = drawing
    empty = build_node_pack([], {SHEET: sheet})
    assert empty["missing_evidence"] == ["no node defined"]
    assert empty["readiness_label"] == "orientation_only_until_missing_evidence_closed"
    assert {g["status"] for g in empty["quality_gates"]} == {"missing"}
    with pytest.raises(ValueError, match="node_id"):
        build_node_pack([{"name": "x"}], {SHEET: sheet})
    with pytest.raises(ValueError, match="sheet"):
        build_node_pack([_node_def(drawings=[{"tags": ["EV-9101"]}])], {SHEET: sheet})
    twice = build_node_pack([_node_def(), _node_def()], {SHEET: sheet}, render=False)
    assert "N1: node id defined more than once" in twice["missing_evidence"]


def test_new_node_types_flow_through_the_pack(drawing):
    sheet, _ = drawing
    pack = build_node_pack(
        [
            _node_def(
                node_id="N7",
                equipment_types=["pig receiver", "riser"],
                drawings=[{"sheet": SHEET, "tags": ["PR-9101", "PSV-9101"]}],
            )
        ],
        {SHEET: sheet},
        render=False,
    )
    node = pack["nodes"][0]
    pairs = {(s["guideWord"], s["parameter"]) for s in node["seed_deviations"]}
    assert ("AS WELL AS", "LIQUID") in pairs and ("OTHER THAN", "LEAK") in pairs
    assert node["unrecognised_equipment_types"] == []
    assert next(s for s in node["seed_deviations"] if s["parameter"] == "PRESSURE")[
        "hint"
    ]


def test_write_node_pack_returns_every_file(drawing, tmp_path):
    sheet, _ = drawing
    pack = build_node_pack([_node_def()], {SHEET: sheet}, render=False)
    files = write_node_pack(pack, tmp_path / "w")
    assert set(files) == {
        "nodes.csv",
        "node_items.csv",
        "node_modes.csv",
        "node_seeds.csv",
        "pack.json",
        "README.md",
    }
    assert all(Path(p).is_file() for p in files.values())


def test_worked_example_from_the_skill_documentation(tmp_path):
    import importlib.util

    path = (
        Path(__file__).resolve().parents[1] / "examples" / "hazop_node_pack_example.py"
    )
    spec = importlib.util.spec_from_file_location("hazop_node_pack_example", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pack = module.build_example(tmp_path)
    node = pack["nodes"][0]
    assert pack["missing_evidence"] == []
    assert {i["tag"] for i in node["items"]} == {
        "EV-9101",
        "PT-9101",
        "PSV-9101",
        "PR-9101",
        "J1",
    }
    assert node["equipment_types"] == ["valve", "pigreceiver"]
    assert Path(node["drawings"][0]["markup"]).is_file()
    assert (tmp_path / "pack" / "pack.json").is_file()


def test_project_tag_prefixes_are_configurable(drawing, monkeypatch):
    from hazop_node_pack import node_pack

    sheet, _ = drawing
    assert {i.key for i in select_items(sheet, tags=["GR-EV-9101"])} == {"EV1"}
    monkeypatch.setattr(node_pack, "TAG_PREFIXES", ())
    assert select_items(sheet, tags=["GR-EV-9101"]) == []
    assert {i.key for i in select_items(sheet, tags=["EV-9101"])} == {"EV1"}
    monkeypatch.setattr(node_pack, "TAG_PREFIXES", ("PRJ-",))
    assert {i.key for i in select_items(sheet, tags=["prj-EV-9101"])} == {"EV1"}
    assert node_pack.norm_tag("GR-EV-9101", prefixes=("GR-",)) == "EV-9101"
