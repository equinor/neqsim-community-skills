"""Bounded, keyless client for the allow-listed open map services (WFS, ArcGIS REST, raster identify, USGS)."""

from __future__ import annotations

import hashlib
import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .sources import ALLOWED_HOSTS, SOURCES, TERMS, USGS

Fetch = Callable[[str, float, int], bytes]
BBox = Tuple[float, float, float, float]  # min_lon, min_lat, max_lon, max_lat (WGS84 degrees)
USER_AGENT = "neqsim-open-marine-constraints/0.1 (+https://github.com/equinor/neqsim-community-skills)"
MAX_BYTES = 25_000_000
PAGE = 1000


class SourceError(RuntimeError):
    """The service refused the request, answered an error object, or the URL is not allow-listed."""


def default_fetch(url: str, timeout: float = 60.0, max_bytes: int = MAX_BYTES) -> bytes:
    """Perform a GET and read at most ``max_bytes``; raises ``SourceError`` when the body is longer."""
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 " + USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - allow-listed https hosts
        body = response.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise SourceError(f"{url} is larger than {max_bytes} bytes; narrow the bounding box")
    return body


@dataclass
class ReadRecord:
    """Provenance of one request for ``results.json`` and ``SOURCES.md``."""

    source: str
    url: str
    sha256: str
    size: int
    cached: bool = False
    terms: str = TERMS
    retrieved_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def to_dict(self) -> Dict[str, Any]:
        """Return the record as a plain dict."""
        return dict(self.__dict__)


@dataclass
class FeatureSet:
    """Features of one layer inside a box; ``truncated`` is True when the cap or the server limit cut the list."""

    source: str
    features: List[Dict[str, Any]]
    truncated: bool = False


def check_url(url: str) -> None:
    """Raise ``SourceError`` unless ``url`` is https on an allow-listed host."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS:
        raise SourceError(f"{url} is not an allow-listed https host")


def _build(url: str, params: Dict[str, Any]) -> str:
    path = urllib.parse.quote(url, safe=":/%")
    return path + "?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote, safe=",:")


class MarineClient:
    """Read layers from the registry in ``sources.SOURCES`` with provenance and an optional disk cache."""

    def __init__(self, fetch: Fetch = default_fetch, cache_dir: Optional[Path] = None, *, timeout: float = 60.0) -> None:
        self.fetch = fetch
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.timeout = timeout
        self.records: List[ReadRecord] = []

    def _get_json(self, source: str, url: str) -> Dict[str, Any]:
        check_url(url)
        cache_file = self.cache_dir / (hashlib.sha1(url.encode("utf-8")).hexdigest() + ".json") if self.cache_dir else None
        cached = cache_file is not None and cache_file.exists()
        body = cache_file.read_bytes() if cached else self.fetch(url, self.timeout, MAX_BYTES)
        try:
            data = json.loads(body.decode("utf-8-sig"))
        except ValueError as error:
            raise SourceError(f"{url} did not return JSON") from error
        if isinstance(data, dict) and isinstance(data.get("error"), dict):
            # ArcGIS answers HTTP 200 with an error object; never read that as an empty layer.
            raise SourceError(f"{source}: {data['error'].get('message', 'service error')}")
        if cache_file is not None and not cached:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_bytes(body)
        self.records.append(ReadRecord(source, url, hashlib.sha256(body).hexdigest(), len(body), cached))
        return data

    def features(self, key: str, bbox: BBox, max_features: int = 5000) -> FeatureSet:
        """Return the features of ``key`` intersecting ``bbox`` as WGS84 lon/lat GeoJSON features."""
        spec = _spec(key)
        if spec["kind"] == "wfs":
            return self._wfs(key, spec, bbox, max_features)
        if spec["kind"] == "arcgis":
            return self._arcgis(key, spec, bbox, max_features)
        raise ValueError(f"{key} is a raster layer; use identify() or sample_route()")

    def _wfs(self, key: str, spec: Dict[str, Any], bbox: BBox, max_features: int) -> FeatureSet:
        min_lon, min_lat, max_lon, max_lat = bbox
        out: List[Dict[str, Any]] = []
        truncated = False
        while len(out) < max_features:
            params = {
                "service": "WFS",
                "version": "2.0.0",
                "request": "GetFeature",
                "typeNames": spec["type_name"],
                "outputFormat": "application/json",
                "srsName": "EPSG:4326",
                # WFS 2.0 with the URN CRS is latitude-first; a bare EPSG:4326 box silently returns nothing.
                "bbox": f"{min_lat},{min_lon},{max_lat},{max_lon},urn:ogc:def:crs:EPSG::4326",
                "count": min(PAGE, max_features - len(out)),
                "startIndex": len(out),
            }
            page = self._get_json(key, _build(spec["url"], params)).get("features", [])
            out.extend(page)
            if len(page) < params["count"]:
                break
        else:
            truncated = True
        return FeatureSet(key, out, truncated)

    def _arcgis(self, key: str, spec: Dict[str, Any], bbox: BBox, max_features: int) -> FeatureSet:
        out: List[Dict[str, Any]] = []
        seen = set()
        truncated = False
        url = f"{spec['url']}/{spec['layer']}/query"
        while len(out) < max_features:
            params = {
                "where": "1=1",
                "geometry": ",".join(str(v) for v in bbox),
                "geometryType": "esriGeometryEnvelope",
                "inSR": 4326,
                "outSR": 4326,
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "*",
                "returnGeometry": "true",
                # ~20 m generalisation keeps large coastal polygons below server size limits (HTTP 500 otherwise)
                "maxAllowableOffset": 0.0002,
                "f": "geojson",
                "resultOffset": len(out),
                "resultRecordCount": min(PAGE, max_features - len(out)),
            }
            data = self._get_json(key, _build(url, params))
            page = data.get("features", [])
            fresh = [f for f in page if json.dumps(f, sort_keys=True) not in seen]
            seen.update(json.dumps(f, sort_keys=True) for f in fresh)
            out.extend(fresh)
            more = bool(data.get("exceededTransferLimit")) or len(page) >= params["resultRecordCount"]
            if not fresh or not more:
                truncated = bool(data.get("exceededTransferLimit")) and not fresh
                break
        else:
            truncated = True
        return FeatureSet(key, out, truncated)

    def identify(self, key: str, lon: float, lat: float, half_width_deg: float = 0.25) -> Dict[str, Any]:
        """Sample a raster layer at one point; returns ``has_data``, ``class_value``, ``pixel`` and raw attributes."""
        spec = _spec(key)
        if spec["kind"] != "raster":
            raise ValueError(f"{key} is not a raster layer")
        params = {
            "geometry": f"{lon},{lat}",
            "geometryType": "esriGeometryPoint",
            "sr": 4326,
            "layers": f"all:{spec['layer']}",
            "tolerance": 1,
            "mapExtent": f"{lon - half_width_deg},{lat - half_width_deg},{lon + half_width_deg},{lat + half_width_deg}",
            "imageDisplay": "400,400,96",
            "returnGeometry": "false",
            "f": "json",
        }
        data = self._get_json(key, _build(spec["url"] + "/identify", params))
        results = data.get("results", [])
        attributes = results[0].get("attributes", {}) if results else {}
        pixel = next((v for k, v in attributes.items() if k.endswith("Pixel Value")), None)
        klass = next((v for k, v in attributes.items() if k.endswith("Class value")), None)
        has_data = pixel not in (None, "NoData", "")
        return {"has_data": has_data, "pixel": pixel if has_data else None, "class_value": klass, "attributes": attributes}

    def earthquakes(self, bbox: BBox, min_magnitude: float = 4.0, start_year: int = 1900, limit: int = 2000) -> FeatureSet:
        """Return USGS earthquakes (GeoJSON points, depth in km as third coordinate) inside ``bbox``."""
        min_lon, min_lat, max_lon, max_lat = bbox
        params = {
            "format": "geojson",
            "minmagnitude": min_magnitude,
            "starttime": f"{start_year}-01-01",
            "minlongitude": min_lon,
            "maxlongitude": max_lon,
            "minlatitude": min_lat,
            "maxlatitude": max_lat,
            "orderby": "magnitude",
            "limit": limit,
        }
        data = self._get_json("usgs_earthquakes", _build(USGS, params))
        feats = data.get("features", [])
        return FeatureSet("usgs_earthquakes", feats, len(feats) >= limit)

    def provenance(self) -> List[Dict[str, Any]]:
        """All read records as dicts."""
        return [r.to_dict() for r in self.records]


def _spec(key: str) -> Dict[str, Any]:
    if key not in SOURCES:
        raise KeyError(f"unknown layer {key!r}; see sources.SOURCES")
    return SOURCES[key]
