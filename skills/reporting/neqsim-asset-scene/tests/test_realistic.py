"""Tests for the realistic 3D primitives (asset_scene.realistic)."""

import math

import pytest

from asset_scene import realistic as rl


def _valid(mesh):
    n = len(mesh[0])
    assert n > 0 and len(mesh[1]) > 0
    assert all(0 <= i < n for f in mesh[1] for i in f)


def test_vessel_ellipsoidal_volume_matches_analytic():
    d, length = 3.0, 10.0
    m = rl.vessel_mesh((0, 0, 0), d, length, "horizontal", "ellipsoidal", segments=96)
    _valid(m)
    r = d / 2
    analytic = math.pi * r * r * length + 2 * (2.0 / 3.0) * math.pi * r * r * (d / 4)
    assert rl.mesh_volume(m) == pytest.approx(analytic, rel=0.01)
    lo, hi = rl.mesh_bounds(m)
    assert hi[0] - lo[0] == pytest.approx(length + d / 2, rel=1e-3)  # tangent length plus two 2:1 heads
    assert hi[2] - lo[2] == pytest.approx(d, rel=1e-2)


def test_vessel_head_types_change_length():
    lens = {}
    for head in ("ellipsoidal", "hemispherical", "torispherical", "flat"):
        lo, hi = rl.mesh_bounds(rl.vessel_mesh((0, 0, 0), 2.0, 6.0, "vertical", head))
        lens[head] = hi[2] - lo[2]
    assert lens["flat"] == pytest.approx(6.0, rel=1e-6)
    assert lens["flat"] < lens["torispherical"] < lens["ellipsoidal"] < lens["hemispherical"]


def test_vessel_parts_have_saddles_and_nozzles():
    parts = rl.vessel_parts((0, 0, 3), 3.0, 10.0, nozzles=[{"s": 0.2, "angle_deg": 0, "diameter": 0.3}, {"s": -0.2, "angle_deg": 180, "diameter": 0.2}])
    names = [p[0] for p in parts]
    assert names.count("saddle") == 2 and names.count("nozzle") == 2 and names.count("flange") == 2
    for _n, m, mat in parts:
        _valid(m)
        assert mat in rl.MATERIALS


def test_fillet_path_rounds_corner_and_shortens_path():
    pts = [(0, 0, 0), (10, 0, 0), (10, 10, 0)]
    path = rl.fillet_path(pts, 2.0)
    assert len(path) > 3
    assert rl.path_length(path) < rl.path_length(pts)
    # arc tangent point at distance bend_radius from the corner for a 90 degree elbow
    assert any(abs(p[0] - 8.0) < 1e-6 and abs(p[1]) < 1e-6 for p in path)
    # every point of the arc lies on or inside the corner (no overshoot)
    assert all(p[0] <= 10 + 1e-9 and p[1] >= -1e-9 for p in path)


def test_swept_tube_follows_elbow_with_constant_radius():
    path = rl.fillet_path([(0, 0, 0), (10, 0, 0), (10, 0, 10)], 2.0)
    m = rl.swept_tube(path, 0.3, 16)
    _valid(m)
    n = 16
    for i in range(len(path)):
        ring = m[0][i * n:(i + 1) * n]
        for p in ring:
            d = math.dist(p, path[i])
            assert d == pytest.approx(0.3, rel=1e-6)


def test_flange_and_valve_parts():
    f = rl.flange_mesh((0, 0, 0), (1, 0, 0), 0.5, 0.05)
    _valid(f)
    lo, hi = rl.mesh_bounds(f)
    assert hi[1] - lo[1] == pytest.approx(0.5, rel=0.05)
    parts = rl.valve_parts((0, 0, 0), (1, 0, 0), 0.2)
    assert {"valve_body", "bonnet", "stem", "handwheel"} <= {p[0] for p in parts}
    _valid(parts[0][1])


def test_jacket_has_four_battered_legs_and_bracing():
    parts = dict((n, m) for n, m, _ in rl.jacket_parts((0, 0), -100.0, 20.0, (60, 60), (30, 30), bays=4))
    legs, bracing = parts["jacket_legs"], parts["jacket_bracing"]
    _valid(legs)
    lo, hi = rl.mesh_bounds(legs)
    assert hi[2] - lo[2] == pytest.approx(120.0, abs=1.5)  # leg radius tilts the end caps slightly
    assert hi[0] - lo[0] == pytest.approx(60 + 2 * 1.0, rel=0.02)  # base footprint plus leg radii
    assert len(bracing[1]) > len(legs[1])


def test_deck_and_module_parts():
    deck = dict((n, m) for n, m, _ in rl.deck_parts((0, 60, 0, 40, 20, 24)))
    assert {"deck_plate", "deck_beams", "handrail"} <= set(deck)
    lo, hi = rl.mesh_bounds(deck["deck_plate"])
    assert hi[2] == pytest.approx(24.0)
    mod = dict((n, m) for n, m, _ in rl.module_parts((0, 20, 0, 12, 24, 30)))
    assert rl.mesh_bounds(mod["module_roof"])[1][2] > 30.0


def test_template_has_trees_per_slot():
    parts = rl.template_parts((0, 0, -160), (30, 20, 6), slots=(2, 2))
    assert sum(1 for p in parts if p[0] == "tree_stack") == 4
    assert sum(1 for p in parts if p[0] == "tree_stack") == sum(1 for p in parts if p[0] == "choke_module")
    no_trees = rl.template_parts((0, 0, -160), (30, 20, 6), with_trees=False)
    assert not any(p[0] == "tree_stack" for p in no_trees)


def test_seabed_relief_and_flattening():
    sb = rl.Seabed((-500, 500), (-300, 300), 40, 24, base_z=-160.0, relief_m=8.0, flatten=[(0.0, 0.0, 120.0)], seed=3)
    _valid(sb.mesh)
    assert sb.z(0.0, 0.0) == pytest.approx(-160.0, abs=1e-6)  # flat at the site
    zs = [v[2] for v in sb.mesh[0]]
    assert max(zs) - min(zs) > 4.0  # relief elsewhere
    assert all(abs(z + 160.0) <= 8.0 + 1e-6 for z in zs)
    sb2 = rl.Seabed((-500, 500), (-300, 300), 40, 24, base_z=-160.0, relief_m=8.0, flatten=[(0.0, 0.0, 120.0)], seed=3)
    assert sb.mesh[0] == sb2.mesh[0]  # deterministic


def test_well_strings_telescope():
    path = [(0, 0, -160.0), (0, 0, -860.0), (-300.0, 0, -1500.0)]
    strings = [{"name": "conductor", "od_m": 0.762, "md_end_m": 150.0}, {"name": "surface", "od_m": 0.508, "md_end_m": 700.0},
               {"name": "tubing", "od_m": 0.14, "md_end_m": 1300.0, "material": "steel"}]
    parts = rl.well_string_parts(path, strings)
    assert [p[0] for p in parts] == ["conductor", "surface", "tubing"]
    zmin = [rl.mesh_bounds(p[1])[0][2] for p in parts]
    assert zmin[0] > zmin[1] > zmin[2]  # outer strings stop higher
    wide = [rl.mesh_bounds(p[1])[1][0] - rl.mesh_bounds(p[1])[0][0] for p in parts]
    assert wide[0] > 0.7 and wide[0] > wide[1]


def test_reservoir_layer_is_closed_with_positive_volume():
    m = rl.reservoir_layer((0, 0, -2870), (1800, 1500, 0), 40.0, undulation_m=0.0, dip_deg=0.0)
    _valid(m)
    assert abs(rl.mesh_volume(m)) == pytest.approx(1800 * 1500 * 40.0, rel=0.02)


def test_normals_unit_length_and_converters():
    m = rl.vessel_mesh((0, 0, 0), 1.0, 2.0)
    for n in rl.vertex_normals(m)[:20]:
        assert math.sqrt(sum(c * c for c in n)) == pytest.approx(1.0, rel=1e-6)
    d = rl.to_plotly_arrays(m)
    assert len(d["x"]) == len(m[0]) and len(d["i"]) == len(m[1])
    groups = rl.merge_parts(rl.vessel_parts((0, 0, 3), 3.0, 8.0))
    assert "vessel_paint" in groups and "steel_dark" in groups
