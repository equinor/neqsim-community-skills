import json
import urllib.parse
from datetime import date

import pytest

from ncs_ownership_equity import OwnershipError, OwnershipReader, portfolio_net
from ncs_ownership_equity.sodir import SodirClient, sql_quote, to_date


def ms(y, m, d):
    from datetime import datetime, timezone
    return int((datetime(y, m, d, tzinfo=timezone.utc) - datetime(1970, 1, 1, tzinfo=timezone.utc)).total_seconds() * 1000)


def make_fetch(layers):
    """Serve canned rows per layer id and ignore the where clause (the reader filters again)."""
    calls = []

    def fetch(url, timeout):
        calls.append(url)
        layer = int(url.split("/MapServer/")[1].split("/")[0])
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        offset = int(query["resultOffset"][0])
        size = int(query["resultRecordCount"][0])
        rows = layers.get(layer, [])
        page = rows[offset:offset + size]
        payload = {"features": [{"attributes": r} for r in page]}
        if offset + size < len(rows):
            payload["exceededTransferLimit"] = True
        return json.dumps(payload).encode("utf-8")

    fetch.calls = calls
    return fetch


def lic(pid, name, company, cid, pct, start, end=None, oper=False):
    return {"prlNpdidLicence": pid, "prlName": name, "cmpLongName": company, "cmpNpdidCompany": cid,
            "prlLicenseeInterest": pct, "prlLicenseeSdfi": None, "prlLicenseeDateValidFrom": start,
            "prlLicenseeDateValidTo": end, "prlOperDateValidFrom": ms(2020, 1, 1) if oper else None,
            "prlOperDateValidTo": None, "prlLicenseeDateUpdated": ms(2026, 2, 1)}


def fld(fid, name, company, cid, pct, start, end=None, owner=("BUSINESS ARRANGEMENT AREA", "ALPHA UNIT")):
    return {"fldNpdidField": fid, "fldName": name, "cmpLongName": company, "cmpNpdidCompany": cid,
            "fldCompanyShare": pct, "fldSdfiShare": None, "fldLicenseeFrom": start, "fldLicenseeTo": end,
            "fldOwnerKind": owner[0], "fldOwnerName": owner[1], "fldLicenseeDateUpdated": ms(2026, 2, 1)}


LAYERS = {
    7100: [{"fldNpdidField": 1, "fldName": "ALPHA", "cmpLongName": "Opco AS", "cmpNpdidCompany": 10}],
    7108: [
        fld(1, "ALPHA", "Opco AS", 10, 60.0, ms(2020, 1, 1)),
        fld(1, "ALPHA", "Partner AS", 20, 40.0, ms(2020, 1, 1)),
        fld(1, "ALPHA", "Opco AS", 10, 50.0, ms(2010, 1, 1), ms(2019, 12, 31)),
        fld(1, "ALPHA", "Oldco AS", 30, 50.0, ms(2010, 1, 1), ms(2019, 12, 31)),
    ],
    7110: [{"fldNpdidField": 1, "cmpNpdidCompany": 10, "cmpLongName": "Opco AS",
            "fldOperatorFrom": ms(2010, 1, 1), "fldOperatorTo": None}],
    7000: [
        {"dscNpdidDiscovery": 100, "dscName": "1/1-1 Beta", "fldName": None, "cmpLongName": "Opco AS",
         "cmpNpdidCompany": 10, "dscCurrentActivityStatus": "Evaluation"},
        {"dscNpdidDiscovery": 200, "dscName": "2/2-2 Gamma", "fldName": "ALPHA", "cmpLongName": "Opco AS",
         "cmpNpdidCompany": 10, "dscCurrentActivityStatus": "Producing"},
        {"dscNpdidDiscovery": 300, "dscName": "3/3-3 Beta North", "fldName": None, "cmpLongName": "Opco AS",
         "cmpNpdidCompany": 10, "dscCurrentActivityStatus": "Evaluation"},
    ],
    7006: [{"dscNpdidDiscovery": 100, "cmpNpdidCompany": 10, "cmpLongName": "Opco AS",
            "dscOperatorFrom": ms(2019, 1, 1), "dscOperatorTo": None}],
    7007: [
        {"dscNpdidDiscovery": 100, "dscOwnerKind": "PRODUCTION LICENCE", "dscOwnerName": "555",
         "dscOwnerFactPageUrl": "https://factpages.sodir.no/licence/pageview/all/5550",
         "dscOwnershipFromDate": ms(2019, 1, 1), "dscOwnershipToDate": None},
        {"dscNpdidDiscovery": 200, "dscOwnerKind": "BUSINESS ARRANGEMENT AREA", "dscOwnerName": "ALPHA UNIT",
         "dscOwnerFactPageUrl": "https://factpages.sodir.no/bsns_arr_area/pageview/all/777",
         "dscOwnershipFromDate": ms(2015, 1, 1), "dscOwnershipToDate": None},
    ],
    3007: [
        lic(5550, "555", "Opco AS", 10, 55.0, ms(2019, 1, 1), oper=True),
        lic(5550, "555", "Partner AS", 20, 45.0, ms(2019, 1, 1)),
        lic(5550, "555", "Opco AS", 10, 100.0, ms(2010, 1, 1), ms(2018, 12, 31)),
    ],
    3304: [
        {"baaNpdidBsnsArrArea": 777, "baaName": "ALPHA UNIT", "cmpLongName": "Opco AS", "cmpNpdidCompany": 10,
         "baaLicenseeInterest": 60.0, "baaLicenseeSdfi": None, "baaLicenseeDateValidFrom": ms(2020, 1, 1),
         "baaLicenseeDateValidTo": None, "baaLicenseeDateUpdated": ms(2026, 2, 1)},
        {"baaNpdidBsnsArrArea": 777, "baaName": "ALPHA UNIT", "cmpLongName": "Partner AS", "cmpNpdidCompany": 20,
         "baaLicenseeInterest": 40.0, "baaLicenseeSdfi": None, "baaLicenseeDateValidFrom": ms(2020, 1, 1),
         "baaLicenseeDateValidTo": None, "baaLicenseeDateUpdated": ms(2026, 2, 1)},
    ],
}


@pytest.fixture()
def reader():
    return OwnershipReader(make_fetch(LAYERS))


def test_field_equity_is_complete_and_marks_operator(reader):
    rec = reader.field("alpha", date(2026, 1, 1))
    assert rec.fractions() == {"Opco AS": 0.6, "Partner AS": 0.4}
    assert rec.is_complete and rec.operator == "Opco AS"
    assert [s.company for s in rec.stakes if s.is_operator] == ["Opco AS"]
    assert rec.owner_name == "ALPHA UNIT" and rec.warnings == []


def test_field_equity_on_earlier_date_uses_that_period(reader):
    rec = reader.field("ALPHA", date(2015, 6, 1))
    assert rec.fractions() == {"Opco AS": 0.5, "Oldco AS": 0.5}


def test_period_end_date_is_inclusive(reader):
    assert "Oldco AS" in reader.field("ALPHA", date(2019, 12, 31)).fractions()
    assert "Partner AS" in reader.field("ALPHA", date(2020, 1, 1)).fractions()


def test_field_before_any_period_falls_back_with_warning(reader):
    rec = reader.field("ALPHA", date(2001, 1, 1))
    assert any("no interests are valid" in w for w in rec.warnings)


def test_discovery_in_licence_resolves_licensees_and_operator(reader):
    rec = reader.discovery("1/1-1 Beta", date(2026, 1, 1))
    assert rec.owner_kind == "PRODUCTION LICENCE" and rec.owner_name == "555"
    assert rec.fractions() == {"Opco AS": 0.55, "Partner AS": 0.45}
    assert rec.operator == "Opco AS" and rec.included_in_field is None


def test_discovery_name_matching_several_is_rejected(reader):
    with pytest.raises(OwnershipError, match="several"):
        reader.discovery("Beta")


def test_discovery_in_unit_uses_business_area_and_flags_field(reader):
    rec = reader.discovery("Gamma", date(2026, 1, 1))
    assert rec.owner_kind == "BUSINESS ARRANGEMENT AREA"
    assert rec.fractions() == {"Opco AS": 0.6, "Partner AS": 0.4}
    assert rec.included_in_field == "ALPHA"
    assert any("field's equity governs" in w for w in rec.warnings)


def test_unknown_name_raises(reader):
    with pytest.raises(OwnershipError, match="no field"):
        reader.field("NOPE")


def test_licence_lookup_and_history(reader):
    rec = reader.licence("555", date(2026, 1, 1))
    assert rec.kind == "licence" and rec.operator == "Opco AS"
    periods = reader.history("licence", "555")
    assert [p["from"] for p in periods] == ["2010-01-01", "2019-01-01"]
    assert periods[0]["stakes"] == {"Opco AS": 100.0}


def test_field_history_orders_periods(reader):
    periods = reader.history("field", "ALPHA")
    assert [p["from"] for p in periods] == ["2010-01-01", "2020-01-01"]


def test_prospect_proxy_is_labelled(reader):
    rec = reader.prospect_from_licence("Delta", "555", date(2026, 1, 1))
    assert rec.kind == "prospect" and rec.basis == "licence_proxy"
    assert any("does not publish prospect-level equity" in w for w in rec.warnings)


def test_user_prospect_validates_sum_and_labels_source():
    rec = OwnershipReader.prospect("Delta", {"A": 60, "B": 40}, operator="A")
    assert rec.basis == "user_provided" and rec.is_complete
    assert rec.find("a").is_operator
    with pytest.raises(OwnershipError, match="not 100"):
        OwnershipReader.prospect("Delta", {"A": 60, "B": 30})
    partial = OwnershipReader.prospect("Delta", {"A": 60, "B": 30}, allow_partial=True)
    assert not partial.is_complete and any("unallocated" in w for w in partial.warnings)


def test_allocate_net_and_handoff(reader):
    rec = reader.field("ALPHA", date(2026, 1, 1))
    gross = {2030: 100.0, 2031: 80.0}
    assert rec.net(gross, "partner") == {2030: 40.0, 2031: 32.0}
    assert rec.allocate([10.0, 20.0])["Opco AS"] == [6.0, 12.0]
    handoff = rec.to_economics_handoff("Opco AS")
    assert handoff["company_fraction"] == 0.6 and handoff["complete"] is True
    assert "tax" in handoff["scaling_note"]


def test_find_rejects_unknown_and_ambiguous_company(reader):
    rec = reader.field("ALPHA", date(2026, 1, 1))
    with pytest.raises(OwnershipError):
        rec.find("nobody")
    with pytest.raises(OwnershipError):
        rec.find("AS")


def test_portfolio_net_adds_assets(reader):
    field = reader.field("ALPHA", date(2026, 1, 1))
    disc = reader.discovery("1/1-1 Beta", date(2026, 1, 1))
    total = portfolio_net([(field, [100.0, 100.0]), (disc, [10.0, 20.0])], "Opco AS")
    assert total == pytest.approx([65.5, 71.0])
    with pytest.raises(OwnershipError):
        portfolio_net([(field, [1.0]), (disc, [1.0, 2.0])], "Opco AS")


def test_company_portfolio_lists_fields_and_discoveries_not_in_fields(reader):
    out = reader.portfolio("Opco AS", date(2026, 1, 1))
    kinds = {(i["kind"], i["name"]): i["interest_pct"] for i in out["items"]}
    assert kinds[("field", "ALPHA")] == 60.0
    assert kinds[("discovery", "1/1-1 Beta")] == 55.0
    assert ("discovery", "2/2-2 Gamma") not in kinds
    with_included = reader.portfolio("Opco AS", date(2026, 1, 1), include_discoveries_in_fields=True)
    assert ("discovery", "2/2-2 Gamma") in {(i["kind"], i["name"]) for i in with_included["items"]}


def test_portfolio_company_ambiguity_is_reported():
    layers = {3007: [lic(1, "1", "Equinor Energy AS", 11, 50.0, ms(2020, 1, 1)),
                     lic(2, "2", "Equinor UK Ltd", 12, 50.0, ms(2020, 1, 1))]}
    with pytest.raises(OwnershipError, match="several companies"):
        OwnershipReader(make_fetch(layers)).portfolio("Equinor")


def test_to_date_handles_pre_1970_and_none():
    assert to_date(None) is None
    assert to_date(ms(1969, 6, 1)) == date(1969, 6, 1)


def test_client_pages_until_limit_clears_and_records_provenance():
    rows = [{"v": i} for i in range(5)]
    client = SodirClient(make_fetch({7000: rows}), page_size=2)
    assert len(client.query(7000)) == 5
    assert client.records[0].layer == 7000 and client.records[0].rows == 5


def test_sql_quote_escapes_apostrophes():
    assert sql_quote("O'Brien") == "'O''Brien'"


def test_service_error_is_raised():
    def fetch(url, timeout):
        return json.dumps({"error": {"code": 400}}).encode()
    with pytest.raises(RuntimeError, match="DataService error"):
        SodirClient(fetch).query(7108)


def test_licence_milestones_use_local_oslo_dates():
    """Sodir stores a deadline as local midnight; read as UTC it is one day early."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    def oslo_midnight(y, m, d):
        return int(datetime(y, m, d, tzinfo=ZoneInfo("Europe/Oslo")).timestamp() * 1000)

    def fetch(url, timeout):
        if "/MapServer/3007/" in url:
            rows = [lic(1263, "1263", "Opco AS", 10, 100.0, ms(2025, 1, 1), oper=True)]
        else:
            assert "/FeatureServer/652/" in url
            rows = [{"prlTaskTypeCode": "DOD", "prlTaskTypeEn": "Decision to drill", "prlTaskCategory": "WORK",
                     "prlTaskStatusEn": "OPEN", "prlTaskExpiryDate": oslo_midnight(2027, 3, 14)},
                    {"prlTaskTypeCode": "BOK", "prlTaskTypeEn": "Drill or drop", "prlTaskCategory": "WORK",
                     "prlTaskStatusEn": "OPEN", "prlTaskExpiryDate": oslo_midnight(2026, 3, 14)}]
        return json.dumps({"features": [{"attributes": r} for r in rows]}).encode("utf-8")

    out = OwnershipReader(fetch=fetch).licence_milestones("1263")
    assert [r["deadline"] for r in out] == ["2026-03-14", "2027-03-14"]
    assert out[1]["code"] == "DOD"
    with pytest.raises(OwnershipError):
        OwnershipReader(fetch=lambda u, t: json.dumps({"features": []}).encode()).licence_milestones("nope")
