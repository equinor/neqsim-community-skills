import json

import pytest

from ncs_infrastructure_network.build import build_snapshot, parse_capacity
from ncs_infrastructure_network.network import NcsNetwork
from ncs_infrastructure_network.open_api import (EntsogTransparency, SodirDataService, SodirFactPages,
                                                 summarise_entry_flows)
from ncs_infrastructure_network.sources import sources_for
from ncs_infrastructure_network.transport_parser import Gazetteer, parse_transport_text


# --------------------------------------------------------------------------- open API clients

def test_sodir_dataservice_pages_until_transfer_limit_clears():
    pages = [
        {"features": [{"attributes": {"id": 1}}, {"attributes": {"id": 2}}], "exceededTransferLimit": True},
        {"features": [{"attributes": {"id": 3}}]},
    ]
    urls = []

    def fetch(url, timeout):
        urls.append(url)
        return json.dumps(pages[len(urls) - 1]).encode()

    rows = SodirDataService(fetch, page_size=2).query("field")
    assert [r["id"] for r in rows] == [1, 2, 3]
    assert "7100/query" in urls[0] and "resultOffset=2" in urls[1]


def test_sodir_dataservice_raises_on_service_error():
    ds = SodirDataService(lambda url, t: json.dumps({"error": {"code": 400}}).encode())
    with pytest.raises(RuntimeError):
        ds.query("pipeline")
    assert ds.records[-1].ok is False


def test_factpages_csv_is_parsed():
    body = "\ufefffldName,fldHcType\nTROLL,GAS\n".encode("utf-8")
    rows = SodirFactPages(lambda url, t: body).table("field")
    assert rows == [{"fldName": "TROLL", "fldHcType": "GAS"}]


class _NotFound(Exception):
    code = 404


def test_entsog_404_is_empty_and_flows_convert_to_msm3():
    def fetch(url, timeout):
        if "ITP-00022" in url:
            return json.dumps({"operationaldatas": [
                {"directionKey": "entry", "value": 440_000_000, "periodFrom": "2026-09-01T06:00:00+02:00",
                 "operatorKey": "UK-TSO-0001"},
                {"directionKey": "exit", "value": 1, "periodFrom": "2026-09-01T06:00:00+02:00"}]}).encode()
        raise _NotFound()

    client = EntsogTransparency(fetch, gcv_kwh_per_sm3=11.0)
    rows = client.norwegian_entry_flows("2026-09-01", "2026-09-02")
    assert len(rows) == 1 and rows[0]["terminal"] == "ST.FERGUS"
    assert rows[0]["value_msm3_per_d"] == pytest.approx(40.0)
    summary = summarise_entry_flows(rows)
    assert summary["ST.FERGUS"]["mean_msm3_per_d"] == pytest.approx(40.0)
    assert all(r.ok for r in client.records)


def test_source_registry_separates_open_and_enterprise():
    assert all(s["tier"] == "open" for s in sources_for(tier="open"))
    assert any(s["owner_skill"] == "enterprise-pdm-api" for s in sources_for(tier="enterprise"))
    assert any(s["id"] == "entsog-transparency" for s in sources_for("flow"))


# --------------------------------------------------------------------------- parser

GAZ = Gazetteer.build({"ALVE": "ALVE", "NORNE": "NORNE", "BALDER": "BALDER", "JOTUN": "JOTUN"})


def test_parser_splits_oil_and_gas_clauses():
    text = ("The oil is offloaded from the Norne FPSO and the gas is transported via the Norne pipeline to "
            "the Åsgard Transport System (ÅTS) and further to the Kårstø terminal for export.")
    routes = {r.medium: r for r in parse_transport_text("ALVE", text, GAZ)}
    assert routes["liquid"].nodes == ["ALVE", "NORNE", "TANKER_EXPORT"]
    assert routes["gas"].nodes == ["ALVE", "NORNE", "ASGARD", "KARSTO"]


def test_parser_maps_statpipe_to_rich_gas_junction():
    text = ("The oil is transported by tankers. Excess gas from Balder and Ringhorne is exported from the Jotun "
            "FPSO through the Statpipe system to Kårstø and from there on to continental Europe.")
    gas = [r for r in parse_transport_text("BALDER", text, GAZ) if r.medium == "gas"][0]
    assert gas.nodes == ["BALDER", "JOTUN", "STATPIPE_RICH_GAS", "KARSTO"]


def test_parse_capacity_handles_ranges():
    assert parse_capacity("10–27") == (10.0, [10.0, 27.0])
    assert parse_capacity(46) == (46.0, None)
    assert parse_capacity(None) == (None, None)


# --------------------------------------------------------------------------- builder

def _raw_fixture():
    return {
        "field": [{"fldName": "ALPHA", "fldNpdidField": 1, "fldCurrentActivitySatus": "Producing",
                   "fldHcType": "GAS", "_geometry": {"rings": [[[2.0, 60.0], [2.2, 60.2], [2.0, 60.2]]]}}],
        "field_description": [{"fldNpdidField": 1, "fldDescriptionHeading": "Transport", "fldCultureCode": "en",
                               "fldDescriptionText": "The gas is exported to Kårstø."},
                              {"fldNpdidField": 1, "fldDescriptionHeading": "Transport", "fldCultureCode": "nb",
                               "fldDescriptionText": "Gassen eksporteres til Kollsnes."}],
        "field_reserves": [{"fldNpdidField": 1, "fldVersion": 2024, "fldRemainingGas": 10.0},
                           {"fldNpdidField": 1, "fldVersion": 2025, "fldRemainingGas": 8.0}],
        "profiles": [{"prfPeriod": "year", "prfYear": 2025, "prfNpdidInformationCarrier": 1,
                      "prfInformationCarrierKind": "FIELD", "prfPrdGasNetBillSm3": 3.65}],
        "gas_pipelines": [{"name": "Europipe II", "from": "Kårstø", "to": "Dornum (D)", "capacity_raw": 71,
                           "diameter_in": 42, "length_km": 660}],
        "oil_pipelines": [],
        "discovery": [], "discovery_reserves": [], "facility": [], "pipeline": [],
    }


def test_build_snapshot_from_fixture():
    snap = build_snapshot(_raw_fixture(), generated_utc="2026-01-01T00:00:00+00:00")
    net = NcsNetwork(snap)
    assert net.fields["ALPHA"]["reserves"]["remaining_gas_bsm3"] == 8.0  # latest version wins
    assert net.field_rate("ALPHA", 2025) == pytest.approx(10.0)  # 3.65 GSm3/yr = 10 MSm3/d
    ids = {a["id"] for a in snap["arcs"]}
    assert {"EUROPIPE_II_A", "EUROPIPE_II_B", "BALTIC_PIPE"} <= ids  # Europipe II split at Baltic Pipe
    path = net.preferred_path("ALPHA")
    assert path.nodes[:3] == ["ALPHA", "KARSTO", "EUROPIPE_II_BALTIC_TIE_IN"]  # English text only
    assert path.exit.startswith("MARKET_")
