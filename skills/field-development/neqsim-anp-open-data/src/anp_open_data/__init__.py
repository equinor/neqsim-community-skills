"""Helpers for reading Brazilian ANP open data safely.

The module makes no assumption about column names. Callers pass a mapping from
their file's header to the fields they need, so a change in a dataset is a
visible error instead of a silent wrong number. ``wfs`` reads the public ANP
GeoServer layers and derives approximate installation positions from producing
wellheads; ``tieins`` screens and ranks tie-in hosts and export lines.
"""

from .bathymetry import (
    altitude_at,
    build_etopo_url,
    depth_at,
    fetch_etopo_grid,
    flag_slopes,
    profile_along_route,
)
from .overview import (
    connect_pipelines,
    load_cached_layers,
    node_register,
    pipeline_register,
    plot_overview,
    summarise,
    write_csv,
)
from .tieins import DEFAULT_WEIGHTS, nearest_pipeline, point_to_polyline_km, rank_tie_in_hosts
from .tools import (
    OIL_M3_TO_BBL,
    check_crs,
    gas_volume,
    haversine_km,
    load_table,
    monthly_to_daily,
    oil_volume,
)
from .wfs import (
    ANP_LAYERS,
    ANP_WFS_BASE,
    build_getfeature_url,
    fetch_layer,
    installation_production,
    locate_installations,
    name_key,
    repair_name,
)

__all__ = [
    "altitude_at",
    "build_etopo_url",
    "connect_pipelines",
    "depth_at",
    "fetch_etopo_grid",
    "flag_slopes",
    "load_cached_layers",
    "node_register",
    "pipeline_register",
    "plot_overview",
    "profile_along_route",
    "summarise",
    "write_csv",
    "ANP_LAYERS",
    "ANP_WFS_BASE",
    "DEFAULT_WEIGHTS",
    "OIL_M3_TO_BBL",
    "build_getfeature_url",
    "check_crs",
    "fetch_layer",
    "gas_volume",
    "haversine_km",
    "installation_production",
    "load_table",
    "locate_installations",
    "monthly_to_daily",
    "name_key",
    "nearest_pipeline",
    "oil_volume",
    "point_to_polyline_km",
    "rank_tie_in_hosts",
    "repair_name",
]
