import pytest

from field_layout_import import FieldLayoutImporter


def _feature(name, x, y, depth=None, kind=None):
    properties = {"name": name}
    if depth is not None:
        properties["water_depth_m"] = depth
    if kind is not None:
        properties["kind"] = kind
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [x, y]},
        "properties": properties,
    }


def test_imports_geojson_points() -> None:
    geojson = {
        "type": "FeatureCollection",
        "features": [
            _feature("Host", 0.0, 0.0, 120.0, "host"),
            _feature("W1", 8000.0, 1500.0, 340.0, "well"),
        ],
    }
    result = FieldLayoutImporter().from_geojson(geojson)

    assert result.node_count == 2
    assert result.nodes[0].name == "Host"
    assert result.nodes[1].x == pytest.approx(8000.0)


def test_missing_depth_defaulted_with_issue() -> None:
    geojson = {
        "type": "FeatureCollection",
        "features": [
            _feature("Host", 0.0, 0.0, 120.0, "host"),
            _feature("W1", 8000.0, 1500.0, None, "well"),
        ],
    }
    result = FieldLayoutImporter().from_geojson(geojson)

    assert result.nodes[1].water_depth_m == 0.0
    assert any("missing water_depth_m" in issue for issue in result.issues)


def test_unknown_kind_normalized() -> None:
    geojson = {
        "type": "FeatureCollection",
        "features": [_feature("M1", 100.0, 100.0, 200.0, "drilling-centre")],
    }
    result = FieldLayoutImporter().from_geojson(geojson)

    assert result.nodes[0].kind == "well"
    assert any("unknown kind" in issue for issue in result.issues)


def test_non_point_feature_skipped() -> None:
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
                "properties": {"name": "Route"},
            },
            _feature("Host", 0.0, 0.0, 120.0, "host"),
        ],
    }
    result = FieldLayoutImporter().from_geojson(geojson)

    assert result.node_count == 1
    assert any("not a Point" in issue for issue in result.issues)


def test_from_rows_with_lon_lat() -> None:
    rows = [
        {"name": "Host", "longitude": 2.0, "latitude": 60.0, "water_depth_m": 120.0, "kind": "host"},
        {"name": "W1", "longitude": 2.1, "latitude": 60.1, "water_depth_m": 340.0},
    ]
    result = FieldLayoutImporter().from_rows(rows)

    assert result.node_count == 2
    assert result.nodes[0].x == pytest.approx(2.0)
    assert result.nodes[1].kind == "well"


def test_duplicate_name_flagged() -> None:
    geojson = {
        "type": "FeatureCollection",
        "features": [
            _feature("W1", 0.0, 0.0, 100.0, "well"),
            _feature("W1", 100.0, 100.0, 200.0, "well"),
        ],
    }
    result = FieldLayoutImporter().from_geojson(geojson)

    assert any("duplicate node name" in issue for issue in result.issues)


def test_rejects_non_dict_geojson() -> None:
    with pytest.raises(ValueError, match="already-parsed dict"):
        FieldLayoutImporter().from_geojson([])
