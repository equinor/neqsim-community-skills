"""Read-only clients for the open NCS data APIs.

Every client takes an injectable ``fetch(url, timeout) -> bytes`` so tests and
offline runs never touch the network. All calls are GET, bounded (page size,
page count, timeout) and return plain Python data plus a provenance record.

Covered open sources (no credentials):

* Sodir DataService (ArcGIS REST) - every FactPages table and map layer:
  fields, discoveries, facilities, pipelines (with from/to facility), reserves,
  field descriptions (incl. the Transport text) and yearly/monthly profiles.
* Sodir FactPages CSV table views - the same tables as flat CSV.
* ENTSOG Transparency Platform - daily physical flow and firm capacity at the
  Norwegian gas entry points into the UK and continental Europe.
* norskpetroleum.no figure tables - pipeline capacity tables (xlsx).
"""

from __future__ import annotations

import csv
import io
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional

Fetch = Callable[[str, float], bytes]

USER_AGENT = "neqsim-ncs-infrastructure-network/0.1 (+https://github.com/equinor/neqsim-community-skills)"

SODIR_DATASERVICE = "https://factmaps.sodir.no/api/rest/services/DataService/Data/MapServer"
SODIR_FACTPAGES_CSV = (
    "https://factpages.sodir.no/public?/Factpages/external/tableview/{table}"
    "&rs:Command=Render&rc:Toolbar=false&rc:Parameters=f&IpAddress=not_used"
    "&CultureCode=en&rs:Format=CSV&Top100=false"
)
ENTSOG_API = "https://transparency.entsog.eu/api/v1"
NORSKPETROLEUM = "https://www.norskpetroleum.no"

# Layer ids of the Sodir DataService (see the MapServer description).
SODIR_LAYERS: Dict[str, int] = {
    "facility": 6000,
    "facility_function": 6001,
    "facility_belongs_to": 6003,
    "pipeline": 6100,
    "tuf": 6200,
    "tuf_operator_hst": 6201,
    "tuf_owner_hst": 6202,
    "discovery": 7000,
    "discovery_description": 7001,
    "discovery_reserves": 7008,
    "field": 7100,
    "field_activity_status_hst": 7101,
    "field_description": 7102,
    "field_investment_expected": 7107,
    "field_licensee_hst": 7108,
    "field_operator_hst": 7110,
    "field_reserves": 7113,
    "field_reserves_company": 7114,
    "profiles": 7300,
}

# ENTSOG interconnection points where Norwegian gas enters the downstream grid.
ENTSOG_NORWEGIAN_ENTRY_POINTS: Dict[str, Dict[str, str]] = {
    "ITP-00022": {"terminal": "ST.FERGUS", "country": "UK"},
    "ITP-00091": {"terminal": "EASINGTON", "country": "UK"},
    "ITP-00106": {"terminal": "ZEEBRUGGE", "country": "BE"},
    "ITP-00045": {"terminal": "DUNKERQUE", "country": "FR"},
    "ITP-00208": {"terminal": "DORNUM", "country": "DE"},
    "ITP-00525": {"terminal": "DORNUM", "country": "DE"},
    "ITP-00209": {"terminal": "EMDEN", "country": "DE"},
    "ITP-00210": {"terminal": "EMDEN", "country": "DE"},
    "ITP-00630": {"terminal": "NYBRO", "country": "DK"},
}

# Screening gross calorific value used to turn ENTSOG kWh/d into Sm3/d.
DEFAULT_GCV_KWH_PER_SM3 = 11.0

# The figure tables behind norskpetroleum.no's pipeline pages (xlsx uploads).
# The file names carry a revision date; update them when norskpetroleum reissues.
NORSKPETROLEUM_TABLES: Dict[str, str] = {
    "gas_pipelines": NORSKPETROLEUM + "/wp-content/uploads/72_Gassrorledninger_tabell_250220.xlsx",
    "oil_pipelines": NORSKPETROLEUM + "/wp-content/uploads/73_Olje_og_kondensatrorledninger_tabell_25012021-1.xlsx",
}


def default_fetch(url: str, timeout: float = 90.0) -> bytes:
    """Perform a bounded, read-only GET and return the body."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https hosts
        return response.read()


@dataclass
class ReadRecord:
    """Provenance of one open-API read."""

    source: str
    url: str
    rows: int
    retrieved_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    licence: str = "NLOD 2.0 (Sodir) / source terms; reuse with attribution"
    ok: bool = True
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


class SodirDataService:
    """Read any Sodir DataService layer with bounded paging."""

    def __init__(self, fetch: Fetch = default_fetch, *, timeout: float = 120.0, page_size: int = 1000,
                 max_pages: int = 100) -> None:
        self.fetch = fetch
        self.timeout = timeout
        self.page_size = page_size
        self.max_pages = max_pages
        self.records: List[ReadRecord] = []

    def layer_url(self, layer: str | int) -> str:
        layer_id = SODIR_LAYERS[layer] if isinstance(layer, str) else int(layer)
        return f"{SODIR_DATASERVICE}/{layer_id}/query"

    def query(self, layer: str | int, where: str = "1=1", out_fields: str = "*",
              return_geometry: bool = False, out_sr: Optional[int] = None,
              max_offset: Optional[float] = None) -> List[Dict[str, Any]]:
        """Return all features of a layer as dicts (``attributes`` plus optional ``geometry``)."""
        base = self.layer_url(layer)
        rows: List[Dict[str, Any]] = []
        offset = 0
        url = base
        for _ in range(self.max_pages):
            params = {
                "where": where,
                "outFields": out_fields,
                "returnGeometry": "true" if return_geometry else "false",
                "f": "json",
                "resultOffset": offset,
                "resultRecordCount": self.page_size,
            }
            if out_sr:
                params["outSR"] = out_sr
            if max_offset:
                # generalise polygons server-side; enough for a centroid
                params["maxAllowableOffset"] = max_offset
                params["geometryPrecision"] = 4
            url = base + "?" + urllib.parse.urlencode(params)
            payload = json.loads(self.fetch(url, self.timeout).decode("utf-8"))
            if "error" in payload:
                self.records.append(ReadRecord("sodir-dataservice", url, len(rows), ok=False,
                                               error=str(payload["error"])))
                raise RuntimeError(f"Sodir DataService error for layer {layer}: {payload['error']}")
            features = payload.get("features", [])
            for feature in features:
                row = dict(feature.get("attributes", {}))
                if return_geometry and "geometry" in feature:
                    row["_geometry"] = feature["geometry"]
                rows.append(row)
            if not features or not payload.get("exceededTransferLimit"):
                break
            offset += len(features)
        self.records.append(ReadRecord("sodir-dataservice", base, len(rows)))
        return rows


class SodirFactPages:
    """Read a Sodir FactPages table view as CSV rows."""

    def __init__(self, fetch: Fetch = default_fetch, *, timeout: float = 120.0) -> None:
        self.fetch = fetch
        self.timeout = timeout
        self.records: List[ReadRecord] = []

    def table(self, table: str) -> List[Dict[str, str]]:
        url = SODIR_FACTPAGES_CSV.format(table=table)
        text = self.fetch(url, self.timeout).decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(text)))
        self.records.append(ReadRecord("sodir-factpages", url, len(rows)))
        return rows


class EntsogTransparency:
    """Read daily physical flows / firm capacity at Norwegian entry points."""

    def __init__(self, fetch: Fetch = default_fetch, *, timeout: float = 90.0,
                 gcv_kwh_per_sm3: float = DEFAULT_GCV_KWH_PER_SM3) -> None:
        self.fetch = fetch
        self.timeout = timeout
        self.gcv = gcv_kwh_per_sm3
        self.records: List[ReadRecord] = []

    def operational_data(self, point_key: str, date_from: str, date_to: str,
                         indicator: str = "Physical Flow", limit: int = 1000) -> List[Dict[str, Any]]:
        params = {"pointKey": point_key, "indicator": indicator, "periodType": "day",
                  "from": date_from, "to": date_to, "limit": limit}
        url = f"{ENTSOG_API}/operationaldatas?" + urllib.parse.urlencode(params)
        try:
            body = self.fetch(url, self.timeout)
        except Exception as exc:
            # ENTSOG answers 404 "No result found" when a point published nothing
            # for the window - an empty series, not a failure.
            if getattr(exc, "code", None) == 404:
                self.records.append(ReadRecord("entsog-transparency", url, 0,
                                               licence="ENTSOG Transparency Platform terms"))
                return []
            raise
        payload = json.loads(body.decode("utf-8"))
        rows = payload.get("operationaldatas", [])
        self.records.append(ReadRecord("entsog-transparency", url, len(rows),
                                       licence="ENTSOG Transparency Platform terms; reuse with attribution"))
        return rows

    def norwegian_entry_flows(self, date_from: str, date_to: str,
                              indicator: str = "Physical Flow") -> List[Dict[str, Any]]:
        """Daily entry flow per Norwegian terminal, in kWh/d and screening MSm3/d."""
        out: List[Dict[str, Any]] = []
        for point_key, meta in ENTSOG_NORWEGIAN_ENTRY_POINTS.items():
            try:
                rows = self.operational_data(point_key, date_from, date_to, indicator)
            except Exception as exc:  # one failing point must not drop the others
                self.records.append(ReadRecord("entsog-transparency", point_key, 0, ok=False, error=str(exc)))
                continue
            for row in rows:
                value = row.get("value")
                if value is None or row.get("directionKey") != "entry":
                    continue
                out.append({
                    "point_key": point_key,
                    "terminal": meta["terminal"],
                    "country": meta["country"],
                    "operator": row.get("operatorKey"),
                    "day": str(row.get("periodFrom", ""))[:10],
                    "indicator": indicator,
                    "value_kwh_per_d": float(value),
                    "value_msm3_per_d": float(value) / self.gcv / 1.0e6,
                    "flow_status": row.get("flowStatus"),
                })
        return out


def summarise_entry_flows(rows: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    """Average MSm3/d per terminal, summing the operators of a shared point per day."""
    per_day: Dict[tuple, float] = {}
    for row in rows:
        key = (row["terminal"], row["day"])
        per_day[key] = per_day.get(key, 0.0) + row["value_msm3_per_d"]
    out: Dict[str, Dict[str, float]] = {}
    for (terminal, _day), value in per_day.items():
        stats = out.setdefault(terminal, {"days": 0, "sum": 0.0, "max": 0.0})
        stats["days"] += 1
        stats["sum"] += value
        stats["max"] = max(stats["max"], value)
    return {t: {"days": s["days"], "mean_msm3_per_d": s["sum"] / s["days"], "max_msm3_per_d": s["max"]}
            for t, s in out.items() if s["days"]}


def read_norskpetroleum_capacity_xlsx(content: bytes) -> List[Dict[str, Any]]:
    """Parse a norskpetroleum pipeline table (served as xlsx even when labelled csv)."""
    try:
        import openpyxl  # optional dependency
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("openpyxl is required to read norskpetroleum xlsx tables") from exc
    sheet = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True).active
    header: Optional[List[Any]] = None
    rows: List[Dict[str, Any]] = []
    for values in sheet.iter_rows(values_only=True):
        cells = list(values)
        if header is None:
            if "Operator" in cells and "From" in cells and "To" in cells:
                header = cells
            continue
        if not any(cells):
            continue
        record = {"name_no": cells[1], "name": cells[2]}
        for key, value in zip(header, cells):
            if key in ("Operator", "From", "To"):
                record[key.lower()] = value
            elif isinstance(key, str) and key.startswith("Start"):
                record["start_year"] = value
            elif isinstance(key, str) and key.startswith("Capacity"):
                record["capacity_raw"] = value
                record["capacity_unit"] = "MSm3/d" if "mill" in key.lower() else "Sm3/d"
            elif isinstance(key, str) and key.startswith("Diameter"):
                record["diameter_in"] = value
            elif isinstance(key, str) and key.startswith("Length"):
                record["length_km"] = value
        if record.get("name"):
            rows.append(record)
    return rows
