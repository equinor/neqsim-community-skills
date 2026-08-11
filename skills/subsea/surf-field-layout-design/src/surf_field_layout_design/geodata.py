"""Open geospatial and met-ocean data sources for subsea field-layout design.

The module is **offline by default**: it never opens a network connection of its
own. It builds a request plan (URL, parameters, licence, attribution) that a
caller can execute with its own read-only fetch adapter, so the same code runs
in a sandbox, in CI and on a workstation with internet access.

Every source registered here is openly licensed and free to use with
attribution. Bathymetry, coastline and licence-block data are what a screening
layout needs; met-ocean data is what an FPSO heading needs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence
from urllib.parse import urlencode


@dataclass(frozen=True)
class OpenDataSource:
    """A publicly available dataset that a layout study may draw on."""

    key: str
    name: str
    provider: str
    kind: str
    base_url: str
    service: str
    licence: str
    attribution: str
    notes: str


#: Openly licensed sources. Verify the licence text at the provider before publishing.
OPEN_DATA_SOURCES: dict[str, OpenDataSource] = {
    "gebco": OpenDataSource(
        key="gebco",
        name="GEBCO global bathymetric grid",
        provider="General Bathymetric Chart of the Oceans",
        kind="bathymetry",
        base_url="https://wms.gebco.net/mapserv",
        service="WMS",
        licence="free to use, attribution required",
        attribution="GEBCO Compilation Group, GEBCO Grid",
        notes="global 15 arc-second grid; coarse for detailed routing but fine for orientation",
    ),
    "emodnet_bathymetry": OpenDataSource(
        key="emodnet_bathymetry",
        name="EMODnet Bathymetry digital terrain model",
        provider="European Marine Observation and Data Network",
        kind="bathymetry",
        base_url="https://ows.emodnet-bathymetry.eu/wcs",
        service="WCS",
        licence="CC BY 4.0",
        attribution="EMODnet Bathymetry Consortium",
        notes="European seas, finer than GEBCO; the best open source for an NCS layout",
    ),
    "etopo": OpenDataSource(
        key="etopo",
        name="ETOPO global relief model",
        provider="NOAA National Centers for Environmental Information",
        kind="bathymetry",
        base_url="https://gis.ngdc.noaa.gov/arcgis/rest/services/DEM_mosaics/DEM_global_mosaic/ImageServer",
        service="ArcGIS ImageServer",
        licence="public domain (US Government)",
        attribution="NOAA NCEI ETOPO Global Relief Model",
        notes="global fallback when EMODnet does not cover the area",
    ),
    "sodir_factmaps": OpenDataSource(
        key="sodir_factmaps",
        name="Norwegian Offshore Directorate FactMaps",
        provider="Sokkeldirektoratet (Norwegian Offshore Directorate)",
        kind="licence-and-infrastructure",
        base_url="https://factmaps.sodir.no/arcgis/rest/services/FactMaps/3_0/MapServer",
        service="ArcGIS REST",
        licence="Norwegian Licence for Open Government Data (NLOD)",
        attribution="Norwegian Offshore Directorate FactMaps",
        notes="quadrants, blocks, licences, wellbores, discoveries, fields, facilities, pipelines",
    ),
    "sodir_factpages": OpenDataSource(
        key="sodir_factpages",
        name="Norwegian Offshore Directorate FactPages",
        provider="Sokkeldirektoratet (Norwegian Offshore Directorate)",
        kind="licence-and-infrastructure",
        base_url="https://factpages.sodir.no/public",
        service="tabular download",
        licence="Norwegian Licence for Open Government Data (NLOD)",
        attribution="Norwegian Offshore Directorate FactPages",
        notes="wellbore coordinates, discovery and field records as CSV",
    ),
    "natural_earth": OpenDataSource(
        key="natural_earth",
        name="Natural Earth coastline and land polygons",
        provider="Natural Earth",
        kind="basemap",
        base_url="https://naciscdn.org/naturalearth",
        service="file download",
        licence="public domain",
        attribution="Made with Natural Earth",
        notes="coastline for a locator map; 1:10m is enough at field scale",
    ),
    "copernicus_marine": OpenDataSource(
        key="copernicus_marine",
        name="Copernicus Marine Service reanalysis",
        provider="Copernicus Marine Environment Monitoring Service",
        kind="met-ocean",
        base_url="https://data.marine.copernicus.eu",
        service="OPeNDAP / STAC",
        licence="free and open, registration required",
        attribution="E.U. Copernicus Marine Service Information",
        notes="wave, wind and current statistics for the FPSO heading and riser design",
    ),
    "norwegian_hindcast": OpenDataSource(
        key="norwegian_hindcast",
        name="NORA3 Norwegian hindcast archive",
        provider="Norwegian Meteorological Institute",
        kind="met-ocean",
        base_url="https://thredds.met.no/thredds/projects/nora3.html",
        service="THREDDS / OPeNDAP",
        licence="CC BY 4.0",
        attribution="Norwegian Meteorological Institute, NORA3",
        notes="3 km wind and wave hindcast covering the Norwegian and Barents Seas",
    ),
}


@dataclass(frozen=True)
class DataRequest:
    """A planned read-only request. Nothing is sent until a caller executes it."""

    source_key: str
    url: str
    method: str
    purpose: str
    licence: str
    attribution: str

    def to_dict(self) -> dict:
        return {
            "source": self.source_key,
            "url": self.url,
            "method": self.method,
            "purpose": self.purpose,
            "licence": self.licence,
            "attribution": self.attribution,
        }


def _source(key: str) -> OpenDataSource:
    if key not in OPEN_DATA_SOURCES:
        raise ValueError(
            "unknown source %r; known sources are %s" % (key, ", ".join(sorted(OPEN_DATA_SOURCES)))
        )
    return OPEN_DATA_SOURCES[key]


def plan_bathymetry_request(
    west: float,
    south: float,
    east: float,
    north: float,
    source_key: str = "emodnet_bathymetry",
    width: int = 512,
    height: int = 512,
) -> DataRequest:
    """Plan a bathymetry coverage request over a WGS84 bounding box."""
    for name, value in (("west", west), ("east", east)):
        if not -180.0 <= value <= 180.0:
            raise ValueError("%s must be between -180 and 180" % name)
    for name, value in (("south", south), ("north", north)):
        if not -90.0 <= value <= 90.0:
            raise ValueError("%s must be between -90 and 90" % name)
    if west >= east or south >= north:
        raise ValueError("bounding box must have west < east and south < north")

    source = _source(source_key)
    query = {
        "service": "WCS",
        "version": "2.0.1",
        "request": "GetCoverage",
        "coverageId": "emodnet__mean",
        "format": "image/tiff",
        "subset": "Long(%f,%f)" % (west, east),
    }
    url = "%s?%s&subset=Lat(%f,%f)" % (source.base_url, urlencode(query), south, north)
    if source.service == "WMS":
        url = "%s?%s" % (
            source.base_url,
            urlencode(
                {
                    "service": "WMS",
                    "version": "1.3.0",
                    "request": "GetMap",
                    "layers": "GEBCO_LATEST",
                    "crs": "EPSG:4326",
                    "bbox": "%f,%f,%f,%f" % (south, west, north, east),
                    "width": width,
                    "height": height,
                    "format": "image/png",
                }
            ),
        )
    return DataRequest(
        source_key=source.key,
        url=url,
        method="GET",
        purpose="seabed depth over the field area for routing and riser design",
        licence=source.licence,
        attribution=source.attribution,
    )


def plan_sodir_layer_request(
    layer: str,
    west: float,
    south: float,
    east: float,
    north: float,
) -> DataRequest:
    """Plan a Sodir FactMaps feature query over a WGS84 bounding box.

    ``layer`` is a FactMaps layer id, for example the block, wellbore, discovery,
    field, facility or pipeline layer. Layer ids change between FactMaps
    releases, so read the service directory rather than hard-coding them.
    """
    source = _source("sodir_factmaps")
    query = {
        "f": "geojson",
        "where": "1=1",
        "geometry": "%f,%f,%f,%f" % (west, south, east, north),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
    }
    return DataRequest(
        source_key=source.key,
        url="%s/%s/query?%s" % (source.base_url, layer, urlencode(query)),
        method="GET",
        purpose="licence blocks, existing wellbores, infrastructure and pipelines near the field",
        licence=source.licence,
        attribution=source.attribution,
    )


def plan_layout_data_package(
    west: float,
    south: float,
    east: float,
    north: float,
    sodir_layers: Sequence[str] = ("0", "1"),
) -> list[DataRequest]:
    """Plan every open-data request a screening layout study needs."""
    requests = [plan_bathymetry_request(west, south, east, north)]
    for layer in sodir_layers:
        requests.append(plan_sodir_layer_request(layer, west, south, east, north))
    return requests


def execute(
    requests: Sequence[DataRequest],
    fetch: Callable[[str], object] | None = None,
) -> dict:
    """Execute planned requests with a caller-supplied read-only ``fetch``.

    Without a ``fetch`` adapter nothing is retrieved and the plan is returned as
    a manifest, so the caller can see exactly what would be requested, from
    where, and under which licence.
    """
    manifest = {
        "schemaVersion": "1.0",
        "executed": fetch is not None,
        "requests": [request.to_dict() for request in requests],
        "attribution": sorted({request.attribution for request in requests}),
        "results": {},
        "errors": {},
    }
    if fetch is None:
        return manifest
    for request in requests:
        try:
            manifest["results"][request.source_key] = fetch(request.url)
        except Exception as error:  # a failed source must not abort the study
            manifest["errors"][request.source_key] = "%s: %s" % (type(error).__name__, error)
    return manifest


def attribution_block(source_keys: Sequence[str]) -> list[str]:
    """Attribution lines to reproduce on any map made from these sources."""
    return [
        "%s (%s, %s)" % (_source(key).attribution, _source(key).provider, _source(key).licence)
        for key in source_keys
    ]
