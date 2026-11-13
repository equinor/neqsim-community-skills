import json
import os
import urllib.parse

import pytest

from open_marine_constraints import MarineClient, SourceError, screen_earthquakes, screen_route, summary_rows
from open_marine_constraints.client import check_url
from open_marine_constraints.geometry import haversine_m, route_bbox, route_length_m
from open_marine_constraints.sources import ALLOWED_HOSTS, SOURCES, keys_for_theme

# Route along 60.5 N from 2.0 E to 2.5 E (about 27.6 km)
ROUTE = [(2.0, 60.5), (2.5, 60.5)]


def square(lon0, lat0, lon1, lat1):
    return {"type": "Polygon", "coordinates": [[[lon0, lat0], [lon1, lat0], [lon1, lat1], [lon0, lat1], [lon0, lat0]]]}


def feature(geometry, **props):
    return {"type": "Feature", "geometry": geometry, "properties": props}


class FakeServer:
    def __init__(self, routes):
        self.routes = routes
        self.urls = []

    def __call__(self, url, timeout, max_bytes):
        self.urls.append(url)
        for needle, payload in self.routes:
            if needle in url:
                body = payload(url) if callable(payload) else payload
                return json.dumps(body).encode("utf-8")
        raise AssertionError("unexpected url " + url)


def test_allow_list_rejects_other_hosts_and_http():
    with pytest.raises(SourceError):
        check_url("https://example.com/x")
    with pytest.raises(SourceError):
        check_url("http://gis.fiskeridir.no/x")
    for host in ALLOWED_HOSTS:
        check_url(f"https://{host}/x")
    for spec in SOURCES.values():
        check_url(spec["url"])


def test_wfs_bbox_is_latitude_first_urn():
    server = FakeServer([("emodnet", {"features": []})])
    MarineClient(server).features("eu_pipelines", (2.0, 60.0, 3.0, 61.0))
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(server.urls[0]).query)
    assert query["bbox"] == ["60.0,2.0,61.0,3.0,urn:ogc:def:crs:EPSG::4326"]
    assert query["typeNames"] == ["emodnet:pipelines"]


def test_arcgis_error_object_is_not_an_empty_layer():
    server = FakeServer([("Korallrev", {"error": {"code": 400, "message": "Invalid or missing input parameters."}})])
    with pytest.raises(SourceError, match="Invalid or missing"):
        MarineClient(server).features("no_coral_reef_ban", (2, 60, 3, 61))


def test_arcgis_paging_collects_all_pages_and_url_is_encoded():
    pages = [
        {"features": [feature(square(0, 0, 1, 1), navn=str(i)) for i in range(1000)], "exceededTransferLimit": True},
        {"features": [feature(square(0, 0, 1, 1), navn="last")]},
    ]
    state = {"n": 0}

    def payload(url):
        i = state["n"]
        state["n"] += 1
        return pages[i]

    server = FakeServer([("Korallrev", payload)])
    result = MarineClient(server).features("no_coral_reef_ban", (2, 60, 3, 61), max_features=5000)
    assert len(result.features) == 1001 and not result.truncated
    assert "%C3%A5" not in server.urls[0] and "Korallrev" in server.urls[0]
    server2 = FakeServer([("Marine_verneomr", {"features": []})])
    MarineClient(server2).features("no_marine_protected", (2, 60, 3, 61))
    assert "Marine_verneomr%C3%A5der" in server2.urls[0]


def test_polygon_line_and_point_screening():
    features = [
        feature(square(2.1, 60.45, 2.2, 60.55), navn="Zone A", mw_fshn=4.0),  # route runs through it
        feature(square(2.3, 60.60, 2.4, 60.70), navn="Zone B"),  # about 11 km north
        feature({"type": "LineString", "coordinates": [[2.3, 60.4], [2.3, 60.6]]}, name="Pipe 1"),  # crosses the route
        feature({"type": "Point", "coordinates": [2.45, 60.52]}, name="Wreck"),  # about 2.2 km off
    ]
    server = FakeServer([("emodnet", {"features": features})])
    client = MarineClient(server)
    result = screen_route(client, ROUTE, ["fishing_bottom_otter_trawls"], buffer_km=20.0)
    entry = result["layers"]["fishing_bottom_otter_trawls"]
    # Zone A is 0.1 deg of longitude wide at 60.5 N, which is 5.5 km
    assert entry["km_inside_polygons"] == pytest.approx(5.5, abs=0.5)
    assert entry["effort_mw_fishing_hours"]["max"] == 4.0
    assert entry["line_crossings"] == 1
    names = {e["name"]: e for e in entry["nearest"]}
    assert names["Wreck"]["distance_km"] == pytest.approx(2.2, abs=0.2)
    assert entry["intersecting"] == 2
    assert result["route_km"] == pytest.approx(route_length_m(ROUTE) / 1000.0, abs=0.01)
    assert result["errors"] == {} and result["provenance"]


def test_emodnet_effort_keeps_newest_period_only():
    def cell(period, validto, value):
        return feature(square(2.1, 60.45, 2.2, 60.55), c_squar="c1", avgyears=period, validto=validto, mw_fshn=value)

    old, new = cell("2015-2018", "2018-12-31Z", 20.0), cell("2021-2024", "2024-12-31Z", 7.0)
    server = FakeServer([("emodnet", {"features": [old, new]})])
    entry = screen_route(MarineClient(server), ROUTE, ["fishing_bottom_otter_trawls"])["layers"]["fishing_bottom_otter_trawls"]
    assert entry["features_in_box"] == 1 and entry["averaging_periods_used"] == ["2021-2024"]
    assert entry["effort_mw_fishing_hours"]["max"] == 7.0
    assert entry["km_inside_polygons"] == pytest.approx(5.5, abs=0.5)


def test_layer_failure_is_reported_not_fatal():
    server = FakeServer([("emodnet", {"features": []}), ("Korallrev", {"error": {"message": "boom"}})])
    result = screen_route(MarineClient(server), ROUTE, ["eu_pipelines", "no_coral_reef_ban"])
    assert "no_coral_reef_ban" in result["errors"] and "eu_pipelines" in result["layers"]
    assert result["layers"]["eu_pipelines"]["nearest_km"] is None


def test_raster_sampling_uses_identify():
    def identify(url):
        lon = float(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)["geometry"][0].split(",")[0])
        if lon < 2.25:
            return {"results": [{"attributes": {"Classify.Pixel Value": "7", "Classify.Class value": "1"}}]}
        return {"results": [{"attributes": {"Stretch.Pixel Value": "NoData"}}]}

    server = FakeServer([("identify", identify)])
    result = screen_route(MarineClient(server), ROUTE, ["no_bottom_trawl_intensity"], raster_step_km=5.0)
    entry = result["layers"]["no_bottom_trawl_intensity"]
    assert 0.3 < entry["fraction_with_data"] < 0.7
    assert entry["class_values_seen"] == ["1"] and entry["max_pixel_value"] == 7.0
    assert summary_rows(result)[0]["layer"] == "no_bottom_trawl_intensity"


def test_single_point_and_earthquakes():
    quake = {"type": "Feature", "geometry": {"type": "Point", "coordinates": [2.1, 60.6, 10]}, "properties": {"mag": 5.1, "place": "North Sea", "time": 0}}
    server = FakeServer([("fdsnws", {"features": [quake]})])
    result = screen_earthquakes(MarineClient(server), [(2.0, 60.5)], radius_km=50.0)
    assert result["events_within_radius"] == 1 and result["max_magnitude"] == 5.1
    assert result["strongest"][0]["year"] == 1970


def test_geometry_helpers_and_registry():
    assert haversine_m((0, 0), (1, 0)) == pytest.approx(111195, rel=1e-3)
    box = route_bbox(ROUTE, 10.0)
    assert box[0] < 2.0 and box[2] > 2.5 and box[1] < 60.5 < box[3]
    assert {"fishing", "environment", "grid", "wind"} <= {s["theme"] for s in SOURCES.values()}
    assert keys_for_theme("grid") == sorted(k for k in SOURCES if k.startswith("no_grid"))


@pytest.mark.skipif(not os.environ.get("NEQSIM_SKILLS_LIVE"), reason="live network test")
def test_live_services_answer_for_a_north_sea_route():
    route = [(2.0, 60.5), (3.2, 60.6)]
    keys = [k for k, s in SOURCES.items() if s["theme"] in {"fishing", "infrastructure", "wind", "hazard"} and k.startswith(("eu_", "fishing_", "no_bottom"))]
    result = screen_route(MarineClient(), route, keys, buffer_km=20.0, raster_step_km=20.0)
    assert result["errors"] == {}, result["errors"]
    assert result["layers"]["fishing_bottom_otter_trawls"]["features_in_box"] > 0
