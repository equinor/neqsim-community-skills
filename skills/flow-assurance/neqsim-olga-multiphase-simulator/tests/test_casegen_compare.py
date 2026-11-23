"""Tests for the Grimsnes-style case generator (route profile -> genkey) and the NeqSim-vs-OLGA comparison helper."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest
from olga_multiphase_simulator import (
    STEEL,
    ComparisonRow,
    FlowlineCaseSpec,
    Material,
    WallLayer,
    build_mesh,
    compare_rows,
    dominant_period,
    equivalent_insulation_thickness,
    list_keywords,
    load_route_profile,
    overall_u_inner,
    render_genkey,
    simplify_route,
    slug_statistics,
    to_csv,
    to_markdown,
)
from olga_multiphase_simulator.genkey import get_parameter

FOAM = Material("PU_FOAM", 0.12, 600.0, 1800.0)
ID, T_STEEL = 0.2857, 0.0191


@pytest.fixture()
def route_json(tmp_path: Path) -> Path:
    # 6 km of gently undulating seabed (95-105 m depth), SURF route_profile style
    kp = [i * 0.1 for i in range(61)]
    depth = [100.0 + 5.0 * math.sin(2 * math.pi * k / 3.0) for k in kp]
    path = tmp_path / "route.json"
    path.write_text(
        json.dumps({"route": "demo", "kp_km": kp, "depth_m": depth, "crossings": []}),
        encoding="utf-8",
    )
    return path


def _spec(route_json: Path, **kw) -> FlowlineCaseSpec:
    route = load_route_profile(route_json)
    mesh = build_mesh(
        route,
        150.0,
        121.0,
        target_section_m=300.0,
        riser_section_m=10.0,
        simplify_tol_m=0.5,
    )
    layers = [WallLayer(STEEL, T_STEEL), WallLayer(FOAM, 0.08)]
    return FlowlineCaseSpec(
        name="demo",
        pvt_file="fluid.tab",
        fluid_label="FLUIDX",
        mesh=mesh,
        diameter_m=ID,
        layers_seabed=layers,
        layers_riser=layers,
        source_massflow_kg_s=(30.0,),
        gas_fraction_hc=0.45,
        water_fraction=0.2,
        **kw,
    )


def test_route_profile_is_converted_to_elevation(route_json):
    route = load_route_profile(route_json)
    assert route.x_m[0] == 0.0 and route.x_m[-1] == pytest.approx(6000.0)
    assert all(z < 0 for z in route.z_m)  # depth is positive down, z up
    assert route.z_m[0] == pytest.approx(-100.0)


def test_simplify_keeps_ends_and_respects_tolerance():
    x = [float(i) for i in range(101)]
    z = [0.2 * math.sin(i / 7.0) for i in range(101)]
    xs, zs = simplify_route(x, z, 0.5)
    assert (
        xs[0] == 0.0 and xs[-1] == 100.0 and len(xs) == 2
    )  # all deviations below 0.5 m
    xs, zs = simplify_route(x, [10 * v for v in z], 0.5)
    assert len(xs) > 2
    for xi, zi in zip(
        x, [10 * v for v in z]
    ):  # every input point within tolerance of the polyline
        j = (
            max(k for k in range(len(xs)) if xs[k] <= xi)
            if xi < xs[-1]
            else len(xs) - 2
        )
        zz = zs[j] + (zs[j + 1] - zs[j]) * (xi - xs[j]) / (xs[j + 1] - xs[j])
        assert abs(zi - zz) <= 0.5 + 1e-9


def test_mesh_has_seabed_and_riser_with_bounded_ratio(route_json):
    route = load_route_profile(route_json)
    mesh = build_mesh(route, 150.0, 121.0, target_section_m=300.0, riser_section_m=10.0)
    labels = [p.label for p in mesh.pipes]
    assert labels[0].startswith("SEA") and labels[-1] == "RIS_01"
    riser = mesh.pipes[-1]
    assert riser.length == pytest.approx(150.0, rel=1e-6)
    assert riser.elevation_change == pytest.approx(121.0)
    assert mesh.summary()["max_adjacent_ratio"] <= 1.8 + 1e-6


def test_equivalent_insulation_reproduces_target_u():
    for u_target in (2.0, 3.0):
        t = equivalent_insulation_thickness(u_target, ID, T_STEEL, FOAM, 100.0)
        u = overall_u_inner(ID, [WallLayer(STEEL, T_STEEL), WallLayer(FOAM, t)], 100.0)
        assert u == pytest.approx(u_target, rel=1e-6)
    assert equivalent_insulation_thickness(
        2.0, ID, T_STEEL, FOAM, 100.0
    ) > equivalent_insulation_thickness(3.0, ID, T_STEEL, FOAM, 100.0)
    with pytest.raises(ValueError):
        equivalent_insulation_thickness(
            500.0, ID, T_STEEL, FOAM, 100.0
        )  # more than bare steel + film allows


def test_genkey_structure_and_source_bases(route_json):
    text = render_genkey(_spec(route_json))
    kws = list_keywords(text)
    for needed in (
        "OPTIONS",
        "FILES",
        "INTEGRATION",
        "MATERIAL",
        "WALL",
        "NETWORKCOMPONENT",
        "CONNECTION",
        "ENDCASE",
    ):
        assert needed in kws
    assert get_parameter(text, "FILES", "PVTFILE").strip('"') == "fluid.tab"
    assert "STEADYSTATE=ON" in text
    # GASFRACTION is the hydrocarbon basis and WATERFRACTION the total basis, both on the SOURCE
    assert "GASFRACTION=(0.450000)" in text.replace(
        " ", ""
    ) and "WATERFRACTION=(0.200000)" in text.replace(" ", "")
    assert (
        text.count("NETWORKCOMPONENT TYPE=FLOWPATH") == 1
    )  # single topology: topside inlet + ESDV inside the production flowpath
    assert "TOP_01" in text and 'VALVE LABEL="ESDV"' in text and "NODE_TOP" not in text
    node_text = render_genkey(_spec(route_json, topology="node"))
    assert node_text.count("NETWORKCOMPONENT TYPE=FLOWPATH") == 2
    assert "NODE_TOP" in node_text
    assert "FP_BDV" not in text
    flat0 = re.sub(r"\s+", " ", text.replace("\\\n", " "))
    sep_line = flat0[flat0.index('LABEL="SEPARATOR"') :]
    assert (
        "GASFRACTION=1 -" in sep_line and "WATERFRACTION=0 -" in sep_line
    )  # pressure-node back-flow is gas, not table-equilibrium liquid
    assert all(len(line) <= 125 for line in text.splitlines())


def test_genkey_events_esdv_bdv_hydrate_and_pressure_series(route_json):
    spec = _spec(
        route_json,
        esdv_times_s=(0.0, 600.0, 610.0),
        esdv_opening=(1.0, 1.0, 0.0),
        bdv_diameter_m=0.1016,
        bdv_mode="branch",
        bdv_times_s=(0.0, 630.0, 640.0),
        bdv_opening=(0.0, 0.0, 1.0),
        choke_diameter_m=0.15,
        hydrate_curve_block='HYDRATECURVE LABEL="HYD", PRESSURE=(2,10,50) bara, TEMPERATURE=(-5,8,18) C',
        hydrate_curve_label="HYD",
        p_outlet_times_s=(0.0, 100.0),
        p_outlet_series_bara=(13.0, 14.0),
    )
    text = render_genkey(spec)
    flat = re.sub(r"\s+", " ", text.replace("\\\n", " "))
    assert "FP_BDV" in text and "NODE_FLARE" in text
    assert "OPENING=(1, 1, 0) -" in flat and "OPENING=(0, 0, 1) -" in flat
    assert 'HYDRATECHECK HYDRATECURVE="HYD"' in text and "DTHYD" in text
    assert 'LABEL="CHOKE"' in text
    assert "PRESSURE=(13, 14) bara" in flat and "TIME=(0, 100) s" in flat
    # the hydrate block goes before the first network component (library level)
    assert text.index("HYDRATECURVE") < text.index("NETWORKCOMPONENT")


def test_blowdown_as_external_leak_has_no_checkvalve_and_opens_by_back_pressure(
    route_json,
):
    spec = _spec(
        route_json,
        bdv_diameter_m=0.1016,
        bdv_times_s=(0.0, 630.0, 640.0),
        bdv_opening=(0.0, 0.0, 1.0),
        p_flare_bara=2.0,
    )
    text = render_genkey(spec)
    flat = re.sub(r"\s+", " ", text.replace("\\\n", " "))
    assert (
        "FP_BDV" not in text and "NODE_FLARE" not in text
    )  # default mode is the robust LEAK
    assert 'LEAK LABEL="BDV"' in flat and "PIPE=RIS_01" in flat
    assert (
        "CHECKVALVE" not in flat
    )  # CHECKVALVE=YES turns it into an internal leak (needs TOPOSITION)
    assert "TIME=(0, 630, 640) s" in flat and "BACKPRESSURE=(150, 150, 2) bara" in flat
    assert "GTLEAK" in flat and "TLEAEX" in flat


def test_comment_lines_are_never_wrapped():
    from olga_multiphase_simulator.casegen import wrap_genkey

    comment = "! " + "long comment, with commas, " * 12
    out = wrap_genkey([comment, "A " + ", ".join(["B=1"] * 60)]).splitlines()
    assert out[0] == comment
    assert any(line.endswith("\\") for line in out[1:])


def test_mesh_requires_sea_and_riser_pipes(route_json):
    spec = _spec(route_json)
    spec.mesh.pipes[:] = [p for p in spec.mesh.pipes if p.label.startswith("SEA")]
    with pytest.raises(ValueError):
        render_genkey(spec)


# ------------------------------------------------------------------------------------------------ comparison helper
def test_comparison_verdicts_follow_the_unsafe_direction():
    rows = [
        ComparisonRow(
            "peak pressure", "bara", neqsim=120.0, olga=80.0, higher_is_worse=True
        ),  # NeqSim higher -> conservative
        ComparisonRow(
            "peak pressure", "bara", neqsim=50.0, olga=80.0, higher_is_worse=True
        ),  # NeqSim lower -> non-conservative
        ComparisonRow(
            "time to hydrate", "h", neqsim=3.0, olga=6.0, higher_is_worse=False
        ),  # shorter time is worse -> conservative
        ComparisonRow(
            "time to hydrate", "h", neqsim=9.0, olga=6.0, higher_is_worse=False
        ),  # longer time -> non-conservative
        ComparisonRow("dp", "bar", neqsim=10.5, olga=10.0),  # within 25 %
        ComparisonRow(
            "zero", "-", neqsim=1.0, olga=0.0
        ),  # OLGA saw nothing, NeqSim predicted a slug
        ComparisonRow("missing", "-", neqsim=1.0, olga=float("nan")),
    ]
    assert [r.verdict.split(" (")[0] for r in rows] == [
        "NEQSIM CONSERVATIVE",
        "NEQSIM NON-CONSERVATIVE",
        "NEQSIM CONSERVATIVE",
        "NEQSIM NON-CONSERVATIVE",
        "CONSISTENT",
        "NEQSIM CONSERVATIVE",
        "NOT_COMPARABLE",
    ]
    assert rows[0].ratio == pytest.approx(1.5)
    assert compare_rows(rows) == {
        "conservative": 3,
        "non_conservative": 2,
        "consistent": 1,
        "not_comparable": 1,
    }


def test_comparison_renders_markdown_and_csv():
    rows = [
        ComparisonRow("slug volume", "m3", 4.6, 12.0, True, note="screening vs OLGA")
    ]
    md, csv_text = to_markdown(rows), to_csv(rows)
    assert md.splitlines()[0].startswith("| Item") and "NON-CONSERVATIVE" in md
    assert (
        csv_text.splitlines()[0].startswith("item,unit,neqsim,olga")
        and "slug volume" in csv_text
    )


def _periodic_signal(period=900.0, total=7200.0, dt=10.0, q_mean=0.01, amp=0.02):
    t = [i * dt for i in range(int(total / dt) + 1)]
    q = [
        q_mean + (amp if (ti % period) < 0.2 * period else -amp * 0.25) for ti in t
    ]  # short liquid surge each period
    return t, q


def test_slug_statistics_recover_period_and_surge_volume():
    t, q = _periodic_signal()
    p = [1.5e6 + 2e5 * (1 if (ti % 900.0) < 180 else 0) for ti in t]
    st = slug_statistics(t, q, p, area_m2=0.064, t_start_s=900.0)
    assert st["period_s"] == pytest.approx(900.0, rel=0.05)
    # surge: liquid above the mean over one 180 s burst: (q_hi - q_mean) * 180 s with q_hi = 0.03, mean ~0.01+...
    expected = (0.03 - st["mean_q_m3_h"] / 3600.0) * 180.0
    assert st["max_surge_volume_m3"] == pytest.approx(expected, rel=0.12)
    assert st["slug_length_m"] == pytest.approx(st["max_surge_volume_m3"] / 0.064)
    assert st["p_amplitude_bar"] == pytest.approx(2.0)
    assert st["peak_to_mean"] > 1.5


def test_slug_statistics_steady_flow_has_no_surge_and_no_period():
    t = [float(i * 10) for i in range(300)]
    st = slug_statistics(t, [0.02] * 300, area_m2=0.064)
    assert st["max_surge_volume_m3"] == pytest.approx(0.0, abs=1e-9)
    assert math.isnan(st["period_s"]) and st["peak_to_mean"] == pytest.approx(1.0)
    assert math.isnan(dominant_period(t[:4], [1, 2, 3, 4]))
