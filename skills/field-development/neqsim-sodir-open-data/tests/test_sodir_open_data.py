import json
import re
from urllib.parse import parse_qs, urlparse

import pytest

from sodir_open_data import (
    BULK_DATASETS, USE_CASES, SodirOpenData, bulk_download_url, describe, factpages_table_url, field_names,
    items, resolve_id, search, sql_quote, to_date, use_case,
)
from sodir_open_data.client import point_lonlat, to_float


def test_catalog_covers_all_categories():
    ids = {int(i["id"]) for i in items()}
    assert len(ids) >= 100
    assert {i // 1000 for i in ids} >= {1, 2, 3, 4, 5, 6, 7, 9}
    assert resolve_id("wellbore") == 5000 and resolve_id("7113") == 7113 and resolve_id(9001) == 9001


def test_search_and_describe():
    hits = search("wellbore drill stem test")
    assert hits and hits[0]["name"] == "wellbore_dst"
    text = describe("field_reserves")
    assert "fldRecoverableOil" in text and "field_reserves" in text
    assert "wlbNpdidWellbore" in field_names("wellbore_dst")
    with pytest.raises(KeyError):
        resolve_id("no_such_layer")


def test_guides_reference_real_layers_and_keys():
    known_ids = {int(i["id"]) for i in items()}
    all_fields = {f["name"] for i in items() for f in i.get("fields", [])}
    for topic, spec in USE_CASES.items():
        for layer in spec["layers"]:
            for number in re.findall(r"\((\d{4})", layer):
                assert int(number) in known_ids, (topic, layer)
        for key in spec["join_keys"]:
            assert key in all_fields, (topic, key)
    assert use_case("pvt")["topic"] == "pvt_and_reservoir_data"
    assert use_case("wellbores")["gotchas"]
    with pytest.raises(KeyError):
        use_case("zzz")


def test_urls():
    assert bulk_download_url("wlbPoint") == "https://factpages.sodir.no/downloads/csv/wlbPoint.zip"
    assert bulk_download_url("fldArea", "shape").endswith("/shape/fldArea.zip")
    assert "tableview/field_reserves&" in factpages_table_url("field_reserves")
    assert "pipLine" in BULK_DATASETS
    with pytest.raises(KeyError):
        bulk_download_url("nope")


class FakeSodir:
    def __init__(self, total=5):
        self.urls = []
        self.total = total

    def __call__(self, url, timeout):
        self.urls.append(url)
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        if q.get("returnCountOnly"):
            return json.dumps({"count": self.total}).encode()
        if q.get("returnDistinctValues"):
            return json.dumps({"features": [{"attributes": {"wlbPurpose": v}} for v in ("WILDCAT", "APPRAISAL", "WILDCAT")]}).encode()
        offset, take = int(q["resultOffset"]), int(q["resultRecordCount"])
        rows = [{"attributes": {"id": n}, "geometry": {"x": 1.0, "y": 60.0}} for n in range(self.total)][offset:offset + take]
        return json.dumps({"features": rows, "exceededTransferLimit": offset + take < self.total}).encode()


def test_query_pages_and_bbox_and_geometry():
    fake = FakeSodir(total=5)
    client = SodirOpenData(fake, page_size=2)
    rows = client.query("wellbore", "wlbPurpose='WILDCAT'", geometry=True, out_sr=4326, bbox=(1, 59, 3, 61))
    assert [r["id"] for r in rows] == [0, 1, 2, 3, 4]
    assert point_lonlat(rows[0]) == (1.0, 60.0)
    first = fake.urls[0]
    assert "/5000/query" in first and "outSR=4326" in first and "esriGeometryEnvelope" in first and "inSR=4326" in first
    assert len(fake.urls) == 3
    assert client.provenance()[0]["rows"] == 5 and "NLOD" in client.provenance()[0]["licence"]


def test_max_rows_count_distinct():
    client = SodirOpenData(FakeSodir(total=10), page_size=4)
    assert len(client.query(7100, max_rows=6)) == 6
    assert client.count("field") == 10
    assert client.distinct("wellbore", "wlbPurpose") == ["APPRAISAL", "WILDCAT"]


def test_service_error_raises():
    def bad(url, timeout):
        return json.dumps({"error": {"code": 400, "message": "bad where"}}).encode()

    client = SodirOpenData(bad)
    with pytest.raises(RuntimeError):
        client.query("field", "oops")
    assert client.records[-1].ok is False


def test_factpages_csv_and_helpers():
    csv_bytes = "\ufefffldName,fldRecoverableOil\nTROLL,12.5\n".encode("utf-8")
    client = SodirOpenData(lambda url, timeout: csv_bytes)
    rows = client.factpages_table("field_reserves")
    assert rows == [{"fldName": "TROLL", "fldRecoverableOil": "12.5"}]
    assert to_float("1,5") == 1.5 and to_float("") is None
    assert sql_quote("O'Brien") == "'O''Brien'"
    assert to_date(0).year == 1970 and to_date(None) is None
