import math

import pytest

from subsea_equipment_placement import (
    Limit, Line, PlacementBasis, Structure, Target, Zone, candidate_grid, rank_sites, screen_route, screen_site, to_geojson,
    polyline_crossings, point_polygon_distance, to_local, to_lonlat, slope_deg,
)

SUPPLIED = lambda v, u="m": Limit(v, u, "test basis", "SUPPLIED")
SQUARE = [(-500.0, -500.0), (500.0, -500.0), (500.0, 500.0), (-500.0, 500.0)]


def test_local_roundtrip():
    x, y = to_local(2.7954, 60.3897, 2.6117, 60.2893)
    lon, lat = to_lonlat(x, y, 2.6117, 60.2893)
    assert lon == pytest.approx(2.7954, abs=1e-9) and lat == pytest.approx(60.3897, abs=1e-9)
    assert math.hypot(x, y) == pytest.approx(15000.0, rel=0.02)


def test_crossing_angle_and_chainage():
    hits = polyline_crossings([(0.0, 0.0), (1000.0, 0.0)], [(400.0, -100.0), (600.0, 100.0)])
    assert len(hits) == 1
    assert hits[0][0] == pytest.approx(500.0)
    assert hits[0][1] == pytest.approx(45.0)


def test_polygon_distance_inside_and_outside():
    assert point_polygon_distance((0.0, 0.0), SQUARE) == 0.0
    assert point_polygon_distance((800.0, 0.0), SQUARE) == pytest.approx(300.0)


def test_unapproved_limit_never_passes_or_fails():
    basis = PlacementBasis(structures=[Structure("S1", (100.0, 0.0))], limits={"structure_clearance_m": Limit(200.0, "m", "", "ASSUMED")})
    r = screen_site((0.0, 0.0), basis)
    row = next(c for c in r["checks"] if c["id"] == "STRUCT")
    assert row["status"] == "NEEDS_REVIEW" and row["indicative"] == "FAIL"
    assert r["verdict"] == "NEEDS_REVIEW" and r["hard_fail"] == []


def test_supplied_limit_fails_hard():
    basis = PlacementBasis(zones=[Zone("Z", SQUARE)], limits={"zone_clearance_m": SUPPLIED(50.0)})
    assert screen_site((0.0, 0.0), basis)["hard_fail"] == ["ZONE"]
    assert screen_site((700.0, 0.0), basis)["verdict"] == "PASS"


def test_slope_and_reach_checks():
    depth = lambda x, y: 100.0 + 0.1 * x   # 5.71 degrees
    assert slope_deg(depth, (0.0, 0.0), 50.0) == pytest.approx(math.degrees(math.atan(0.1)), rel=1e-6)
    basis = PlacementBasis(depth_fn=depth, targets=[Target("T", (3000.0, 0.0), 3000.0)],
                           limits={"max_slope_deg": SUPPLIED(3.0, "deg"), "max_erd_ratio": SUPPLIED(1.5, "-")})
    r = screen_site((0.0, 0.0), basis)
    assert set(r["hard_fail"]) == {"SLOPE"}      # ERD ratio 1.0 passes
    basis.limits["max_erd_ratio"] = SUPPLIED(0.5, "-")
    assert "ERD" in screen_site((0.0, 0.0), basis)["hard_fail"]


def test_missing_data_is_not_assessed():
    r = screen_site((0.0, 0.0), PlacementBasis(depth_fn=lambda x, y: 100.0))
    assert next(c for c in r["checks"] if c["id"] == "SLOPE")["status"] == "NEEDS_REVIEW"
    assert screen_site((0.0, 0.0), PlacementBasis())["checks"] == []


def test_route_crossings_zone_entry_and_parallel_clearance():
    existing = Line("P1", [(5000.0, -2000.0), (5000.0, 2000.0)], status="existing")
    parallel = Line("P2", [(0.0, 60.0), (10000.0, 60.0)])
    zone = Zone("OSS", [(9000.0, -500.0), (10500.0, -500.0), (10500.0, 500.0), (9000.0, 500.0)])
    basis = PlacementBasis(lines=[existing, parallel], zones=[zone],
                           limits={"min_crossing_angle_deg": SUPPLIED(30.0, "deg"), "line_clearance_m": SUPPLIED(100.0), "max_crossings": SUPPLIED(0.0, "-")})
    r = screen_route([(0.0, 0.0), (10000.0, 0.0)], basis)
    ids = {c["id"]: c for c in r["checks"]}
    assert r["crossings"][0]["angle_deg"] == pytest.approx(90.0)
    assert ids["XANGLE"]["status"] == "PASS"
    assert ids["XCOUNT"]["status"] == "FAIL"                  # one crossing against a limit of zero
    assert ids["PARALLEL"]["status"] == "FAIL"                # P2 runs 60 m away
    assert ids["ZONEENTRY"]["status"] == "FAIL"               # enters the host zone without declaring it terminal
    r2 = screen_route([(0.0, 0.0), (10000.0, 0.0)], basis, terminal_zone_ids=["OSS"])
    assert {c["id"]: c for c in r2["checks"]}["ZONEENTRY"]["status"] == "PASS"


def test_rank_sites_orders_by_score_and_puts_failures_last():
    host = Structure("HOST", (10000.0, 0.0), "host")
    basis = PlacementBasis(host=host, targets=[Target("T", (0.0, 0.0), 3000.0)], zones=[Zone("BAD", [(3900.0, -100.0), (4100.0, -100.0), (4100.0, 100.0), (3900.0, 100.0)])],
                           limits={"zone_clearance_m": SUPPLIED(10.0)})
    sites = [(0.0, 0.0), (4000.0, 0.0), (2000.0, 0.0)]
    ranked = rank_sites(sites, basis)
    assert [r["site"] for r in ranked][-1] == (4000.0, 0.0)
    assert ranked[-1]["verdict"] == "FAIL"
    assert ranked[0]["score"] <= ranked[1]["score"]
    gj = to_geojson(ranked, (2.6, 60.3))
    assert len(gj["features"]) == 3


def test_candidate_grid_region():
    pts = candidate_grid((0.0, 0.0), 400.0, 200.0, SQUARE)
    assert len(pts) == 25
    assert len(candidate_grid((0.0, 0.0), 400.0, 200.0, [(-100.0, -100.0), (100.0, -100.0), (100.0, 100.0), (-100.0, 100.0)])) == 1


def test_documented_example_runs():
    origin = (2.6117, 60.2893)
    xy = lambda lon, lat: to_local(lon, lat, *origin)
    approved = lambda v, u="m": Limit(v, u, "project design basis rev A", "SUPPLIED")
    basis = PlacementBasis(
        host=Structure("HOST", xy(2.7954, 60.3897), "host"),
        lines=[Line("Existing gas export", [xy(2.69, 60.36), xy(2.74, 60.42)], "pipeline", "existing", "gas")],
        zones=[Zone("HOST-500m", [xy(2.78, 60.385), xy(2.79, 60.385), xy(2.79, 60.395), xy(2.78, 60.395)], "Safety Zone")],
        targets=[Target("T1", (-1800.0, 0.0), 3100.0), Target("T2", (1800.0, 0.0), 3100.0)],
        depth_fn=lambda x, y: 100.0,
        limits={"zone_clearance_m": approved(50.0), "max_slope_deg": Limit(3.0, "deg", "", "ASSUMED")},
    )
    sites = candidate_grid((0.0, 0.0), 600.0, 100.0)
    ranked = rank_sites(sites, basis, route_fn=lambda s: [s, basis.host.point])
    assert len(ranked) == 169
    route = screen_route([ranked[0]["site"], basis.host.point], basis, terminal_zone_ids=["HOST-500m"])
    assert route["verdict"] in ("PASS", "NEEDS_REVIEW", "FAIL")


def test_soft_zone_entry_is_listed_not_failed():
    soft = Zone("ORANGE", [(4000.0, -300.0), (6000.0, -300.0), (6000.0, 300.0), (4000.0, 300.0)], "Orange Caution Zone", hard=False)
    r = screen_route([(0.0, 0.0), (10000.0, 0.0)], PlacementBasis(zones=[soft]))
    assert r["zones_entered"] == [{"id": "ORANGE", "type": "Orange Caution Zone", "hard": False}]
    assert next(c for c in r["checks"] if c["id"] == "ZONEENTRY")["status"] == "PASS"
