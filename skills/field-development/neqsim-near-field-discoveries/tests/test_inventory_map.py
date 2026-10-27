import json

import pytest

from near_field_discoveries import Discovery, area_clusters, near_field, plot_near_field
from near_field_discoveries.geo import cluster_points, haversine_km, point_in_rings, point_to_rings_km


def rec(name, lon, lat, stage="not_evaluated", oe=None, kind="discovery", rings=None):
    return Discovery(country="NO", id=name, name=name, kind=kind, stage=stage, lon=lon, lat=lat,
                     volumes={"oe_msm3": oe} if oe is not None else {}, rings=rings or [], source="test", gaps=["gap A"])


HOSTS = [{"name": "Host 1", "lon": 2.0, "lat": 60.0, "kind": "FPSO"}, {"name": "Host 2", "lon": 3.0, "lat": 60.5}]
RECORDS = [
    rec("Near", 2.1, 60.0, "in_clarification", 20.0),
    rec("Mid", 2.3, 60.1, "not_evaluated"),
    rec("Far", 6.0, 62.0, "producing"),
    rec("Poly", 2.0, 59.8, "in_development", 5.0, kind="field",
        rings=[[(1.95, 59.75), (2.05, 59.75), (2.05, 59.85), (1.95, 59.85), (1.95, 59.75)]]),
]


def test_geometry_helpers() -> None:
    ring = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]
    assert point_in_rings(0.5, 0.5, [ring])
    assert point_to_rings_km(0.5, 0.5, [ring]) == 0.0
    d = point_to_rings_km(2.0, 0.5, [ring])
    assert abs(d - haversine_km(2.0, 0.5, 1.0, 0.5)) < 1.0
    assert cluster_points([(0, 0), (0.01, 0), (5, 5)], 5.0) == [[0, 1], [2]]


def test_near_field_filters_ranks_and_attaches_hosts() -> None:
    inv = near_field((2.0, 60.0), 60.0, RECORDS, name="T", hosts=HOSTS)
    assert [r.name for r in inv.records] == ["Near", "Poly", "Mid"]
    near = next(r for r in inv.records if r.name == "Near")
    assert near.nearest_hosts[0]["name"] == "Host 1"
    assert near.bearing == "E"
    assert "Far" not in [r.name for r in inv.records]
    assert RECORDS[0].distance_km is None  # inputs untouched
    s = inv.summary()
    assert s["n_discoveries"] == 2 and s["n_fields"] == 1
    assert s["stages"]["in_clarification"]["oe_msm3_sum"] == 20.0
    assert s["stages"]["not_evaluated"]["n_without_volume"] == 1


def test_clusters_sum_known_volumes() -> None:
    inv = near_field((2.0, 60.0), 60.0, RECORDS, hosts=HOSTS)
    clusters = area_clusters(inv.records, link_km=30.0)
    both = next(c for c in clusters if len(c["members"]) == 2)
    assert set(both["members"]) == {"Near", "Mid"}
    assert both["oe_msm3_sum"] == 20.0 and both["n_without_volume"] == 1


def test_outputs_csv_geojson_and_map(tmp_path) -> None:
    inv = near_field((2.0, 60.0), 60.0, RECORDS, name="Target X", hosts=HOSTS,
                     pipelines=[{"name": "P", "medium": "Gas", "parts": [[(2.0, 60.0), (2.2, 60.1)]]}])
    paths = inv.write(tmp_path)
    gj = json.loads((tmp_path / "near_field_discoveries.geojson").read_text(encoding="utf-8"))
    roles = {f["properties"]["role"] for f in gj["features"]}
    assert {"target", "study_radius", "discovery", "field", "host", "pipeline"} <= roles
    assert "Target X" in (tmp_path / "near_field_discoveries.md").read_text(encoding="utf-8")
    assert (tmp_path / "near_field_discoveries.csv").read_text(encoding="utf-8-sig").startswith("country,kind,name")
    assert set(paths) == {"csv", "json", "geojson", "markdown"}


def test_prospect_records_are_listed_apart_and_drawn(tmp_path) -> None:
    pytest.importorskip("matplotlib")
    recs = RECORDS + [rec("Prospect P", 2.2, 59.9, "unknown", kind="prospect")]
    inv = near_field((2.0, 60.0), 60.0, recs, hosts=HOSTS)
    s = inv.summary()
    assert s["n_prospects"] == 1 and s["n_discoveries"] == 2
    assert plot_near_field(inv, tmp_path / "p.png", dpi=50).exists()


def test_map_is_written(tmp_path) -> None:
    pytest.importorskip("matplotlib")
    inv = near_field((2.0, 60.0), 60.0, RECORDS, name="Target X", hosts=HOSTS,
                     pipelines=[{"name": "P", "medium": "Gas", "parts": [[(2.0, 60.0), (2.2, 60.1)]]}])
    png = plot_near_field(inv, tmp_path / "map.png", dpi=60,
                          bathymetry={"lats": [59.0, 61.0], "lons": [1.0, 4.0], "z": [[-100.0, -200.0], [-300.0, -400.0]]})
    assert png.exists() and png.stat().st_size > 5000
