import json
import math

import pytest

from asset_scene import (
    AssetScene,
    analyse_pipe_stress,
    analyse_piping,
    stress_fragment,
    ColorBy,
    attach_values,
    box,
    cylinder,
    equipment_records_from_neqsim,
    from_equipment_records,
    from_layout_items,
    from_subsea_nodes,
    from_well_trajectory,
    minimum_curvature,
    read_glb_json,
    results_fragment,
    stale_live_values,
    write_glb,
    write_html,
)


def _scene():
    s = AssetScene("Test train")
    s.add_object("V-1", "vessel", cylinder([0, 0, 3], 2.0, 6.0, "z"), tag="20-VA-001", source={"quality": "verified"})
    s.add_object("K-1", "compressor", box([10, 0, 2], [6, 4, 4]), tag="23-KA-001", state="proposed")
    s.add_connection("V-1", "K-1", state="proposed")
    return s


def test_invalid_geometry_and_unknown_connection_are_rejected():
    s = AssetScene("x")
    with pytest.raises(ValueError):
        s.add_object("a", "vessel", cylinder([0, 0, 0], -1.0, 2.0))
    with pytest.raises(ValueError):
        s.add_object("b", "spaceship", box([0, 0, 0], [1, 1, 1]))
    s.add_object("c", "vessel", box([0, 0, 0], [1, 1, 1]))
    s.add_connection("c", "missing")
    assert any("missing" in issue for issue in s.validate())


def test_round_trip_and_tag_lookup(tmp_path):
    s = _scene()
    loaded = AssetScene.load(s.save(tmp_path / "scene.json"))
    assert loaded.validate() == []
    assert loaded.find_by_tag(" 20-va-001")["id"] == "V-1"


def test_auto_layout_follows_flow_and_flags_assumptions():
    records = [
        {"tag": "K-1", "kind": "compressor", "size_m": [6, 4, 4], "size_quality": "derived"},
        {"tag": "V-1", "kind": "vessel", "diameter_m": 2.0, "length_m": 6.0, "orientation": "vertical"},
        {"tag": "E-1", "kind": "heat_exchanger"},
    ]
    conns = [{"from": "V-1", "to": "K-1"}, {"from": "K-1", "to": "E-1"}]
    s = from_equipment_records(records, conns)
    x = {o["id"]: o["geometry"]["center"][0] for o in s.objects}
    assert x["V-1"] < x["K-1"] < x["E-1"]
    assert s.get("V-1")["geometry"]["center"][2] == pytest.approx(3.0)
    assert all(o["source"]["position_quality"] == "assumed" for o in s.objects)
    assert any("E-1" in gap["gap"] for gap in s.data_gaps)
    assert len(s.connections) == 2


def test_minimum_curvature_quarter_circle():
    radius = 1000.0
    md = [i * math.pi / 2 * radius / 90 for i in range(91)]
    inc = list(range(91))
    pts = minimum_curvature(md, inc, [0.0] * 91)
    north, east, tvd = pts[-1]
    assert north == pytest.approx(radius, rel=1e-6)
    assert tvd == pytest.approx(radius, rel=1e-6)
    assert east == pytest.approx(0.0, abs=1e-6)


def test_well_trajectory_uses_datum_and_aliases():
    stations = [{"md": 0, "inc": 0, "azi": 0}, {"md": 500, "inc": 0, "azi": 0}]
    s = from_well_trajectory("A-1", stations, (100.0, 200.0), datum_z=40.0)
    pts = s.get("A-1")["geometry"]["points"]
    assert pts[-1] == pytest.approx([100.0, 200.0, -460.0])
    assert s.get("A-1")["source"]["quality"] == "derived"


def test_subsea_line_to_host_gets_riser_and_geographic_projection():
    nodes = [
        {"name": "HOST", "x": 2.0, "y": 60.0, "water_depth_m": 300, "kind": "host"},
        {"name": "T1", "x": 2.0, "y": 61.0, "water_depth_m": 320, "kind": "template"},
    ]
    s = from_subsea_nodes(nodes, [{"from": "T1", "to": "HOST", "kind": "flowline"}], coordinate_system="geographic")
    line = [o for o in s.objects if o["kind"] == "flowline"][0]
    pts = line["geometry"]["points"]
    assert pts[-1][2] == 0.0 and pts[-2][2] == -300.0
    assert abs(pts[0][1] - pts[-1][1]) == pytest.approx(111195, rel=1e-3)
    assert line["source"]["quality"] == "assumed"
    assert s.assumptions


def test_glb_is_valid_and_tagged(tmp_path):
    path = write_glb(_scene(), tmp_path / "s.glb")
    doc = read_glb_json(path)
    names = {n["name"] for n in doc["nodes"]}
    assert {"20-VA-001", "23-KA-001"} <= names
    vessel = next(n for n in doc["nodes"] if n["name"] == "20-VA-001")
    acc = doc["accessors"][doc["meshes"][vessel["mesh"]]["primitives"][0]["attributes"]["POSITION"]]
    assert acc["max"][1] == pytest.approx(6.0, abs=1e-4)  # z (height) maps to glTF Y
    assert vessel["extras"]["state"] == "existing"


def test_html_viewer_is_offline(tmp_path):
    s = _scene()
    s.classification = "Internal"
    html = write_html(s, tmp_path / "s.html").read_text(encoding="utf-8")
    assert "<script src" not in html and "http" not in html.lower().replace("http-equiv", "")
    assert "20-VA-001" in html and "Internal" in html


def test_png_render(tmp_path):
    pytest.importorskip("matplotlib")
    from asset_scene import render_png

    out = render_png(_scene(), tmp_path / "iso.png")
    assert (tmp_path / "iso.png").stat().st_size > 1000
    assert "verified" in out["caption"]


def test_values_colouring_and_results_fragment():
    s = _scene()
    unmatched = attach_values(s, {"20-VA-001": {"utilisation": 1.1}, "99-XX-999": {"utilisation": 0.2}})
    assert unmatched == ["99-XX-999"]
    cb = ColorBy("results", "utilisation", mode="utilisation").fit(s.objects)
    red = cb.color(s.get("V-1"))
    assert red[0] > red[1]
    frag = results_fragment(s)
    gap = frag["data_gaps"][0]
    assert set(gap) == {"gap", "source", "status", "assumed", "effect"}
    assert frag["tables"][0]["headers"][0] == "Tag"


def test_stale_live_values():
    s = _scene()
    s.get("V-1")["live"]["pressure"] = {"value": 70, "unit": "bara", "timestamp": "2020-01-01T00:00:00Z"}
    assert stale_live_values(s, max_age_s=3600) == ["V-1"]


def test_layout_items_use_bounds():
    items = [
        {"name": "Deck", "tag": "DECK-1", "kind": "deck", "deck": "M10", "bounds_m": [0, 0, 0, 30, 20, 0.5]},
        {
            "name": "Sep",
            "tag": "20-VA-001",
            "kind": "equipment",
            "equipment_kind": "separator",
            "deck": "M10",
            "bounds_m": [2, 2, 0.5, 12, 6, 4.5],
            "dimension_source": "NeqSim mechanical design",
        },
    ]
    s = from_layout_items(items)
    sep = s.find_by_tag("20-VA-001")
    assert sep["kind"] == "vessel" and sep["source"]["quality"] == "derived"
    assert sep["geometry"]["size"] == [10.0, 4.0, 4.0]


class _J:
    def __init__(self, value):
        self.value = value

    def getSimpleName(self):
        return self.value


class _Unit:
    def __init__(self, name, cls, design=None):
        self._name, self._cls, self._design = name, cls, design

    def getName(self):
        return self._name

    def getClass(self):
        return _J(self._cls)

    def getMechanicalDesign(self):
        design = self._design

        class _MD:
            def toDesignDataJson(self):
                if design is None:
                    raise RuntimeError("no design")
                return json.dumps(design)

        return _MD()


class _Node:
    def __init__(self, name):
        self.name = name

    def getName(self):
        return self.name


class _Edge:
    def __init__(self, s, t, kind="MATERIAL"):
        self.s, self.t, self.kind = _Node(s), _Node(t), kind

    def getSource(self):
        return self.s

    def getTarget(self):
        return self.t

    def getEdgeType(self):
        return self.kind


class _Process:
    def __init__(self, units, edges):
        self.units, self.edges = units, edges

    def getUnitOperations(self):
        return self.units

    def buildGraph(self):
        edges = self.edges

        class _G:
            def getEdges(self):
                return edges

        return _G()


def test_neqsim_adapter_reads_design_json_and_bridges_streams():
    design = {
        "geometry": {"innerDiameter": {"value": 2.4, "unit": "m"}, "tangentLength": {"value": 7.5, "unit": "m"}},
        "designBasis": {"maximumDesignPressure": {"value": 8.0e6, "unit": "Pa"}},
        "orientation": "horizontal",
    }
    process = _Process(
        [_Unit("feed", "Stream"), _Unit("HP sep", "Separator", design), _Unit("gas", "Stream"), _Unit("comp", "Compressor")],
        [_Edge("feed", "HP sep"), _Edge("HP sep", "gas"), _Edge("gas", "comp")],
    )
    records, conns = equipment_records_from_neqsim(process)
    assert [r["tag"] for r in records] == ["HP sep", "comp"]
    assert records[0]["diameter_m"] == 2.4 and records[0]["attributes"]["neqsim_max_design_pressure_bara"] == 80.0
    assert conns == [{"from": "HP sep", "to": "comp", "kind": "process"}]
    s = from_equipment_records(records, conns)
    assert s.get("HP sep")["geometry"]["axis"] == "x"
    assert s.get("comp")["source"]["size_quality"] == "assumed"


def _is_axis_aligned(points):
    for p, q in zip(points[:-1], points[1:]):
        changed = sum(1 for i in range(3) if abs(p[i] - q[i]) > 1e-9)
        if changed > 1:
            return False
    return True


def test_orthogonal_route_clears_obstacle_and_starts_at_faces():
    from asset_scene import route_connections

    s = AssetScene("Rack")
    s.add_object("A", "vessel", box([0, 0, 2], [4, 2, 4]))
    s.add_object("B", "vessel", box([20, 6, 1.5], [3, 2, 3]))
    s.add_object("C", "compressor", box([10, 0, 3], [4, 4, 6]))  # tall item under the run
    s.add_connection("A", "B")
    route = route_connections(s, 0.2)["A->B"]
    pts = route["points"]
    assert route["mode"] == "orthogonal" and _is_axis_aligned(pts)
    assert pts[0][0] == pytest.approx(2.0)  # leaves A through its +x face
    assert pts[-1][1] == pytest.approx(5.0) or pts[-1][0] == pytest.approx(18.5)  # enters a B face
    assert max(p[2] for p in pts) >= 6.0 + 1.0  # rack clears C (top at 6 m)


def test_parallel_pipes_get_separate_lanes():
    from asset_scene import route_connections

    s = AssetScene("Lanes")
    s.add_object("A", "vessel", box([0, 0, 2], [4, 2, 4]))
    s.add_object("B", "vessel", box([20, 0, 2], [4, 2, 4]))
    s.add_connection("A", "B", id="1")
    s.add_connection("A", "B", id="2")
    r = route_connections(s, 0.2)
    assert max(p[2] for p in r["2"]["points"]) > max(p[2] for p in r["1"]["points"])


def test_supplied_route_is_used_and_validated(tmp_path):
    from asset_scene import route_connections

    s = _scene()
    s.connections.clear()
    with pytest.raises(ValueError):
        s.add_connection("V-1", "K-1", route=[[0, 0, 0]])
    s.add_connection("V-1", "K-1", route=[[2, 0, 5], [7, 0, 5]], route_reference="ISO-001", line_number="L-1")
    r = route_connections(s, 0.2)["V-1->K-1"]
    assert r["mode"] == "supplied" and [2.0, 0.0, 5.0] in r["points"]
    doc = read_glb_json(write_glb(s, tmp_path / "r.glb"))
    pipe = next(n for n in doc["nodes"] if n["name"] == "L-1")
    assert pipe["extras"]["route_mode"] == "supplied"
    frag = results_fragment(s)
    assert not any("no piping route" in g["gap"] for g in frag["data_gaps"])
    s.translate(1, 0, 0)
    assert s.connections[0]["route"][0] == [3.0, 0.0, 5.0]


def test_field_scale_connections_follow_seabed_and_caption_names_routing(tmp_path):
    pytest.importorskip("matplotlib")
    from asset_scene import render_png, route_connections

    s = AssetScene("Field")
    s.add_object("T1", "template", box([0, 0, -297], [20, 15, 6]), group="subsea")
    s.add_object("T2", "template", box([3000, 0, -317], [20, 15, 6]), group="subsea")
    s.add_connection("T1", "T2")
    r = route_connections(s, 0.3)["T1->T2"]
    assert r["mode"] == "seabed" and r["points"][0][2] == pytest.approx(-300.0)
    out = render_png(s, tmp_path / "f.png")
    assert "along the seabed" in out["caption"]
    assert any("no piping route" in g["gap"] for g in results_fragment(s)["data_gaps"])


# ---------------------------------------------------------------- piping screening
def test_span_is_at_or_below_mss_sp69_tables():
    from asset_scene import max_span

    for od, wall, table in ((0.0603, 0.00391, 3.0), (0.1683, 0.00711, 5.2), (0.3239, 0.00953, 7.0)):
        span = max_span(od, wall)["span_m"]
        assert 0.85 * table <= span <= 1.05 * table


def test_b313_flexibility_screen():
    from asset_scene import b313_flexibility

    straight = b313_flexibility(0.1683, 20.0, 20.0, 100.0)
    assert straight["status"] == "needs_stress_analysis" and straight["ratio"] is None
    loop = b313_flexibility(0.1683, 40.0, 20.0, 100.0)
    # y = 12e-6 * 100 * 20 m = 24 mm; 168.3 * 24 / 20^2 = 10.1 < 208.3
    assert loop["y_mm"] == pytest.approx(24.0) and loop["ratio"] == pytest.approx(10.1, abs=0.1)
    assert loop["status"] == "pass"


def test_nozzles_and_port_conventions_set_pipe_ends():
    from asset_scene import route_connections

    s = AssetScene("Nozzles")
    s.add_object("SEP", "vessel", cylinder([0, 0, 1.5], 3.0, 10.0, "x"),
                 nozzles={"N2": {"offset_m": [4.0, 0.0, 1.5], "direction": [0, 0, 1], "service": "gas_outlet"}})
    s.add_object("K", "compressor", box([20, 0, 2], [6, 4, 4]))
    s.add_object("P", "pump", box([20, 8, 0.6], [2, 1, 1.2]))
    s.add_connection("SEP", "K", from_port="gas_outlet", diameter=0.3)
    s.add_connection("SEP", "P", from_port="liquid_outlet", diameter=0.15)
    r = route_connections(s, 0.2)
    assert r["SEP->K"]["points"][0] == pytest.approx([4.0, 0.0, 3.0]) and r["SEP->K"]["ends"][0] == "nozzle"
    assert r["SEP->P"]["points"][0][2] == pytest.approx(0.0) and r["SEP->P"]["ends"][0] == "port_convention"
    with pytest.raises(ValueError):
        s.add_object("bad", "vessel", box([0, 0, 0], [1, 1, 1]), nozzles={"N1": {"offset_m": [0, 0]}})
    with pytest.raises(ValueError):
        s.add_connection("SEP", "K", slope=0.01)


def test_slope_is_built_into_auto_routes_and_checked_on_supplied_routes():
    from asset_scene import analyse_piping

    s = AssetScene("Flare")
    s.add_object("KO", "vessel", box([0, 0, 2], [3, 3, 4]))
    s.add_object("FL", "vessel", box([40, 10, 2], [3, 3, 4]))
    s.add_object("D", "vessel", box([0, 30, 2], [3, 3, 4]))
    s.add_connection("FL", "KO", diameter=0.3, min_slope=0.005, id="auto")
    s.add_connection("D", "KO", diameter=0.2, min_slope=0.005, id="flat", route=[[0, 26, 8], [0, 5, 8]])
    rep = analyse_piping(s)
    rows = {r["id"]: r for r in rep["connections"]}
    assert rows["auto"]["slope"]["status"] == "pass"
    assert rows["auto"]["slope"]["minimum_achieved"] >= 0.005 - 1e-9
    assert rows["flat"]["slope"]["status"] == "fail"


def test_supports_flexibility_from_neqsim_result_and_gaps(tmp_path):
    pytest.importorskip("matplotlib")
    from asset_scene import add_pipe_supports, analyse_piping, piping_fragment, render_png

    s = AssetScene("Train")
    s.add_object("A", "vessel", box([0, 0, 2], [4, 2, 4]), results={"temperature": {"value": 120.0, "unit": "C"}})
    s.add_object("B", "vessel", box([30, 0, 2], [4, 2, 4]))
    s.add_object("C", "vessel", box([0, 20, 2], [4, 2, 4]))
    s.add_connection("A", "B", diameter=0.1683, line_number="L-1")
    s.add_connection("C", "B", line_number="L-2")
    rep = analyse_piping(s)
    l1, l2 = rep["connections"]
    assert l1["max_span_m"] == pytest.approx(5.05, abs=0.1) and len(l1["supports"]) >= 6
    assert l1["flexibility"]["temperature_basis"].startswith("NeqSim result")
    assert l2["flexibility"]["status"] == "no_size"
    added = add_pipe_supports(s, rep)
    assert added and s.get(added[0])["kind"] == "support" and s.validate() == []
    gaps = " ".join(g["gap"] for g in piping_fragment(rep, s.name)["data_gaps"])
    assert "No pipe size for L-2" in gaps and "Nozzle position not supplied for L-1" in gaps
    assert rep["summary"]["pipe_clashes"] == 0
    render_png(s, tmp_path / "t.png")


def test_clash_is_resolved_by_lane_change_and_reported_when_forced():
    from asset_scene import check_clashes, route_connections

    s = AssetScene("Clash")
    s.add_object("A", "vessel", box([0, 0, 2], [4, 2, 4]))
    s.add_object("B", "vessel", box([20, 0, 2], [4, 2, 4]))
    s.add_object("C", "vessel", box([0, 6, 2], [4, 2, 4]))
    s.add_object("D", "vessel", box([20, -6, 2], [4, 2, 4]))
    s.add_connection("A", "B", diameter=0.3)
    s.add_connection("C", "D", diameter=0.3)
    assert check_clashes(s, route_connections(s, 0.3), 0.3) == []
    s2 = AssetScene("Forced")
    s2.objects = s.objects
    s2.add_connection("A", "B", diameter=0.3, route=[[3, 0, 6], [17, 0, 6]], id="r1")
    s2.add_connection("C", "D", diameter=0.3, route=[[10, 6, 6], [10, -6, 6]], id="r2")
    clashes = check_clashes(s2, route_connections(s2, 0.3), 0.3)
    assert any(c["type"] == "pipe" for c in clashes)


def test_bottom_outlet_clears_own_vessel():
    from asset_scene import check_clashes, route_connections

    s = AssetScene("Bottom")
    s.add_object("SEP", "vessel", cylinder([0, 0, 2], 3.0, 10.0, "x"))
    s.add_object("P", "pump", box([15, 0, 0.6], [2, 1, 1.2]))
    s.add_object("K", "compressor", box([15, 8, 2], [6, 4, 4]))
    s.add_connection("SEP", "P", from_port="liquid_outlet", diameter=0.15)
    s.add_connection("SEP", "K", from_port="gas_outlet", diameter=0.3)
    routes = route_connections(s, 0.2)
    assert check_clashes(s, routes, 0.2) == []
    pts = routes["SEP->P"]["points"]
    risers = [(p, q) for p, q in zip(pts[:-1], pts[1:]) if abs(p[0] - q[0]) < 1e-9 and abs(p[1] - q[1]) < 1e-9]
    assert all(abs(p[0]) > 5.0 for p, _ in risers if p[2] < 0)  # rises outside the 10 m long shell


def _stress_scene(temperature_c=140.0, allowables=None):
    s = AssetScene("Hot gas train")
    s.add_object("V", "vessel", cylinder([0, 0, 1.6], 3.2, 10.0, "x"), tag="20-VA-001",
                 attributes={"design_pressure_barg": 95.0},
                 nozzles={"N2": {"offset_m": [4.0, 0, 1.6], "direction": [0, 0, 1], "service": "gas_outlet"}})
    s.add_object("K", "compressor", box([25, 6, 2.25], [7, 4, 4.5]), tag="23-KA-001",
                 attributes={"nozzle_allowables": allowables} if allowables else {})
    s.add_connection("V", "K", line_number="20-PG-0101", from_port="gas_outlet", diameter=0.2731,
                     wall_thickness_m=0.0151, operating_temperature_C=temperature_c, fluid_density_kg_m3=60.0)
    return s


def _stress_class_or_skip():
    import os

    jar = os.environ.get("NEQSIM_JAR")
    if jar:
        jpype = pytest.importorskip("jpype")
        if not jpype.isJVMStarted():
            jpype.startJVM(classpath=[jar])
    from asset_scene.stress import neqsim_pipe_stress_class

    if neqsim_pipe_stress_class() is None:
        pytest.skip("installed NeqSim has no PipeStressModel (set NEQSIM_JAR to a >= 3.29.0 jar)")


def test_stress_without_neqsim_class_is_reported_as_gap(monkeypatch):
    import asset_scene.stress as stress

    monkeypatch.setattr(stress, "neqsim_pipe_stress_class", lambda: None)
    s = _stress_scene()
    rep = stress.analyse_pipe_stress(s, analyse_piping(s))
    assert rep["connections"][0]["stress"]["status"] == "unavailable"
    frag = stress_fragment(rep, s.name)
    assert any("PipeStressModel" in g["gap"] or "20-PG-0101" in g["gap"] for g in frag["data_gaps"])


def test_stress_runs_in_neqsim_with_friction_lift_off_and_nozzle_check():
    _stress_class_or_skip()
    allow = {"default": {"force_N": 15000.0, "moment_Nm": 12000.0}}
    cold = analyse_pipe_stress(_stress_scene(60.0, allow), analyse_piping(_stress_scene(60.0, allow)))
    s = _stress_scene(250.0, allow)
    hot = analyse_pipe_stress(s, analyse_piping(s), seismic_g=0.1)
    st = hot["connections"][0]["stress"]
    assert st["converged"]
    assert st["pressure_design"] == "pass"
    # expansion stress grows with temperature, sustained stress does not
    assert st["expansion_ratio"] > cold["connections"][0]["stress"]["expansion_ratio"]
    assert st["sustained_ratio"] == pytest.approx(cold["connections"][0]["stress"]["sustained_ratio"], rel=1e-6)
    assert st["occasional_ratio"] > 0.0
    states = {x["state"] for x in st["supports"]}
    assert states <= {"in_contact", "sliding", "lifted_off"}
    by_obj = {n["object"]: n["status"] for n in st["nozzles"]}
    assert by_obj["K"] in ("pass", "fail") and by_obj["V"] == "no_allowable"
    frag = stress_fragment(hot, s.name)
    assert frag["tables"][0]["rows"][0][0] == "20-PG-0101"
    assert any("nozzle load allowables" in g["gap"] for g in frag["data_gaps"])


def test_merge_replaces_table_with_same_title():
    from asset_scene import merge_into_results

    results = {"tables": [{"title": "Other", "rows": []}]}
    merge_into_results(results, {"tables": [{"title": "Pipe stress", "rows": [[1]]}]})
    merge_into_results(results, {"tables": [{"title": "Pipe stress", "rows": [[2]]}]})
    assert [t["title"] for t in results["tables"]] == ["Other", "Pipe stress"]
    assert results["tables"][1]["rows"] == [[2]]
