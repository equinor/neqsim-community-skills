"""Geographic helpers: local ENU frame, Norwegian block grids and GeoJSON export.

Dependency-free. Distances use a local tangent-plane (equirectangular)
approximation about a reference latitude, which is accurate to well under a
metre over the few tens of kilometres a subsea field spans.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, degrees, radians, sin, sqrt
from typing import Iterable, Mapping, Sequence

EARTH_RADIUS_M = 6_371_008.8
#: Metres per degree of latitude on the WGS84 ellipsoid at mid latitudes.
METRES_PER_DEGREE_LATITUDE = 111_132.0


@dataclass(frozen=True)
class LocalFrame:
    """East-north-up frame with its origin at a reference longitude and latitude."""

    origin_latitude_deg: float
    origin_longitude_deg: float

    def __post_init__(self) -> None:
        if not -90.0 <= self.origin_latitude_deg <= 90.0:
            raise ValueError("origin_latitude_deg must be between -90 and 90")
        if not -180.0 <= self.origin_longitude_deg <= 180.0:
            raise ValueError("origin_longitude_deg must be between -180 and 180")

    @property
    def metres_per_degree_longitude(self) -> float:
        return METRES_PER_DEGREE_LATITUDE * cos(radians(self.origin_latitude_deg))

    def to_geographic(self, east_m: float, north_m: float) -> tuple[float, float]:
        """Local east/north offsets in metres -> (latitude, longitude) in degrees."""
        latitude = self.origin_latitude_deg + north_m / METRES_PER_DEGREE_LATITUDE
        longitude = self.origin_longitude_deg + east_m / self.metres_per_degree_longitude
        return latitude, longitude

    def to_local(self, latitude_deg: float, longitude_deg: float) -> tuple[float, float]:
        """(latitude, longitude) in degrees -> local east/north offsets in metres."""
        north = (latitude_deg - self.origin_latitude_deg) * METRES_PER_DEGREE_LATITUDE
        east = (longitude_deg - self.origin_longitude_deg) * self.metres_per_degree_longitude
        return east, north


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two WGS84 positions."""
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2.0) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2.0) ** 2
    return 2.0 * EARTH_RADIUS_M * asin(sqrt(min(1.0, a)))


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial true bearing in degrees from the first position to the second."""
    from math import atan2

    phi1, phi2 = radians(lat1), radians(lat2)
    dlambda = radians(lon2 - lon1)
    y = sin(dlambda) * cos(phi2)
    x = cos(phi1) * sin(phi2) - sin(phi1) * cos(phi2) * cos(dlambda)
    return (degrees(atan2(y, x)) + 360.0) % 360.0


# ---------------------------------------------------------------------------
# Norwegian Continental Shelf quadrant and block grid (north of 62 degN)
# ---------------------------------------------------------------------------

#: Blocks per quadrant and the grid they form, north of 62 degN.
BLOCKS_PER_QUADRANT = 12
BLOCK_COLUMNS = 3
BLOCK_ROWS = 4


def quadrant_bounds(quadrant: str | int) -> dict:
    """Bounding box of a Norwegian quadrant north of 62 degN, e.g. ``"7324"``.

    North of 62 degN the quadrant label is the latitude of its southern edge
    followed by the longitude of its western edge, and the quadrant spans one
    degree of latitude by two degrees of longitude.
    """
    text = str(quadrant).strip()
    if len(text) != 4 or not text.isdigit():
        raise ValueError("quadrant must be a four-digit label such as '7324'")
    south = int(text[:2])
    west = int(text[2:])
    if south < 62:
        raise ValueError(
            "only the north-of-62-degN quadrant convention is implemented; "
            "quadrants south of 62 degN use a different numbering"
        )
    return {
        "quadrant": text,
        "south_latitude_deg": float(south),
        "north_latitude_deg": float(south + 1),
        "west_longitude_deg": float(west),
        "east_longitude_deg": float(west + 2),
    }


def block_bounds(designation: str, numbering: str = "row-major-from-northwest") -> dict:
    """Bounding box of a block such as ``"7324/8"``.

    Each quadrant is divided into 12 blocks of 15 arc-minutes of latitude by 40
    arc-minutes of longitude. The block numbering direction is a **documented
    assumption** rather than a calculation: verify the resulting box against the
    Norwegian Offshore Directorate FactMaps block layer before using it for
    anything but orientation.
    """
    if numbering != "row-major-from-northwest":
        raise ValueError("only 'row-major-from-northwest' numbering is implemented")
    if "/" not in designation:
        raise ValueError("designation must look like '7324/8'")
    quadrant_text, block_text = designation.split("/", 1)
    quadrant = quadrant_bounds(quadrant_text)
    block = int(block_text.strip())
    if not 1 <= block <= BLOCKS_PER_QUADRANT:
        raise ValueError("block number must be between 1 and %d" % BLOCKS_PER_QUADRANT)

    index = block - 1
    row = index // BLOCK_COLUMNS  # 0 is the northernmost row
    column = index % BLOCK_COLUMNS  # 0 is the westernmost column

    latitude_step = 1.0 / BLOCK_ROWS
    longitude_step = 2.0 / BLOCK_COLUMNS
    north = quadrant["north_latitude_deg"] - row * latitude_step
    west = quadrant["west_longitude_deg"] + column * longitude_step
    return {
        "designation": designation,
        "quadrant": quadrant["quadrant"],
        "block": block,
        "south_latitude_deg": north - latitude_step,
        "north_latitude_deg": north,
        "west_longitude_deg": west,
        "east_longitude_deg": west + longitude_step,
        "centre_latitude_deg": north - latitude_step / 2.0,
        "centre_longitude_deg": west + longitude_step / 2.0,
        "numbering_assumption": numbering,
        "verification": "confirm against the Sodir FactMaps block layer before use",
    }


# ---------------------------------------------------------------------------
# GeoJSON
# ---------------------------------------------------------------------------


def point_feature(latitude: float, longitude: float, properties: Mapping) -> dict:
    """A GeoJSON point feature (longitude first, per RFC 7946)."""
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [round(longitude, 7), round(latitude, 7)]},
        "properties": dict(properties),
    }


def line_feature(route: Sequence[tuple[float, float]], properties: Mapping) -> dict:
    """A GeoJSON line feature from a sequence of (latitude, longitude) points."""
    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [[round(lon, 7), round(lat, 7)] for lat, lon in route],
        },
        "properties": dict(properties),
    }


def polygon_feature(ring: Sequence[tuple[float, float]], properties: Mapping) -> dict:
    """A GeoJSON polygon feature from a closed ring of (latitude, longitude) points."""
    coordinates = [[round(lon, 7), round(lat, 7)] for lat, lon in ring]
    if coordinates[0] != coordinates[-1]:
        coordinates.append(coordinates[0])
    return {
        "type": "Feature",
        "geometry": {"type": "Polygon", "coordinates": [coordinates]},
        "properties": dict(properties),
    }


def feature_collection(features: Iterable[dict], name: str = "") -> dict:
    """Wrap features in a WGS84 GeoJSON FeatureCollection."""
    collection = {"type": "FeatureCollection", "features": list(features)}
    if name:
        collection["name"] = name
    return collection
