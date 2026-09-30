"""Best-effort resolver from an NCS installation name to WGS84 coordinates.

Reads the Sodir (Norwegian Offshore Directorate) ``facility`` layer of the
public DataService (ArcGIS REST, NLOD 2.0 licence) - the same open API used by
the ``neqsim-ncs-infrastructure-network`` skill. Field names on that layer are
not guaranteed stable across Sodir releases, so this client scans every string
attribute for the search term instead of hard-coding a name column, and reads
the geometry in ``outSR=4326`` (WGS84) directly rather than guessing separate
lat/lon columns.

This is a convenience resolver, not an authoritative position source. Verify
the returned coordinates against STID/P&ID or the operator's own records
before any safety-critical siting decision; do not use it to place equipment.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

Fetch = Callable[[str, float], bytes]

USER_AGENT = "neqsim-weather-data/0.1 (+https://github.com/equinor/neqsim-community-skills)"
FACILITY_QUERY_URL = "https://factmaps.sodir.no/api/rest/services/DataService/Data/MapServer/6000/query"


def default_fetch(url: str, timeout: float = 60.0) -> bytes:
    """Perform a bounded, read-only GET and return the body."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https host
        return response.read()


@dataclass
class FacilityLocation:
    """One Sodir ``facility`` record matching a name search."""

    name: str
    latitude: float
    longitude: float
    attributes: Dict[str, Any]
    source_url: str = "https://factmaps.sodir.no/"
    licence: str = "NLOD 2.0 (Sodir)"


class SodirFacilityLocator:
    """Best-effort name -> WGS84 coordinate lookup for NCS installations."""

    def __init__(self, fetch: Fetch = default_fetch, *, timeout: float = 60.0,
                 page_size: int = 1000, max_pages: int = 20) -> None:
        self.fetch = fetch
        self.timeout = timeout
        self.page_size = page_size
        self.max_pages = max_pages
        self._cache: Optional[List[Dict[str, Any]]] = None

    def _fetch_all(self) -> List[Dict[str, Any]]:
        if self._cache is not None:
            return self._cache
        rows: List[Dict[str, Any]] = []
        offset = 0
        for _ in range(self.max_pages):
            params = {
                "where": "1=1",
                "outFields": "*",
                "returnGeometry": "true",
                "outSR": 4326,
                "f": "json",
                "resultOffset": offset,
                "resultRecordCount": self.page_size,
            }
            url = FACILITY_QUERY_URL + "?" + urllib.parse.urlencode(params)
            payload = json.loads(self.fetch(url, self.timeout).decode("utf-8"))
            if "error" in payload:
                raise RuntimeError(f"Sodir facility query error: {payload['error']}")
            features = payload.get("features", [])
            if not features:
                break
            rows.extend(features)
            if len(features) < self.page_size:
                break
            offset += self.page_size
        self._cache = rows
        return rows

    @staticmethod
    def _name_of(attributes: Dict[str, Any]) -> Optional[str]:
        for key, value in attributes.items():
            if "name" in key.lower() and isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def find(self, name: str) -> List[FacilityLocation]:
        """Return every facility whose attributes contain ``name`` (case-insensitive)."""
        needle = name.strip().lower()
        if not needle:
            return []
        matches: List[FacilityLocation] = []
        for feature in self._fetch_all():
            attributes = feature.get("attributes", {}) or {}
            geometry = feature.get("geometry") or {}
            haystack = " ".join(str(v) for v in attributes.values() if isinstance(v, (str, int, float)))
            if needle not in haystack.lower():
                continue
            longitude, latitude = geometry.get("x"), geometry.get("y")
            if longitude is None or latitude is None:
                continue
            display_name = self._name_of(attributes) or name
            matches.append(
                FacilityLocation(
                    name=display_name,
                    latitude=float(latitude),
                    longitude=float(longitude),
                    attributes=attributes,
                )
            )
        return matches
