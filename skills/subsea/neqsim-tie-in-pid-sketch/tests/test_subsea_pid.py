import json

import pytest
from tie_in_pid_sketch import (
    CATEGORIES,
    PidSheet,
    considerations_register,
    register_summary,
    subsea_tie_in_considerations,
)


def _sheet():
    s = PidSheet("T-001", "Test", revision="A")
    s.add("tree", "XT-1", 140, 250, w=90, h=110, label="Tree")
    s.add("gate_valve", "MV-1", 280, 250)
    s.add("esdv", "XV-1", 380, 250)
    s.add("manifold", "MF-1", 560, 250, w=80, h=120, label="Manifold")
    s.chain(["XT-1", "MV-1", "XV-1", "MF-1"], "production")
    return s


def test_chain_connects_in_flow_order_and_counts_isolation():
    s = _sheet()
    assert s.isolation_count("XT-1", "MF-1") == 2
    assert s.isolation_count("XT-1", "MF-1", kinds=("esdv",)) == 1
    assert [p.a for p in s.pipes] == ["XT-1", "MV-1", "XV-1"]
    assert all(p.arrow for p in s.pipes)


def test_validate_reports_orphans_missing_kinds_and_isolation():
    s = _sheet()
    s.add("choke", "CH-1", 700, 600)
    findings = s.validate(
        required_kinds=["pig_receiver"], min_isolation={("XT-1", "MF-1"): 3}
    )
    assert any("CH-1" in f and "not connected" in f for f in findings)
    assert any("pig receiver" in f.lower() for f in findings)
    assert any("2 isolating valve" in f for f in findings)
    assert _sheet().validate(["tree"], {("XT-1", "MF-1"): 2}) == []


def test_duplicate_tag_unknown_kind_and_unknown_service_are_rejected():
    s = _sheet()
    with pytest.raises(ValueError):
        s.add("gate_valve", "MV-1", 10, 10)
    with pytest.raises(ValueError):
        s.add("teleporter", "X-1", 10, 10)
    with pytest.raises(ValueError):
        s.pipe("XT-1", "e", "MV-1", "w", service="lava")


def test_svg_and_layout_spec_are_consistent():
    s = _sheet()
    s.add("instrument", "PT-101", 380, 140, label="P")
    s.tap("PT-101", "XV-1", "s", "n")
    s.note("A note.")
    svg = s.to_svg()
    assert svg.startswith("<svg") and 'data-tag="XT-1"' in svg and "XV-1*" in svg
    spec = s.layout_spec()
    assert spec["schema"] == "neqsim.pfd_layout.v1" and spec["kind"] == "pid"
    assert len(spec["nodes"]) == len(s.symbols) and len(spec["edges"]) == len(s.pipes)
    sensing = [e for e in spec["edges"] if e["role"] == "sensing"]
    assert len(sensing) == 1 and sensing[0]["to"] == "PT-101"
    assert spec["drawing_area"][3] > 0
    json.dumps(spec)


def test_write_creates_svg_and_spec(tmp_path):
    paths = _sheet().write(str(tmp_path / "sheet"))
    assert (tmp_path / "sheet.svg").read_text(encoding="utf-8").startswith("<svg")
    assert (
        json.loads((tmp_path / "sheet.layout.json").read_text(encoding="utf-8"))["name"]
        == "T-001"
    )
    assert set(paths) == {"svg", "layout"}


def test_rotated_actuated_valve_bbox_includes_the_actuator():
    s = PidSheet("T-002", "Rot")
    v = s.add("esdv", "XV-9", 100, 100, rot=90)
    _x0, _y0, x1, _y1 = v.bbox()
    assert x1 - v.x > v.w / 2 + 20 and v.port("n")[1] < v.y < v.port("s")[1]


def test_profile_and_table_helpers_add_decoration():
    s = _sheet()
    before = len(s.decor)
    w, h = s.add_table(
        100, 500, ["A", "B"], [["1", "2"], ["3", "4"]], [80, 80], title="T"
    )
    s.add_profile(
        100,
        600,
        400,
        200,
        [0, 5, 10],
        [90, 95, 92],
        "P",
        "KP",
        "m",
        markers=[(5, "x", "#c00")],
    )
    assert w == 160 and h > 60 and len(s.decor) > before + 10


def test_considerations_checklist_is_complete_and_unique():
    items = subsea_tie_in_considerations()
    ids = [i["id"] for i in items]
    assert len(ids) == len(set(ids)) >= 40
    assert {i["id"][0] for i in items} == set(CATEGORIES)
    assert all(i["question"] and i["why"] and i["evidence"] for i in items)
    assert {i["id"][0] for i in subsea_tie_in_considerations("WS")} == {"W", "S"}


def test_register_defaults_to_open_and_validates_input():
    rows = considerations_register(
        {"W1": {"status": "SCREENED", "finding": "f", "action": "a"}}
    )
    by = {r["id"]: r for r in rows}
    assert by["W1"]["status"] == "SCREENED" and by["W1"]["action"] == "a"
    assert by["F6"]["status"] == "OPEN" and "Not addressed" in by["F6"]["finding"]
    summ = register_summary(rows)
    assert (
        summ["total"] == len(rows)
        and summ["by_status"]["SCREENED"] == 1
        and "W1" not in summ["open"]
    )
    with pytest.raises(ValueError):
        considerations_register({"ZZ": {"status": "OPEN"}})
    with pytest.raises(ValueError):
        considerations_register({"W1": {"status": "DONE"}})
