"""Read-only, bounded client for the Sodir open data services.

Every call is an HTTP GET to a fixed Sodir host. ``fetch`` is injectable so tests and offline
runs never touch the network. Each read appends a provenance record (URL, rows, time, licence).
"""

from __future__ import annotations

import csv
import io
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from . import catalog
from .downloads import DATASERVICE_DATA, DATASERVICE_METADATA, LICENCE, factpages_table_url

Fetch = Callable[[str, float], bytes]
USER_AGENT = "neqsim-sodir-open-data/0.1 (+https://github.com/equinor/neqsim-community-skills)"
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def default_fetch(url: str, timeout: float = 120.0) -> bytes:
    """Perform a bounded GET and return the body (www.sodir.no pages answer 403; use the service hosts)."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https hosts
        return response.read()


def sql_quote(value: Any) -> str:
    """Quote a string literal for an ArcGIS ``where`` clause."""
    return "'" + str(value).replace("'", "''") + "'"


def to_date(epoch_ms: Optional[float]) -> Optional[datetime]:
    """Convert a Sodir epoch-millisecond timestamp to a UTC datetime (``None`` stays ``None``).

    Deadlines are stored as local midnight, i.e. the previous day in UTC: convert with
    ``Europe/Oslo`` (``zoneinfo``) when the calendar date matters.
    """
    if epoch_ms is None:
        return None
    return _EPOCH + timedelta(milliseconds=float(epoch_ms))


@dataclass
class ReadRecord:
    """Provenance of one read."""

    source: str
    url: str
    rows: int
    where: str = ""
    retrieved_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    licence: str = LICENCE
    ok: bool = True
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return the record as a plain dict for ``results.json`` / ``SOURCES.md``."""
        return dict(self.__dict__)


class SodirOpenData:
    """Query any DataService layer or table, FactPages CSV view or metadata table."""

    def __init__(self, fetch: Fetch = default_fetch, *, timeout: float = 120.0, page_size: int = 1000,
                 max_pages: int = 100) -> None:
        self.fetch = fetch
        self.timeout = timeout
        self.page_size = min(int(page_size), 2000)  # server maxRecordCount is 2000
        self.max_pages = max_pages
        self.records: List[ReadRecord] = []

    def _json(self, url: str) -> Dict[str, Any]:
        payload = json.loads(self.fetch(url, self.timeout).decode("utf-8"))
        if "error" in payload:
            self.records.append(ReadRecord("sodir-dataservice", url, 0, ok=False, error=str(payload["error"])))
            raise RuntimeError(f"Sodir service error: {payload['error']}")
        return payload

    @staticmethod
    def bbox_params(bbox: Sequence[float]) -> Dict[str, Any]:
        """Return the envelope filter parameters for a WGS84 ``(west, south, east, north)`` box."""
        west, south, east, north = (float(v) for v in bbox)
        return {
            "geometry": f"{west},{south},{east},{north}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
        }

    def count(self, layer: "str | int", where: str = "1=1") -> int:
        """Return the number of rows matching ``where``."""
        url = f"{DATASERVICE_DATA}/{catalog.resolve_id(layer)}/query?" + urllib.parse.urlencode(
            {"where": where, "returnCountOnly": "true", "f": "json"})
        return int(self._json(url).get("count", 0))

    def query(self, layer: "str | int", where: str = "1=1", out_fields: str = "*", *,
              geometry: bool = False, out_sr: Optional[int] = None, bbox: Optional[Sequence[float]] = None,
              order_by: Optional[str] = None, max_rows: Optional[int] = None) -> List[Dict[str, Any]]:
        """Return rows of a layer/table as dicts, paging past the 2000-row server limit.

        ``geometry=True`` adds ``_geometry`` (ArcGIS JSON). Geometry is ED50 (EPSG 4230) unless
        ``out_sr=4326`` is passed; always request WGS84 before mixing with other data. ``bbox`` is a
        WGS84 ``(west, south, east, north)`` envelope and only applies to layers that have geometry.
        """
        layer_id = catalog.resolve_id(layer)
        base = f"{DATASERVICE_DATA}/{layer_id}/query"
        rows: List[Dict[str, Any]] = []
        offset = 0
        url = base
        for _ in range(self.max_pages):
            take = self.page_size if max_rows is None else min(self.page_size, max_rows - len(rows))
            if take <= 0:
                break
            params: Dict[str, Any] = {"where": where, "outFields": out_fields,
                                      "returnGeometry": "true" if geometry else "false", "f": "json",
                                      "resultOffset": offset, "resultRecordCount": take}
            if out_sr:
                params["outSR"] = out_sr
            if order_by:
                params["orderByFields"] = order_by
            if bbox is not None:
                params.update(self.bbox_params(bbox))
            url = base + "?" + urllib.parse.urlencode(params)
            payload = self._json(url)
            features = payload.get("features", [])
            for feature in features:
                row = dict(feature.get("attributes", {}))
                if geometry and "geometry" in feature:
                    row["_geometry"] = feature["geometry"]
                rows.append(row)
            if not features or not payload.get("exceededTransferLimit"):
                break
            offset += len(features)
        self.records.append(ReadRecord("sodir-dataservice", base, len(rows), where))
        return rows

    def distinct(self, layer: "str | int", column: str, where: str = "1=1") -> List[Any]:
        """Return the distinct values of one column (useful for enumerations such as ``wlbPurpose``)."""
        layer_id = catalog.resolve_id(layer)
        url = f"{DATASERVICE_DATA}/{layer_id}/query?" + urllib.parse.urlencode(
            {"where": where, "outFields": column, "returnDistinctValues": "true",
             "returnGeometry": "false", "f": "json"})
        feats = self._json(url).get("features", [])
        self.records.append(ReadRecord("sodir-dataservice", url, len(feats), where))
        return sorted({f["attributes"].get(column) for f in feats if f["attributes"].get(column) is not None})

    def by_name(self, layer: "str | int", column: str, value: str, **kwargs: Any) -> List[Dict[str, Any]]:
        """Query rows where ``column`` equals ``value`` (names are upper/lower case sensitive in Sodir data)."""
        return self.query(layer, f"{column}={sql_quote(value)}", **kwargs)

    def children(self, layer: "str | int", wellbore_npdid: int, **kwargs: Any) -> List[Dict[str, Any]]:
        """Return the rows of a wellbore child table (tops, DST, cores, samples, mud, logs...) for one wellbore."""
        return self.query(layer, f"wlbNpdidWellbore={int(wellbore_npdid)}", **kwargs)

    def metadata_attributes(self, table_name: str) -> List[Dict[str, Any]]:
        """Return the attribute descriptions of a table from the live Metadata service."""
        url = f"{DATASERVICE_METADATA}/11/query?" + urllib.parse.urlencode(
            {"where": f"TableName={sql_quote(table_name)}", "outFields": "*", "returnGeometry": "false", "f": "json"})
        feats = self._json(url).get("features", [])
        self.records.append(ReadRecord("sodir-metadata", url, len(feats)))
        return [f["attributes"] for f in feats]

    def factpages_table(self, table: str) -> List[Dict[str, str]]:
        """Read a FactPages CSV table view (e.g. ``field_production_monthly``) as string rows."""
        url = factpages_table_url(table)
        text = self.fetch(url, self.timeout).decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(text)))
        self.records.append(ReadRecord("sodir-factpages", url, len(rows)))
        return rows

    def provenance(self) -> List[Dict[str, Any]]:
        """Return every recorded read as dicts."""
        return [r.to_dict() for r in self.records]


def to_float(value: Any) -> Optional[float]:
    """Parse a FactPages cell to float (empty string and ``None`` give ``None``)."""
    if value is None or str(value).strip() == "":
        return None
    return float(str(value).replace(",", "."))


def point_lonlat(row: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    """Return ``(lon, lat)`` of a point row fetched with ``geometry=True`` and ``out_sr=4326``."""
    geom = row.get("_geometry") or {}
    if "x" in geom and "y" in geom:
        return float(geom["x"]), float(geom["y"])
    return None
