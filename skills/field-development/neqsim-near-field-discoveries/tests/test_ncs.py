import json
import urllib.parse

from near_field_discoveries import extract_plan_flags, fetch_ncs_near_field, ncs_stage, records_from_snapshot

DSC = [
    {"attributes": {"dscNpdidDiscovery": 1, "dscName": "7324/8-1 (Wisting)", "dscCurrentActivityStatus": "Production in clarification phase",
                    "dscHcType": "OIL", "dscDiscoveryYear": 2013, "cmpLongName": "Equinor Energy AS", "wlbName": "7324/8-1",
                    "dscOwnerKind": "PRODUCTION LICENCE", "dscOwnerName": "537", "fldName": None, "dscResInclInDiscoveryName": None},
     "geometry": {"rings": [[[20.0, 72.0], [20.1, 72.0], [20.1, 72.1], [20.0, 72.1], [20.0, 72.0]]]}},
    {"attributes": {"dscNpdidDiscovery": 2, "dscName": "7324/7-3 S (Drivis)", "dscCurrentActivityStatus": "Included in other discovery",
                    "dscHcType": "OIL", "dscResInclInDiscoveryName": "7324/8-1 (Wisting)", "fldName": None},
     "geometry": {"x": 20.3, "y": 72.05}},
    {"attributes": {"dscNpdidDiscovery": 3, "dscName": "7220/5-2 (Nunatak)", "dscCurrentActivityStatus": "Production is unlikely", "dscHcType": "GAS", "fldName": None},
     "geometry": {"x": 21.0, "y": 72.0}},
]
RES = [{"dscNpdidDiscovery": 1, "dscRecoverableOil": 74.4, "dscRecoverableGas": 0.0, "dscRecoverableNGL": 0.0, "dscRecoverableCondensate": 0.0,
        "dscRecoverableOe": 74.4, "dscReservesRC": "4F", "dscDateOffResEstDisplay": 1767139200000}]
TEXT = [{"dscNpdidDiscovery": 1, "dscCultureCode": "en", "dscDescriptionText": "The discovery will most likely be developed as a stand-alone installation. Drivis may be tied back to the Wisting host."}]
FLD = [{"attributes": {"fldName": "JOHAN CASTBERG", "fldNpdidField": 9, "fldCurrentActivitySatus": "Producing", "fldHcType": "OIL/GAS", "cmpLongName": "Equinor Energy AS"},
        "geometry": {"rings": [[[19.0, 71.5], [19.2, 71.5], [19.2, 71.6], [19.0, 71.6], [19.0, 71.5]]]}}]
FCL = [{"attributes": {"fclName": "JC FPSO", "fclPhase": "IN SERVICE", "fclSurface": "Y", "fclFunctions": "PROCESSING", "fclKind": "FPSO"}, "geometry": {"x": 19.1, "y": 71.55}},
       {"attributes": {"fclName": "SUBSEA X", "fclPhase": "IN SERVICE", "fclSurface": "N", "fclFunctions": "WELL", "fclKind": "TEMPLATE"}, "geometry": {"x": 19.2, "y": 71.5}}]
PPL = [{"attributes": {"pplName": "Oil line", "pplCurrentPhase": "IN SERVICE", "pplMedium": "Oil", "pplDimension": 16.0}, "geometry": {"paths": [[[19.1, 71.55], [20.0, 72.0]]]}}]


def fake_fetch(url, timeout):
    parsed = urllib.parse.urlparse(url)
    layer = int(parsed.path.split("/")[-2])
    q = urllib.parse.parse_qs(parsed.query)
    where = q["where"][0]
    rows = {7000: DSC, 7008: [{"attributes": r} for r in RES], 7001: [{"attributes": r} for r in TEXT], 7100: FLD, 7113: [],
            6000: FCL, 6100: PPL}[layer]
    if layer == 7100 and "fldName=" in where:
        rows = []
    return json.dumps({"features": rows}).encode("utf-8")


def test_stage_mapping() -> None:
    assert ncs_stage("Production in clarification phase") == "in_clarification"
    assert ncs_stage("Production likely but unclarified") == "in_clarification"
    assert ncs_stage("Production is unlikely") == "unlikely"
    assert ncs_stage("Approved for production") == "in_development"
    assert ncs_stage("Producing") == "producing"
    assert ncs_stage("Production not evaluated") == "not_evaluated"
    assert ncs_stage("Included in other discovery") == "unknown"


def test_plan_flags_find_concept_and_host() -> None:
    flags = extract_plan_flags("It will most likely be developed as a stand-alone installation. May be tied back to the Johan Castberg field.")
    assert "stand-alone" in flags and "tie-back" in flags
    assert any(f.startswith("host:Johan Castberg") for f in flags)
    assert extract_plan_flags(None) == []


def test_fetch_builds_records_hosts_and_pipelines() -> None:
    out = fetch_ncs_near_field((20.0, 72.0), 100, fetch=fake_fetch)
    recs = {r.name: r for r in out["records"]}
    wisting = recs["7324/8-1 (Wisting)"]
    assert wisting.stage == "in_clarification"
    assert wisting.oe_msm3() == 74.4 and wisting.volumes["resource_class"] == "4F"
    assert "stand-alone" in wisting.plan_flags
    assert wisting.rings and wisting.position_basis == "polygon-centroid"
    assert recs["7324/7-3 S (Drivis)"].stage == "in_clarification"
    assert recs["7220/5-2 (Nunatak)"].stage == "unlikely"
    assert any("recoverable resource" in g for g in recs["7324/7-3 S (Drivis)"].gaps)
    assert recs["JOHAN CASTBERG"].kind == "field" and recs["JOHAN CASTBERG"].stage == "producing"
    assert [h["name"] for h in out["hosts"]] == ["JC FPSO"]
    assert out["pipelines"][0]["medium"] == "Oil"
    assert all(entry["ok"] for entry in out["log"])


def test_records_from_snapshot() -> None:
    snap = {"discoveries": {"D": {"npdid": 5, "name": "A", "status": "Approved for production", "hc_type": "GAS", "lat": 60.0, "lon": 3.0,
                                   "reserves": {"rc": "3F", "oe_msm3": 12.0, "oil_msm3": None}}},
            "hosts": [{"name": "H", "lat": 60.1, "lon": 3.1}]}
    recs, hosts = records_from_snapshot(snap)
    assert recs[0].stage == "in_development" and recs[0].oe_msm3() == 12.0 and recs[0].volumes["resource_class"] == "3F"
    assert hosts[0]["name"] == "H"
