"""Tests for asset_scene.subsea (recognisable subsea equipment primitives)."""

import math

import pytest

from asset_scene import realistic as rl
from asset_scene import subsea as ss


def names(parts):
    return [p[0] for p in parts]


def test_xmas_tree_has_recognisable_components():
    parts = ss.xmas_tree_parts((0, 0, 0), 4.2)
    n = names(parts)
    for key in ("guide_frame", "wellhead_housing", "bore", "wing", "choke_body", "tree_cap", "fl_hub", "fl_clamp"):
        assert key in n, key
    assert n.count("valve_block") == 3 and n.count("actuator") == 3
    lo, hi = rl.mesh_bounds(rl.merge(*[p[1] for p in parts]))
    assert 3.5 < hi[2] - lo[2] < 5.5
    assert hi[0] > 1.6  # wing branch extends to the flowline connector


def test_tree_heading_rotates_flowline_connector():
    a = rl.mesh_bounds(next(p[1] for p in ss.xmas_tree_parts((0, 0, 0), heading_deg=0.0) if p[0] == "fl_hub"))
    b = rl.mesh_bounds(next(p[1] for p in ss.xmas_tree_parts((0, 0, 0), heading_deg=90.0) if p[0] == "fl_hub"))
    assert a[1][0] > 1.2 and b[1][1] > 1.2 and b[1][0] < 0.9


def test_plet_and_plem():
    plet = ss.plet_parts((0, 0, -160), 0.0)
    plem = ss.plet_parts((0, 0, -160), 0.0, inline=True)
    assert {"mudmat", "manifold_pipe", "protection_frame", "flowline_hub", "jumper_hub"} <= set(names(plet))
    assert "outlet_hub" in names(plem) and "outlet_hub" not in names(plet)
    assert any(n.startswith("valve_") for n in names(plet))


def test_manifold_has_header_and_slot_valves():
    parts = ss.manifold_parts((0, 0, -160), slots=4)
    n = names(parts)
    assert n.count("branch") == 4 and n.count("slot_hub_hub") == 4
    assert "production_header" in n and "test_header" in n and "protection_frame" in n


@pytest.mark.parametrize("shape", ["M", "W", "U"])
def test_jumper_connects_both_hubs_and_clears_seabed(shape):
    a, b = (0.0, 0.0, 1.0), (12.0, 3.0, 1.0)
    path = ss.jumper_path(a, b, shape, 3.0)
    assert path[0] == a and path[-1] == b
    parts = ss.jumper_parts(a, b, 0.273, shape, 3.0)
    lo, hi = rl.mesh_bounds(next(p[1] for p in parts if p[0] == "jumper_pipe"))
    assert hi[2] > 3.5
    assert lo[2] > 0.5 if shape != "W" else lo[2] > 0.2
    assert {"end0_hub", "end1_hub", "lift_point"} <= set(names(parts))


def test_flowline_field_joints_spacing():
    parts = ss.flowline_parts([(0, 0, 0), (122.0, 0, 0)], 0.26, 12.2)
    bands = next(p[1] for p in parts if p[0] == "field_joints")
    ring_count = len(bands[0]) // 26  # 24 side vertices + two cap centres per band
    assert ring_count in (9, 10)


def test_riser_base_and_umbilical_and_uta():
    rb = names(ss.riser_base_parts((0, 0, -160)))
    assert {"gooseneck", "ssiv_valve_body", "ssiv_actuator", "riser_hub"} <= set(rb)
    assert "ssiv_valve_body" not in names(ss.riser_base_parts((0, 0, -160), with_ssiv=False))
    u = ss.umbilical_parts([(0, 0, 0), (100, 0, 0)])
    assert math.isclose(rl.mesh_bounds(u[0][1])[1][0], 100.0, abs_tol=0.2)
    assert {"uth", "stab"} <= set(names(ss.uta_parts((0, 0, 0))))
