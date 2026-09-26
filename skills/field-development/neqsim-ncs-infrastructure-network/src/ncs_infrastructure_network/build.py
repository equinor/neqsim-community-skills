"""Build the bundled NCS network snapshot from the open APIs.

``fetch_raw()`` reads the open sources through the clients in ``open_api``;
``build_snapshot(raw)`` is pure (no I/O) so it is unit-testable from fixtures.

Snapshot schema ``ncs_network_snapshot.v1``::

    nodes      {id: {name, kind, ...}}        hubs, plants, terminals, markets, fields
    arcs       [{id, from, to, medium, capacity, capacity_unit, source, primary, ...}]
    fields     {id: {name, npdid, status, hc_type, area, operator, lat, lon,
                     reserves, recoverable, production{year: {...}}, routes, transport_text}}
    discoveries{id: {name, npdid, status, hc_type, area, lat, lon, reserves{..., rc}}}
    hosts      [{name, field_id, lat, lon, water_depth_m, functions, operator}]
    sources    [read records]
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .open_api import (NORSKPETROLEUM_TABLES, EntsogTransparency, SodirDataService, default_fetch,
                       read_norskpetroleum_capacity_xlsx)
from .topology import ARC_OVERRIDES, CURATED_ARCS, CURATED_NODES, MARKET_LINKS, node_id, norm
from .transport_parser import Gazetteer, parse_transport_text

SCHEMA = "ncs_network_snapshot.v1"
NON_FIELD_KINDS = {"plant", "terminal", "market", "sink", "junction"}
SODIR_FIELD_URL = "https://factpages.sodir.no/field/pageview/all/{npdid}"
SODIR_DISCOVERY_URL = "https://factpages.sodir.no/discovery/pageview/all/{npdid}"

# Discovery statuses that are candidates for future tie-in / development.
CANDIDATE_DISCOVERY_STATUSES = {
    "Production decided", "Approved for production", "Production in clarification phase",
    "Production likely, but unclarified", "Production not evaluated", "Production is unlikely",
}


def fetch_raw(fetch=default_fetch, *, timeout: float = 120.0) -> Dict[str, Any]:
    """Read every open source the snapshot needs. Network, bounded, read-only."""
    ds = SodirDataService(fetch, timeout=timeout)
    raw: Dict[str, Any] = {
        "field": ds.query("field", return_geometry=True, out_sr=4326, max_offset=0.05),
        "discovery": ds.query("discovery", return_geometry=True, out_sr=4326, max_offset=0.05),
        "field_description": ds.query("field_description",
                                       where="fldDescriptionHeading='Transport' AND fldCultureCode='en'"),
        "field_reserves": ds.query("field_reserves"),
        "discovery_reserves": ds.query("discovery_reserves"),
        "facility": ds.query("facility", return_geometry=True, out_sr=4326),
        "profiles": ds.query("profiles", where="prfPeriod='year'"),
        "pipeline": ds.query("pipeline"),
    }
    raw["gas_pipelines"] = read_norskpetroleum_capacity_xlsx(fetch(NORSKPETROLEUM_TABLES["gas_pipelines"], timeout))
    raw["oil_pipelines"] = read_norskpetroleum_capacity_xlsx(fetch(NORSKPETROLEUM_TABLES["oil_pipelines"], timeout))
    raw["sources"] = [r.to_dict() for r in ds.records] + [
        {"source": "norskpetroleum", "url": url, "rows": len(raw[key]),
         "licence": "norskpetroleum.no - reuse with attribution and link"}
        for key, url in NORSKPETROLEUM_TABLES.items()
    ]
    return raw


# --------------------------------------------------------------------------- helpers

def _num(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_capacity(raw: Any) -> Tuple[Optional[float], Optional[List[float]]]:
    """Return (conservative capacity, [low, high]) from '46', 46, '10-27' or '10–27'."""
    if raw in (None, ""):
        return None, None
    if isinstance(raw, (int, float)):
        return float(raw), None
    numbers = [float(x.replace(",", ".")) for x in re.findall(r"\d+(?:[.,]\d+)?", str(raw))]
    if not numbers:
        return None, None
    if len(numbers) >= 2:
        return min(numbers), [min(numbers), max(numbers)]
    return numbers[0], None


def _centroid(geometry: Optional[Dict[str, Any]]) -> Tuple[Optional[float], Optional[float]]:
    if not geometry:
        return None, None
    if "x" in geometry and "y" in geometry:
        return geometry["y"], geometry["x"]
    rings = geometry.get("rings") or []
    points = [pt for ring in rings for pt in ring]
    if not points:
        return None, None
    return (round(sum(p[1] for p in points) / len(points), 4), round(sum(p[0] for p in points) / len(points), 4))


def resolve_name(name: str, gazetteer: Gazetteer) -> str:
    key = norm(name)
    return gazetteer.aliases.get(key) or node_id(name)


def _reachable_by_table(arcs: List[Dict[str, Any]], src: str, dst: str, medium: str, max_hops: int = 4) -> bool:
    """True when table/curated arcs already connect src to dst in 2+ hops.

    Prose often says "exported via Statpipe to Karsto"; a direct text arc
    src->dst would bypass the capacitated trunk, so it is dropped.
    """
    table = [a for a in arcs if a["medium"] == medium and a.get("source") in ("norskpetroleum", "curated")]
    frontier, seen = {src}, {src}
    for hop in range(max_hops):
        nxt = {a["to"] for a in table if a["from"] in frontier} - seen
        if dst in nxt and hop > 0:
            return True
        if not nxt:
            return False
        seen |= nxt
        frontier = nxt
    return False


# --------------------------------------------------------------------------- build

def build_snapshot(raw: Dict[str, Any], *, generated_utc: Optional[str] = None) -> Dict[str, Any]:
    field_rows = raw.get("field", [])
    field_names = {r["fldName"] for r in field_rows if r.get("fldName")}
    base = Gazetteer.build()
    field_ids = {name: resolve_name(name, base) for name in field_names}
    gazetteer = Gazetteer.build({name: fid for name, fid in field_ids.items()})

    nodes: Dict[str, Dict[str, Any]] = {n["id"]: dict(n) for n in CURATED_NODES}
    arcs: List[Dict[str, Any]] = []
    arc_keys = set()

    def ensure_node(nid: str, name: Optional[str] = None, kind: str = "hub") -> None:
        if nid not in nodes:
            nodes[nid] = {"id": nid, "name": name or nid.replace("_", " ").title(), "kind": kind}

    def add_arc(arc: Dict[str, Any]) -> None:
        key = (arc["from"], arc["to"], arc["medium"])
        if key in arc_keys or arc["from"] == arc["to"]:
            return
        if "GASSLED_GENERIC" in key:
            return
        arc_keys.add(key)
        arc.setdefault("id", f"{arc['from']}__{arc['to']}__{arc['medium']}")
        ensure_node(arc["from"])
        ensure_node(arc["to"])
        arcs.append(arc)

    # 1) capacity tables (norskpetroleum) - primary arcs
    for table, medium, unit in (("gas_pipelines", "gas", "MSm3/d"), ("oil_pipelines", "liquid", "Sm3/d")):
        for row in raw.get(table, []):
            name = str(row.get("name") or "").strip()
            src = resolve_name(str(row.get("from") or ""), gazetteer)
            dst = resolve_name(str(row.get("to") or ""), gazetteer)
            capacity, cap_range = parse_capacity(row.get("capacity_raw"))
            common = {
                "name": name, "medium": medium, "capacity": capacity, "capacity_range": cap_range,
                "capacity_unit": unit, "diameter_in": _num(row.get("diameter_in")),
                "length_km": _num(row.get("length_km")), "start_year": row.get("start_year"),
                "operator": row.get("operator"), "source": "norskpetroleum", "primary": True,
                "source_url": NORSKPETROLEUM_TABLES[table], "confidence": "high" if capacity else "medium",
            }
            override = ARC_OVERRIDES.get(name)
            if override:
                add_arc({**common, "id": node_id(name) + "_A", "from": src, "to": override["to"]})
                add_arc({**common, "id": node_id(name) + "_B", "from": override["to"], "to": override["continue_to"],
                         "shared_segment": True})
            else:
                add_arc({**common, "id": node_id(name) + "__" + src + "__" + dst, "from": src, "to": dst})

    # 2) curated arcs and market links
    for arc in CURATED_ARCS:
        add_arc({**arc, "source": "curated", "primary": True, "capacity_range": None})
    for link in MARKET_LINKS:
        add_arc({**link, "id": f"{link['from']}__{link['to']}", "capacity": None,
                 "capacity_unit": "MSm3/d" if link["medium"] == "gas" else "Sm3/d",
                 "source": "curated", "primary": True, "kind": "market_link"})

    # 3) fields
    fields: Dict[str, Dict[str, Any]] = {}
    for row in field_rows:
        name = row.get("fldName")
        if not name:
            continue
        fid = field_ids[name]
        lat, lon = _centroid(row.get("_geometry"))
        fields[fid] = {
            "id": fid, "name": name, "npdid": row.get("fldNpdidField"),
            "status": row.get("fldCurrentActivitySatus"), "hc_type": row.get("fldHcType"),
            "area": row.get("fldMainArea"), "operator": row.get("cmpLongName"),
            "discovery_year": row.get("fldDiscoveryYear"), "lat": lat, "lon": lon,
            "source_url": SODIR_FIELD_URL.format(npdid=row.get("fldNpdidField")),
            "reserves": {}, "recoverable": {}, "production": {}, "routes": [],
        }
        node = nodes.setdefault(fid, {"id": fid, "name": name})
        node.update({"kind": "field", "name": name, "status": row.get("fldCurrentActivitySatus"),
                     "npdid": row.get("fldNpdidField")})

    by_npdid = {f["npdid"]: fid for fid, f in fields.items()}

    # reserves: latest version per field (Sodir: oil/cond MSm3, gas GSm3, NGL Mtonn, OE MSm3oe)
    latest: Dict[Any, Dict[str, Any]] = {}
    for row in raw.get("field_reserves", []):
        npd = row.get("fldNpdidField")
        if npd not in latest or (row.get("fldVersion") or 0) >= (latest[npd].get("fldVersion") or 0):
            latest[npd] = row
    for npd, row in latest.items():
        fid = by_npdid.get(npd)
        if not fid:
            continue
        fields[fid]["reserves"] = {
            "remaining_oil_msm3": _num(row.get("fldRemainingOil")),
            "remaining_gas_bsm3": _num(row.get("fldRemainingGas")),
            "remaining_ngl_mt": _num(row.get("fldRemainingNGL")),
            "remaining_condensate_msm3": _num(row.get("fldRemainingCondensate")),
            "remaining_oe_msm3": _num(row.get("fldRemainingOE")), "version": row.get("fldVersion"),
        }
        fields[fid]["recoverable"] = {
            "oil_msm3": _num(row.get("fldRecoverableOil")), "gas_bsm3": _num(row.get("fldRecoverableGas")),
            "ngl_mt": _num(row.get("fldRecoverableNGL")),
            "condensate_msm3": _num(row.get("fldRecoverableCondensate")),
            "oe_msm3": _num(row.get("fldRecoverableOE")),
        }

    # yearly production (Sodir: oil/NGL/cond MSm3, gas GSm3)
    discovery_profiles: Dict[Any, Dict[str, Any]] = {}
    for row in raw.get("profiles", []):
        if row.get("prfPeriod", "year") != "year":
            continue
        record = {
            "oil_msm3": _num(row.get("prfPrdOilNetMillSm3")) or 0.0,
            "gas_bsm3": _num(row.get("prfPrdGasNetBillSm3")) or 0.0,
            "ngl_msm3": _num(row.get("prfPrdNGLNetMillSm3")) or 0.0,
            "condensate_msm3": _num(row.get("prfPrdCondensateNetMillSm3")) or 0.0,
            "oe_msm3": _num(row.get("prfPrdOeNetMillSm3")) or 0.0,
            "water_msm3": _num(row.get("prfPrdProducedWaterInFieldMillS")) or 0.0,
        }
        npd = row.get("prfNpdidInformationCarrier")
        if row.get("prfInformationCarrierKind", "FIELD") == "FIELD" and npd in by_npdid:
            fields[by_npdid[npd]]["production"][str(row.get("prfYear"))] = record
        else:
            discovery_profiles.setdefault(npd, {})[str(row.get("prfYear"))] = record

    # transport text -> routes and secondary arcs
    for row in raw.get("field_description", []):
        if row.get("fldDescriptionHeading", "Transport") != "Transport":
            continue
        if row.get("fldCultureCode", "en") != "en":  # the parser reads English prose
            continue
        fid = by_npdid.get(row.get("fldNpdidField")) or field_ids.get(row.get("fldName"))
        if not fid:
            continue
        text = row.get("fldDescriptionText") or ""
        fields[fid]["transport_text"] = text
        for route in parse_transport_text(fid, text, gazetteer):
            fields[fid]["routes"].append({"medium": route.medium, "nodes": route.nodes,
                                          "confidence": route.confidence, "needs_review": route.needs_review,
                                          "historic": route.historic})
            if route.historic:
                continue
            for a, b in route.arcs():
                if nodes.get(a, {}).get("kind") in NON_FIELD_KINDS:
                    continue  # outlets of plants/terminals come from tables, never from field prose
                if _reachable_by_table(arcs, a, b, route.medium):
                    continue  # prose skipped an intermediate trunk; keep the capacitated table path
                add_arc({"from": a, "to": b, "medium": route.medium, "capacity": None,
                         "capacity_unit": "MSm3/d" if route.medium == "gas" else "Sm3/d",
                         "source": "sodir-field-description", "reported_by": fid,
                         "primary": a == fid, "confidence": route.confidence,
                         "needs_review": route.needs_review, "source_url": fields[fid]["source_url"]})

    # 4) discoveries
    reserves_by_disc = {r.get("dscNpdidDiscovery"): r for r in raw.get("discovery_reserves", [])}
    discoveries: Dict[str, Dict[str, Any]] = {}
    for row in raw.get("discovery", []):
        status = row.get("dscCurrentActivityStatus")
        if status not in CANDIDATE_DISCOVERY_STATUSES:
            continue
        npd = row.get("dscNpdidDiscovery")
        lat, lon = _centroid(row.get("_geometry"))
        res = reserves_by_disc.get(npd, {})
        did = "DSC_" + node_id(row.get("dscName") or str(npd))
        discoveries[did] = {
            "id": did, "name": row.get("dscName"), "npdid": npd, "status": status,
            "hc_type": row.get("dscHcType"), "area": row.get("nmaName"), "operator": row.get("cmpLongName"),
            "discovery_year": row.get("dscDiscoveryYear"), "lat": lat, "lon": lon,
            "linked_field": row.get("fldName"),
            "source_url": SODIR_DISCOVERY_URL.format(npdid=npd),
            "reserves": {
                "rc": res.get("dscReservesRC"),
                "oil_msm3": _num(res.get("dscRecoverableOil")), "gas_bsm3": _num(res.get("dscRecoverableGas")),
                "ngl_mt": _num(res.get("dscRecoverableNGL")),
                "condensate_msm3": _num(res.get("dscRecoverableCondensate")),
                "oe_msm3": _num(res.get("dscRecoverableOe")),
            },
            "production": discovery_profiles.get(npd, {}),
        }

    # 5) host facilities (surface, processing, in service) for tie-back screening
    hosts: List[Dict[str, Any]] = []
    for row in raw.get("facility", []):
        functions = str(row.get("fclFunctions") or "")
        if row.get("fclPhase") != "IN SERVICE" or "PROCESSING" not in functions:
            continue
        lat, lon = _centroid(row.get("_geometry"))
        if lat is None:
            continue
        fid = by_npdid.get(row.get("fclNpdidBelongsTo"))
        hosts.append({"name": row.get("fclName"), "field_id": fid, "kind": row.get("fclKind"),
                      "lat": round(lat, 4), "lon": round(lon, 4), "water_depth_m": _num(row.get("fclWaterDepth")),
                      "functions": functions, "operator": row.get("fclCurrentOperatorName"),
                      "npdid": row.get("fclNpdidFacility"),
                      "surface": row.get("fclSurface") == "Y", "design_lifetime_y": row.get("fclDesignLifetime")})

    # 6) raw Sodir pipeline segments (in service) for cross-checks
    segments = [{"name": r.get("pplName"), "system": r.get("pplBelongsToName"), "label": r.get("pplMapLabel"),
                 "from_facility": r.get("fclNameFrom"), "to_facility": r.get("fclNameTo"),
                 "medium": r.get("pplMedium"), "diameter_in": r.get("pplDimension"),
                 "phase": r.get("pplCurrentPhase"), "operator": r.get("cmpLongName"),
                 "source_url": r.get("pplFactPageUrl")}
                for r in raw.get("pipeline", []) if r.get("pplCurrentPhase") == "IN SERVICE"]

    return {
        "schema": SCHEMA,
        "generated_utc": generated_utc or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "licence": "Sodir data NLOD 2.0; norskpetroleum.no and gassco.eu reused with attribution",
        "units": {"gas_capacity": "MSm3/d", "liquid_capacity": "Sm3/d", "reserves_oil": "MSm3",
                  "reserves_gas": "GSm3", "reserves_ngl": "Mtonn", "production_gas": "GSm3/yr",
                  "production_liquids": "MSm3/yr"},
        "nodes": nodes, "arcs": arcs, "fields": fields, "discoveries": discoveries,
        "hosts": hosts, "pipeline_segments": segments, "sources": raw.get("sources", []),
    }


def fetch_entsog_calibration(date_from: str, date_to: str, fetch=default_fetch) -> Dict[str, Any]:
    """Observed daily entry flows per Norwegian receiving terminal (for calibration)."""
    from .open_api import summarise_entry_flows

    client = EntsogTransparency(fetch)
    rows = client.norwegian_entry_flows(date_from, date_to)
    return {"window": [date_from, date_to], "by_terminal": summarise_entry_flows(rows),
            "records": [r.to_dict() for r in client.records]}
