"""Offline tests for the pipeline overview and bathymetry helpers."""

import json

import pytest

from anp_open_data import (
    build_etopo_url,
    connect_pipelines,
    depth_at,
    fetch_etopo_grid,
    flag_slopes,
    load_cached_layers,
    node_register,
    pipeline_register,
    profile_along_route,
    summarise,
    write_csv,
)


def _fc(features):
    return {"type": "FeatureCollection", "features": features}


def _line(coords, **props):
    return {"type": "Feature", "geometry": {"type": "LineString", "coordinates": coords}, "properties": props}


def _pt(lon, lat, **props):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": props}


@pytest.fixture
def cache(tmp_path):
    sea = [[[-44, -27], [-40, -27], [-40, -23], [-44, -23], [-44, -27]]]
    land = [[[-48, -27], [-44, -27], [-44, -23], [-48, -23], [-48, -27]]]
    files = {
        "anp_wfs_sisroc_basin_shp_geoanp_x.geojson": _fc(
            [
                {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": sea},
                 "properties": {"NOME_BACIA": "Santos", "SITUAÇÃO": "Marítima"}},
                {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": land},
                 "properties": {"NOME_BACIA": "Land", "SITUAÇÃO": "Terrestre"}},
            ]
        ),
        "anp_wfs_geoanp_gasodutos_de_escoamento_x.geojson": _fc(
            [
                _line([[-42.0, -25.0], [-43.0, -24.5]], NOME_DUTO="ROTA A", NOME_OPER="OP", CP_NOMINAL="10"),
                _line([[-41.0, -25.5], [-43.0, -24.5]], NOME_DUTO="ROTA B"),
            ]
        ),
        "anp_wfs_geoanp_gasodutos_de_transporte_x.geojson": _fc(
            [_line([[-45.0, -24.0], [-46.0, -24.0]], DUTO="GASTRANS", DIAM_POL="28", EXTENS_KM="100,5")]
        ),
        "anp_wfs_geoanp_unidade_de_producao_x.geojson": _fc(
            [_pt(-42.0, -25.0, NOM_INSTALACAO="FPSO ONE", MED_DISTANCIA_LAMINA="2150", DESC_TIPO_UEP="FPSO")]
        ),
        "anp_wfs_geoanp_terminais_limite_x.geojson": _fc([_pt(-45.0, -24.0, TERMINAL_NOME="TERM")]),
    }
    for name, data in files.items():
        (tmp_path / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def test_overview_registers_and_connections(cache, tmp_path):
    layers = load_cached_layers(cache)
    assert set(layers) >= {"basins", "gas_outflow", "gas_transport", "platforms", "limit_terminals"}
    pipes = pipeline_register(layers)
    assert len(pipes) == 3
    gt = next(p for p in pipes if p["name"] == "GASTRANS")
    assert gt["diameter_in"] == 28.0 and gt["length_km_reported"] == 100.5
    assert gt["offshore_fraction"] == 0.0
    a = next(p for p in pipes if p["name"] == "ROTA A")
    assert a["offshore_fraction"] == 1.0
    nodes = node_register(layers)
    assert {n["kind"] for n in nodes} == {"platform", "limit_terminal"}
    assert nodes[0]["water_depth_m"] == 2150.0
    conns = connect_pipelines(pipes, nodes, snap_km=5.0)
    assert a["from_node"] == "platform_000"
    junctions = [n for n in conns["nodes"] if n["kind"] == "junction"]
    assert len(junctions) == 1 and junctions[0]["n_pipelines"] == 2
    s = summarise(pipes, conns)
    assert s["pipeline_count"] == 3
    assert s["offshore_pipelines"]["count"] == 2
    assert s["unnamed_endpoints"] == 2
    out = write_csv(tmp_path / "p.csv", pipes)
    assert "_parts" not in out.read_text(encoding="utf-8-sig").splitlines()[0]


def _erddap(lats, lons, f):
    rows = [[la, lo, f(la, lo)] for la in lats for lo in lons]
    return {"table": {"columnNames": ["latitude", "longitude", "altitude"], "rows": rows}}


def test_bathymetry_grid_profile_and_cache(tmp_path):
    lats = [-26.0, -25.5, -25.0]
    lons = [-43.0, -42.5, -42.0]
    raw = _erddap(lats, lons, lambda la, lo: -2000.0 - 200.0 * (lo + 43.0))
    calls = []

    def getter(url, timeout):
        calls.append(url)
        return json.dumps(raw).encode("utf-8")

    bbox = (-43.0, -42.0, -26.0, -25.0)
    assert "etopo180" in build_etopo_url(bbox)
    grid = fetch_etopo_grid(bbox, tmp_path, getter=getter)
    assert grid["status"] == "downloaded"
    assert depth_at(grid, -25.5, -42.75) == pytest.approx(2050.0)
    again = fetch_etopo_grid(bbox, tmp_path, offline=True)
    assert again["status"] == "cache" and len(calls) == 1
    prof = profile_along_route(grid, [(-43.0, -25.5), (-42.0, -25.5)], step_km=5.0)
    assert prof[0]["kp_km"] == 0.0 and prof[-1]["depth_m"] == pytest.approx(2200.0, abs=1.0)
    summ = flag_slopes(prof)
    assert summ["depth_max_m"] == pytest.approx(2200.0, abs=1.0)
    assert 0.0 < summ["max_slope_deg"] < 1.0
    assert summ["length_above_5deg_km"] == 0.0
    with pytest.raises(ValueError):
        depth_at(grid, -30.0, -42.5)
