"""Bounded, read-only access to the Sodir DataService layers that hold ownership."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
USER_AGENT = "neqsim-ncs-ownership-equity/0.1 (+https://github.com/equinor/neqsim-community-skills)"
SODIR_DATASERVICE = "https://factmaps.sodir.no/api/rest/services/DataService/Data/MapServer"

# Layer ids probed against the live service; they are not all listed in the MapServer index.
LAYERS: Dict[str, int] = {
    "licence_licensee_hst": 3007,
    "licence_transfer_hst": 3003,
    "licence_status": 3009,
    "bsns_arr_area_operator_hst": 3302,
    "bsns_arr_area_licensee_hst": 3304,
    "discovery": 7000,
    "discovery_operator_hst": 7006,
    "discovery_owner_hst": 7007,
    "field": 7100,
    "field_licensee_hst": 7108,
    "field_operator_hst": 7110,
}

Fetch = Callable[[str, float], bytes]


def default_fetch(url: str, timeout: float = 90.0) -> bytes:
    """Perform a bounded, read-only GET and return the body."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https host
        return response.read()


def sql_quote(value: str) -> str:
    """Quote a string literal for an ArcGIS where clause."""
    return "'" + str(value).replace("'", "''") + "'"


def to_date(epoch_ms: Optional[float]) -> Optional[date]:
    """Convert a Sodir epoch-millisecond timestamp to a UTC date (``None`` stays ``None``)."""
    if epoch_ms is None:
        return None
    return (_EPOCH + timedelta(milliseconds=float(epoch_ms))).date()


@dataclass
class ReadRecord:
    """Provenance of one DataService read."""

    layer: int
    where: str
    rows: int
    url: str
    retrieved_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    licence: str = "NLOD 2.0 (Sodir); reuse with attribution"

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


class SodirClient:
    """Page through one layer with a where clause."""

    def __init__(self, fetch: Fetch = default_fetch, *, timeout: float = 120.0, page_size: int = 1000,
                 max_pages: int = 50) -> None:
        self.fetch = fetch
        self.timeout = timeout
        self.page_size = page_size
        self.max_pages = max_pages
        self.records: List[ReadRecord] = []

    def query(self, layer: str | int, where: str = "1=1") -> List[Dict[str, Any]]:
        """Return the attribute dicts of every matching row."""
        layer_id = LAYERS[layer] if isinstance(layer, str) else int(layer)
        base = f"{SODIR_DATASERVICE}/{layer_id}/query"
        rows: List[Dict[str, Any]] = []
        offset = 0
        url = base
        for _ in range(self.max_pages):
            params = {"where": where, "outFields": "*", "returnGeometry": "false", "f": "json",
                      "resultOffset": offset, "resultRecordCount": self.page_size}
            url = base + "?" + urllib.parse.urlencode(params)
            payload = json.loads(self.fetch(url, self.timeout).decode("utf-8"))
            if "error" in payload:
                raise RuntimeError(f"Sodir DataService error for layer {layer_id}: {payload['error']}")
            features = payload.get("features", [])
            rows.extend(dict(f.get("attributes", {})) for f in features)
            if not payload.get("exceededTransferLimit") or not features:
                break
            offset += len(features)
        self.records.append(ReadRecord(layer_id, where, len(rows), url))
        return rows
