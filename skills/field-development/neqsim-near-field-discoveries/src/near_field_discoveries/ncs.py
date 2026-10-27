"""Norwegian discoveries and fields from the open Sodir DataService.

For a target position the reader returns, inside a radius:

* discoveries with status, hydrocarbon type, operator, recoverable volumes
  (Sodir resource estimate, resource class) and the description text that
  usually states the concept ("will most likely be developed as ..."),
* fields with status and remaining reserves,
* facilities (hosts) and pipelines for the map.

Every call is a bounded read-only GET through an injectable ``fetch(url,
timeout) -> bytes`` so tests and offline runs never touch the network. Data
are published by Sodir under NLOD 2.0.
"""

from __future__ import annotations

import datetime as _dt
import json
import re
import urllib.parse
import urllib.request
from typing import Any, Callable, Iterable, Mapping

from .geo import bbox_around, lines_from_geometry, point_from_geometry, rings_from_geometry
from .models import Discovery

Fetch = Callable[[str, float], bytes]

SODIR_DATASERVICE = "https://factmaps.sodir.no/api/rest/services/DataService/Data/MapServer"
LAYERS = {
    "facility": 6000,
    "pipeline": 6100,
    "discovery": 7000,
    "discovery_description": 7001,
    "discovery_reserves": 7008,
    "field": 7100,
    "field_reserves": 7113,
}
USER_AGENT = "neqsim-near-field-discoveries/0.1 (+https://github.com/equinor/neqsim-community-skills)"
DISCOVERY_URL = "https://factpages.sodir.no/discovery/pageview/all/{npdid}"
FIELD_URL = "https://factpages.sodir.no/field/pageview/all/{npdid}"
GAP_NO_PLAN = "Sodir publishes no PDO or concept for this record; the licensee's plans may be ahead of the open data."


def default_fetch(url: str, timeout: float = 90.0) -> bytes:
    """Bounded read-only GET."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - fixed https host
        return resp.read()


def _query(fetch: Fetch, layer: str, where: str = "1=1", *, envelope: tuple[float, float, float, float] | None = None,
           geometry: bool = False, out_fields: str = "*", timeout: float = 90.0, page_size: int = 1000,
           max_pages: int = 20, log: list | None = None) -> list[dict[str, Any]]:
    """Read every row of a layer (paged); rows carry ``_geometry`` (Esri JSON, WGS84) when requested."""
    base = "%s/%d/query" % (SODIR_DATASERVICE, LAYERS[layer])
    rows: list[dict[str, Any]] = []
    for page in range(max_pages):
        params = {
            "where": where, "outFields": out_fields, "f": "json",
            "returnGeometry": "true" if geometry else "false",
            "resultOffset": page * page_size, "resultRecordCount": page_size,
        }
        if geometry:
            params.update({"outSR": 4326, "maxAllowableOffset": 0.002, "geometryPrecision": 5})
        if envelope is not None:
            params.update({
                "geometry": json.dumps({"xmin": envelope[0], "ymin": envelope[1], "xmax": envelope[2], "ymax": envelope[3],
                                         "spatialReference": {"wkid": 4326}}),
                "geometryType": "esriGeometryEnvelope", "inSR": 4326, "spatialRel": "esriSpatialRelIntersects",
            })
        url = base + "?" + urllib.parse.urlencode(params)
        payload = json.loads(fetch(url, timeout).decode("utf-8"))
        if "error" in payload:
            if log is not None:
                log.append({"layer": layer, "url": url, "ok": False, "error": str(payload["error"])})
            raise RuntimeError("Sodir DataService error for %s: %s" % (layer, payload["error"]))
        feats = payload.get("features", [])
        for f in feats:
            row = dict(f.get("attributes", {}))
            if geometry and "geometry" in f:
                row["_geometry"] = f["geometry"]
            rows.append(row)
        if not feats or not payload.get("exceededTransferLimit"):
            break
    if log is not None:
        log.append({"layer": layer, "url": base, "rows": len(rows), "ok": True,
                    "retrieved_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                    "licence": "NLOD 2.0 (Sodir)"})
    return rows


def ncs_stage(status: str | None) -> str:
    """Map a Sodir discovery or field status to the normalised stage.

    ``Included in other discovery`` returns ``unknown`` here; the reader resolves it from the parent.
    """
    s = (status or "").lower()
    if "unlikely" in s:
        return "unlikely"
    if s.startswith("producing"):
        return "producing"
    if "approved" in s or "decided" in s:
        return "in_development"
    if "clarification" in s or "likely" in s:
        return "in_clarification"
    if "not evaluated" in s:
        return "not_evaluated"
    if "shut" in s:
        return "unlikely"
    return "unknown"


_HOST_RE = re.compile(
    r"(?:tied|tie)[- ]?(?:back|in)\w*\s+to\s+(?:the\s+)?([A-ZÆØÅ][\w\-ÆØÅæøå]*(?:\s+[A-ZÆØÅ0-9][\w\-ÆØÅæøå]*){0,2})")


def extract_plan_flags(text: str | None) -> list[str]:
    """Machine-readable hints from a Sodir description text; unverified, for triage only.

    Returns:
        Flags such as ``stand-alone``, ``tie-back``, ``host:<name>``, ``pdo``, ``joint-development``,
        ``no-plans`` and ``drilling-planned``.
    """
    if not text:
        return []
    t = text
    flags: list[str] = []
    if re.search(r"stand[- ]?alone", t, re.I):
        flags.append("stand-alone")
    if re.search(r"tie[d]?[- ]?(back|in)", t, re.I):
        flags.append("tie-back")
    for m in _HOST_RE.finditer(t):
        host = m.group(1).strip()
        if ("host:" + host) not in flags:
            flags.append("host:" + host)
    if re.search(r"plan for development and operation|\bPDO\b", t, re.I):
        flags.append("pdo")
    if re.search(r"developed together|joint development|area development|unitis|unitiz", t, re.I):
        flags.append("joint-development")
    if re.search(r"no (current )?plans|not (been )?further (assessed|evaluated)|will not be developed", t, re.I):
        flags.append("no-plans")
    if re.search(r"(appraisal|exploration) well .{0,40}(will be|is planned|planned)", t, re.I):
        flags.append("drilling-planned")
    return flags


def _ms_date(value: Any) -> str | None:
    if isinstance(value, (int, float)) and value > 0:
        return _dt.datetime.fromtimestamp(value / 1000.0, _dt.timezone.utc).date().isoformat()
    return None


def _in_clause(column: str, values: Iterable[Any]) -> list[str]:
    vals = [v for v in values if v is not None]
    return ["%s IN (%s)" % (column, ",".join(str(v) for v in vals[i:i + 80])) for i in range(0, len(vals), 80)]


def discovery_records(rows: list[dict], reserves: list[dict], descriptions: list[dict],
                      field_status: Mapping[str, str] | None = None) -> list[Discovery]:
    """Build records from raw Sodir discovery rows (see :func:`fetch_ncs_near_field`).

    Args:
        rows: Rows of layer 7000, optionally with ``_geometry``.
        reserves: Rows of layer 7008.
        descriptions: Rows of layer 7001 (English text is preferred).
        field_status: ``{field name: status}`` used for discoveries that are part of a field.

    Returns:
        One record per discovery, staged from the status; a discovery included in another discovery or a
        field takes that object's stage.
    """
    field_status = field_status or {}
    res_by = {r.get("dscNpdidDiscovery"): r for r in reserves}
    text_by: dict[Any, str] = {}
    for d in descriptions:
        if str(d.get("dscCultureCode") or "en").lower().startswith("en") or d.get("dscNpdidDiscovery") not in text_by:
            text_by[d.get("dscNpdidDiscovery")] = str(d.get("dscDescriptionText") or "")
    out: list[Discovery] = []
    for r in rows:
        npd = r.get("dscNpdidDiscovery")
        pt = point_from_geometry(r.get("_geometry"))
        if pt is None:
            continue
        status = r.get("dscCurrentActivityStatus")
        res = res_by.get(npd, {})
        volumes: dict[str, Any] = {}
        if res:
            volumes = {
                "oil_msm3": res.get("dscRecoverableOil"), "gas_gsm3": res.get("dscRecoverableGas"),
                "ngl_mt": res.get("dscRecoverableNGL"), "condensate_msm3": res.get("dscRecoverableCondensate"),
                "oe_msm3": res.get("dscRecoverableOe"), "resource_class": res.get("dscReservesRC"),
                "as_of": _ms_date(res.get("dscDateOffResEstDisplay")), "basis": "Sodir recoverable resource estimate (7008)",
            }
        text = text_by.get(npd, "")
        linked = {"discovery_well": r.get("wlbName"), "field": r.get("fldName"), "included_in_discovery": r.get("dscResInclInDiscoveryName"),
                  "owner": "%s %s" % (r.get("dscOwnerKind") or "", r.get("dscOwnerName") or ""),
                  "area": r.get("nmaName"), "main_area": r.get("ngpName")}
        stage = ncs_stage(status)
        if r.get("fldName") and r["fldName"] in field_status:
            stage = ncs_stage(field_status[r["fldName"]])
        gaps = [] if text else [GAP_NO_PLAN]
        if not volumes:
            gaps.append("No Sodir recoverable resource estimate for this discovery.")
        out.append(Discovery(
            country="NO", id="NO_DSC_%s" % npd, name=str(r.get("dscName") or npd), kind="discovery", stage=stage,
            status_raw=status, hc_type=r.get("dscHcType"), discovery_year=r.get("dscDiscoveryYear"),
            operator=r.get("cmpLongName"), lon=pt[0], lat=pt[1], position_basis="polygon-centroid",
            rings=rings_from_geometry(r.get("_geometry")), volumes=volumes, plan_note=text[:1500] or None,
            plan_flags=extract_plan_flags(text), linked=linked, source="Sodir DataService 7000/7001/7008",
            source_url=DISCOVERY_URL.format(npdid=npd), gaps=gaps))
    parent = {d.name: d for d in out}
    for d in out:
        incl = d.linked.get("included_in_discovery")
        if incl and d.stage == "unknown":
            target = parent.get(incl)
            if target is not None and target.stage != "unknown":
                d.stage = target.stage
            d.plan_note = (d.plan_note or "") if d.plan_note else "Included in %s; evaluate through that discovery." % incl
    return out


def field_records_ncs(rows: list[dict], reserves: list[dict]) -> list[Discovery]:
    """Field records from Sodir layer 7100 and 7113 (remaining reserves in oil equivalent)."""
    res_by = {r.get("fldNpdidField"): r for r in reserves}
    out = []
    for r in rows:
        pt = point_from_geometry(r.get("_geometry"))
        if pt is None:
            continue
        npd = r.get("fldNpdidField")
        res = res_by.get(npd, {})
        vol = {"oe_msm3": res.get("fldRecoverableOE"), "remaining_oe_msm3": res.get("fldRemainingOE"),
               "basis": "Sodir field reserves (7113), original recoverable and remaining"} if res else {}
        out.append(Discovery(
            country="NO", id="NO_FLD_%s" % npd, name=str(r.get("fldName")), kind="field",
            stage=ncs_stage(r.get("fldCurrentActivitySatus")), status_raw=r.get("fldCurrentActivitySatus"),
            hc_type=r.get("fldHcType"), discovery_year=r.get("fldDiscoveryYear"), operator=r.get("cmpLongName"),
            lon=pt[0], lat=pt[1], rings=rings_from_geometry(r.get("_geometry")), volumes=vol,
            linked={"area": r.get("fldMainArea"), "discovery_well": r.get("wlbName")},
            source="Sodir DataService 7100/7113", source_url=FIELD_URL.format(npdid=npd)))
    return out


def hosts_ncs(rows: list[dict]) -> list[dict[str, Any]]:
    """Surface or processing facilities that are in service or planned, as host dicts with positions."""
    out = []
    for r in rows:
        pt = point_from_geometry(r.get("_geometry"))
        phase = r.get("fclPhase")
        functions = str(r.get("fclFunctions") or "")
        if pt is None or phase not in ("IN SERVICE", "FUTURE", "INSTALLATION", "FABRICATION"):
            continue
        if r.get("fclSurface") != "Y" and "PROCESSING" not in functions:
            continue
        out.append({"name": r.get("fclName"), "lon": pt[0], "lat": pt[1], "kind": r.get("fclKind"), "phase": phase,
                    "functions": functions, "operator": r.get("fclCurrentOperatorName"), "water_depth_m": r.get("fclWaterDepth"),
                    "design_lifetime_y": r.get("fclDesignLifetime"), "field": r.get("fclBelongsToName"),
                    "source": "Sodir DataService 6000", "source_url": r.get("fclFactPageUrl")})
    return out


def pipelines_ncs(rows: list[dict]) -> list[dict[str, Any]]:
    """In-service pipelines with their line parts for the map."""
    out = []
    for r in rows:
        if r.get("pplCurrentPhase") != "IN SERVICE":
            continue
        parts = lines_from_geometry(r.get("_geometry"))
        if parts:
            out.append({"name": r.get("pplName"), "medium": r.get("pplMedium"), "diameter_in": r.get("pplDimension"),
                        "from": r.get("fclNameFrom"), "to": r.get("fclNameTo"), "parts": parts,
                        "source": "Sodir DataService 6100"})
    return out


def fetch_ncs_near_field(point: tuple[float, float], radius_km: float, *, fetch: Fetch | None = None, timeout: float = 90.0,
                         extra_margin_km: float = 10.0, include_infrastructure: bool = True) -> dict[str, Any]:
    """Read discoveries, fields, hosts and pipelines around a (lon, lat) point from Sodir.

    Args:
        point: ``(lon, lat)`` in WGS84 degrees.
        radius_km: Study radius; the read envelope adds ``extra_margin_km``.
        fetch: Optional ``fetch(url, timeout) -> bytes``; defaults to a bounded HTTPS GET.
        timeout: Per-request timeout in seconds.
        extra_margin_km: Margin so polygons crossing the circle are read completely.
        include_infrastructure: Also read facilities and pipelines.

    Returns:
        Dict with ``records`` (discoveries and fields as :class:`Discovery`), ``hosts``, ``pipelines``
        and ``log`` (one provenance record per read).
    """
    fetch = fetch or default_fetch
    log: list[dict[str, Any]] = []
    env = bbox_around(point[0], point[1], radius_km + extra_margin_km)
    dsc = _query(fetch, "discovery", envelope=env, geometry=True, timeout=timeout, log=log)
    npdids = [r.get("dscNpdidDiscovery") for r in dsc]
    reserves: list[dict] = []
    descriptions: list[dict] = []
    for clause in _in_clause("dscNpdidDiscovery", npdids):
        reserves += _query(fetch, "discovery_reserves", clause, timeout=timeout, log=log)
        descriptions += _query(fetch, "discovery_description", clause + " AND dscCultureCode='en'", timeout=timeout,
                               out_fields="dscNpdidDiscovery,dscDescriptionText,dscCultureCode", log=log)
    flds = _query(fetch, "field", envelope=env, geometry=True, timeout=timeout, log=log)
    known = {r.get("fldName"): r.get("fldCurrentActivitySatus") for r in flds}
    missing = sorted({r["fldName"] for r in dsc if r.get("fldName") and r["fldName"] not in known})
    for name in missing:
        for row in _query(fetch, "field", "fldName='%s'" % name.replace("'", "''"), timeout=timeout,
                          out_fields="fldName,fldCurrentActivitySatus", log=log):
            known[row.get("fldName")] = row.get("fldCurrentActivitySatus")
    freserves: list[dict] = []
    for clause in _in_clause("fldNpdidField", [r.get("fldNpdidField") for r in flds]):
        freserves += _query(fetch, "field_reserves", clause, timeout=timeout, log=log)
    records = discovery_records(dsc, reserves, descriptions, known) + field_records_ncs(flds, freserves)
    hosts: list[dict[str, Any]] = []
    pipes: list[dict[str, Any]] = []
    if include_infrastructure:
        hosts = hosts_ncs(_query(fetch, "facility", envelope=env, geometry=True, timeout=timeout, log=log))
        pipes = pipelines_ncs(_query(fetch, "pipeline", envelope=env, geometry=True, timeout=timeout, log=log))
    return {"records": records, "hosts": hosts, "pipelines": pipes, "log": log}


def records_from_snapshot(snapshot: Mapping[str, Any]) -> tuple[list[Discovery], list[dict[str, Any]]]:
    """Offline records and hosts from an ``ncs_network_snapshot.v1`` (skill ``neqsim-ncs-infrastructure-network``).

    The snapshot keeps only candidate discoveries as points, without description text; use
    :func:`fetch_ncs_near_field` for polygons, concepts and a fresh status.
    """
    out = []
    for d in snapshot.get("discoveries", {}).values():
        if d.get("lat") is None or d.get("lon") is None:
            continue
        res = d.get("reserves") or {}
        vol = {k: v for k, v in res.items() if v is not None}
        if "rc" in vol:
            vol["resource_class"] = vol.pop("rc")
        out.append(Discovery(
            country="NO", id="NO_DSC_%s" % d.get("npdid"), name=str(d.get("name")), stage=ncs_stage(d.get("status")),
            status_raw=d.get("status"), hc_type=d.get("hc_type"), discovery_year=d.get("discovery_year"),
            operator=d.get("operator"), lat=d["lat"], lon=d["lon"], volumes=vol, source="ncs_network_snapshot.v1",
            source_url=d.get("source_url"), linked={"field": d.get("linked_field"), "area": d.get("area")},
            gaps=["Snapshot holds a point and status only; re-read Sodir for polygons and the concept text."]))
    hosts = [dict(h, source="ncs_network_snapshot.v1") for h in snapshot.get("hosts", [])]
    return out, hosts
