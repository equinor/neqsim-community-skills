"""Tests for CRS and datum checks."""

from __future__ import annotations

import json

import pytest

from crs_checks import (
    AmbiguousOperationError,
    CrsError,
    axis_check,
    datum_sensitivity,
    geojson_check,
    projection_factors,
    route_lengths,
    run_crs_check,
    transform,
)
from crs_checks.__main__ import main

NORTH_SEA = (2.610422, 60.290422)  # lon, lat on ED50, south of 62 N


def test_named_datum_operation_and_refusals():
    north = transform([(2.5, 63.5)], "EPSG:4230", "EPSG:4326", "EPSG:1612")
    assert north.coordinates[0] == pytest.approx(
        (2.49818, 63.49961), abs=1e-5
    )  # geodetic-engine README value
    assert "ED50 to WGS 84 (23)" in north.operation and north.accuracy_m == 1.0
    assert "helmert" in north.pipeline
    with pytest.raises(AmbiguousOperationError):
        transform([NORTH_SEA], "EPSG:4230", "EPSG:4326")
    with pytest.raises(CrsError, match="outside"):
        transform([NORTH_SEA], "EPSG:4230", "EPSG:4326", "EPSG:1612")
    south = transform([NORTH_SEA], "EPSG:4230", "EPSG:4326", "EPSG:1613")
    assert "ED50 to WGS 84 (24)" in south.operation
    no_datum_change = transform([(500000.0, 6680000.0)], "EPSG:32631", "EPSG:4326")
    assert no_datum_change.coordinates[0][0] == pytest.approx(3.0, abs=1e-9)


def test_axis_and_geojson_checks():
    assert any(
        "swapped" in f for f in axis_check([(NORTH_SEA[1], NORTH_SEA[0])], "EPSG:4230")
    )
    assert axis_check([NORTH_SEA], "EPSG:4230") == []
    assert any("degrees" in f for f in axis_check([NORTH_SEA], "EPSG:23031"))
    assert any(
        "160-840 km" in f for f in axis_check([(950000.0, 6680000.0)], "EPSG:23031")
    )
    projected = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [478460.0, 6683976.0]},
    }
    assert any("projected" in f for f in geojson_check(projected))
    named = {
        "type": "FeatureCollection",
        "crs": {"properties": {"name": "EPSG:23031"}},
        "features": [],
    }
    assert any("not RFC 7946" in f for f in geojson_check(named))


def test_datum_sensitivity_factors_and_route_length():
    numbers = [(478460.0, 6683976.0)]
    sens = datum_sensitivity(
        numbers, ["EPSG:23031", "EPSG:32631", "EPSG:25831"], {"EPSG:23031": "EPSG:1613"}
    )
    pairs = {(p["a"], p["b"]): p["max_shift_m"] for p in sens["pairs"]}
    assert 150 < pairs[("EPSG:23031", "EPSG:32631")] < 300
    assert pairs[("EPSG:32631", "EPSG:25831")] < 1.0
    factors = projection_factors("EPSG:32631", 3.0, 60.0)
    assert factors["meridian_convergence_deg"] == pytest.approx(0.0, abs=1e-9)
    assert factors["meridional_scale"] == pytest.approx(0.9996, abs=1e-6)
    lengths = route_lengths(
        [(500000.0, 6680000.0), (500000.0, 6700000.0)], "EPSG:32631"
    )
    assert lengths["difference_ppm"] == pytest.approx(-400.0, abs=5.0)


def test_workflow_statuses_and_cli(tmp_path, capsys):
    ok = run_crs_check(
        {
            "points": [{"name": "w", "x": NORTH_SEA[0], "y": NORTH_SEA[1]}],
            "crs": "EPSG:4230",
            "target_crs": "EPSG:4326",
            "operation": "EPSG:1613",
        }
    )
    assert ok["status"] == "ok" and ok["results"]["transform"]["accuracy_m"] == 1.0
    attention = run_crs_check(
        {
            "points": [{"x": 478460.0, "y": 6683976.0}],
            "crs": "EPSG:32631",
            "datum_candidates": ["EPSG:23031", "EPSG:32631"],
            "out_dir": str(tmp_path),
        }
    )
    assert (
        attention["status"] == "attention"
        and "datum must be confirmed" in attention["findings"][0]
    )
    assert (tmp_path / "crs_check_evidence.json").exists()
    blocked = run_crs_check({"points": [{"x": 1.0, "y": 2.0}]})
    assert blocked["status"] == "blocked"
    assert (
        main(
            [
                "transform",
                "EPSG:4230",
                "EPSG:4326",
                str(NORTH_SEA[0]),
                str(NORTH_SEA[1]),
                "--operation",
                "EPSG:1613",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["accuracy_m"] == 1.0
    assert (
        main(
            [
                "transform",
                "EPSG:4230",
                "EPSG:4326",
                str(NORTH_SEA[0]),
                str(NORTH_SEA[1]),
            ]
        )
        == 2
    )
