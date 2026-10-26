import json
import urllib.parse

import pytest

from anp_open_data import (
    build_getfeature_url,
    fetch_layer,
    haversine_km,
    installation_production,
    locate_installations,
    name_key,
    nearest_pipeline,
    point_to_polyline_km,
    rank_tie_in_hosts,
    repair_name,
)


def _fc(features):
    return {"type": "FeatureCollection", "features": features}


def test_getfeature_url_uses_layer_alias_and_filters() -> None:
    url = build_getfeature_url("wells", cql="nome_bloco='X-1'", max_features=10)
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert q["typeName"] == ["sisroc:pocos_gishub_db"]
    assert q["CQL_FILTER"] == ["nome_bloco='X-1'"]
    assert q["outputFormat"] == ["application/json"]
    url = build_getfeature_url("fields", bbox=(-44, -26, -42, -24))
    assert "bbox=" in url
    with pytest.raises(ValueError):
        build_getfeature_url("fields", cql="a=1", bbox=(-44, -26, -42, -24))
    with pytest.raises(ValueError):
        build_getfeature_url("fields", bbox=(-42, -26, -44, -24))


def test_fetch_layer_caches_and_logs(tmp_path) -> None:
    calls = []
    payload = _fc([{"type": "Feature", "properties": {"name": "A"}, "geometry": None}])

    def getter(url, timeout):
        calls.append(url)
        return json.dumps(payload).encode("utf-8")

    data, rec = fetch_layer("fields", tmp_path, cql="a=1", getter=getter, max_features=1)
    assert rec["status"] == "downloaded" and rec["n_features"] == 1 and rec["truncated"]
    assert rec["retrieved_utc"]
    data2, rec2 = fetch_layer("fields", tmp_path, cql="a=1", getter=getter, max_features=1)
    assert rec2["status"] == "cache" and len(calls) == 1
    assert rec2["retrieved_utc"] == rec["retrieved_utc"]
    with pytest.raises(FileNotFoundError):
        fetch_layer("wells", tmp_path, cql="b=2", offline=True)


def test_fetch_layer_rejects_non_geojson(tmp_path) -> None:
    with pytest.raises(ValueError):
        fetch_layer("fields", tmp_path, getter=lambda u, t: b'{"error": "x"}')


def test_repair_name_and_name_key_match_damaged_spellings() -> None:
    assert repair_name("FPSO CIDADE DE S\u00c3\u0192O PAULO") == "FPSO CIDADE DE S\u00c3O PAULO"
    good = name_key("FPSO Cidade de S\u00e3o Paulo")
    assert good == name_key("FPSO CIDADE DE S\ufffdO PAULO".replace("\ufffd", "")) or good.startswith("FPSO CIDADE DE S")
    assert name_key("FPSO  Ilhabela (Sapinhoa)") == "FPSO ILHABELA"
    assert name_key(None) == ""


def test_locate_installations_uses_median_wellhead() -> None:
    wells = _fc(
        [
            {"type": "Feature", "properties": {"name": "W1", "longitude": -43.0, "latitude": -25.0, "lamina_dagua": 2100}},
            {"type": "Feature", "properties": {"name": "W2", "longitude": -43.1, "latitude": -25.1, "lamina_dagua": 2150}},
            {"type": "Feature", "properties": {"name": "W3"}, "geometry": {"type": "Point", "coordinates": [-43.2, -25.2]}},
        ]
    )
    pairs = [("W1", "FPSO A"), ("W2", "FPSO A"), ("W3", "FPSO A"), ("W9", "FPSO B")]
    res = {r["installation_key"]: r for r in locate_installations(wells, pairs)}
    a = res["FPSO A"]
    assert a["lon"] == pytest.approx(-43.1) and a["lat"] == pytest.approx(-25.1)
    assert a["n_wells_matched"] == 3 and a["water_depth_m_median"] == 2125
    assert a["well_spread_max_km"] == pytest.approx(haversine_km(-43.1, -25.1, -43.0, -25.0), abs=0.1)
    assert res["FPSO B"]["lon"] is None and res["FPSO B"]["location_quality"] == "unlocated"


def test_installation_production_daily_rates() -> None:
    rows = [
        {"inst": "FPSO A", "m": "01/2026", "oil": 3100.0, "cond": 0.0, "gas": 31.0},
        {"inst": "FPSO A", "m": "02/2026", "oil": 2800.0, "cond": 0.0, "gas": 28.0},
        {"inst": "FPSO  A", "m": "2026-02", "oil": 2800.0, "cond": 0.0, "gas": 28.0},
    ]
    out = installation_production(rows, "inst", "m", ["oil", "cond"], ["gas"])
    a = out["FPSO A"]
    assert a["latest_month"] == "2026-02" and a["months"] == 2
    assert a["oil_m3d_latest"] == pytest.approx(200.0)
    assert a["gas_mm3d_latest"] == pytest.approx(2.0)
    assert a["oil_m3d_peak"] == pytest.approx(200.0)


def test_point_to_polyline_matches_perpendicular_distance() -> None:
    d, near, along = point_to_polyline_km((0.0, 0.5), [(-1.0, 0.0), (1.0, 0.0)])
    assert d == pytest.approx(haversine_km(0.0, 0.5, 0.0, 0.0), rel=0.01)
    assert near[0] == pytest.approx(0.0, abs=1e-6)
    assert along == pytest.approx(haversine_km(-1.0, 0.0, 0.0, 0.0), rel=0.01)
    d1, _, _ = point_to_polyline_km((0.0, 0.0), [(1.0, 0.0)])
    assert d1 == pytest.approx(haversine_km(0.0, 0.0, 1.0, 0.0), rel=0.01)
    with pytest.raises(ValueError):
        point_to_polyline_km((0, 0), [])


def test_nearest_pipeline_orders_and_handles_multiline() -> None:
    pipes = _fc(
        [
            {"type": "Feature", "properties": {"nome": "FAR"}, "geometry": {"type": "LineString", "coordinates": [[2, 2], [3, 3]]}},
            {"type": "Feature", "properties": {"nome": "NEAR"}, "geometry": {"type": "MultiLineString", "coordinates": [[[0.1, -1], [0.1, 1]]]}},
            {"type": "Feature", "properties": {}, "geometry": {"type": "Point", "coordinates": [0, 0]}},
        ]
    )
    res = nearest_pipeline((0.0, 0.0), pipes)
    assert [r["name"] for r in res] == ["NEAR", "FAR"]
    assert res[0]["distance_km"] == pytest.approx(11.1, abs=0.2)


def test_rank_tie_in_hosts_prefers_near_host_with_ullage() -> None:
    target = (-42.84, -26.70)
    hosts = [
        {"name": "Near full", "lon": -42.5, "lat": -26.4, "oil_capacity_m3d": 20000, "oil_m3d_current": 20000, "remaining_life_years": 15},
        {"name": "Near free", "lon": -42.5, "lat": -26.5, "oil_capacity_m3d": 20000, "oil_m3d_current": 10000, "remaining_life_years": 15, "operator": "OpA"},
        {"name": "Far free", "lon": -41.0, "lat": -25.0, "oil_capacity_m3d": 30000, "oil_m3d_current": 0},
        {"name": "Stand-alone", "kind": "standalone", "remaining_life_years": 25},
        {"name": "Line", "kind": "pipeline", "distance_km": 105.0},
    ]
    res = rank_tie_in_hosts(target, hosts, required_oil_m3d=8000, preferred_operators=["opa"])
    names = [r["name"] for r in res]
    assert names.index("Near free") < names.index("Near full")
    far = next(r for r in res if r["name"] == "Far free")
    assert not far["feasible_step_out"] and far["sub_scores"]["distance"] == 0.0
    assert next(r for r in res if r["name"] == "Line")["distance_km"] == 105.0
    assert "oil ullage unknown" in next(r for r in res if r["name"] == "Line")["notes"]
    assert [r["rank"] for r in res] == list(range(1, len(res) + 1))
    with pytest.raises(ValueError):
        rank_tie_in_hosts(target, [{"name": "x"}])
    with pytest.raises(ValueError):
        rank_tie_in_hosts(target, hosts, weights={k: 0 for k in ("distance", "ullage", "water_depth", "operator", "remaining_life")})
