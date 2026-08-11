"""Screening design of subsea (SURF) field layouts and host placement.

Public entry points:

``design_surf_layout``
    place drill centres, wells, Xmas trees, manifolds, PLEMs, riser bases and the
    host, route every flowline, riser and umbilical, and size each line.
``plan_layout_data_package`` / ``execute``
    plan and (optionally) execute read-only requests to open bathymetry,
    licence-block and met-ocean sources.
``block_bounds`` / ``quadrant_bounds`` / ``LocalFrame``
    geographic helpers for placing a field on the map.
``plot_layout_map``
    draw the layout on latitude/longitude axes (needs matplotlib).
``build_well_paths`` / ``plot_reservoir_3d``
    screening well trajectories from each tree down to a reservoir target, and a
    three-dimensional illustration of the reservoir, the wells and the layout.
"""

from .geo import (
    LocalFrame,
    bearing_deg,
    block_bounds,
    feature_collection,
    haversine_m,
    line_feature,
    point_feature,
    polygon_feature,
    quadrant_bounds,
)
from .geodata import (
    OPEN_DATA_SOURCES,
    DataRequest,
    OpenDataSource,
    attribution_block,
    execute,
    plan_bathymetry_request,
    plan_layout_data_package,
    plan_sodir_layer_request,
)
from .layout import (
    Line,
    LineSize,
    Node,
    SurfLayout,
    design_surf_layout,
    erosional_velocity_m_per_s,
    inner_diameter_m,
    select_line_size,
)
from .plot import plot_layout_map
from .plot3d import plot_reservoir_3d
from .wells import (
    MAX_SCREENING_DOGLEG_DEG_PER_30M,
    WellPath,
    build_well_paths,
    trajectory_warnings,
)

__all__ = [
    "LocalFrame",
    "bearing_deg",
    "block_bounds",
    "quadrant_bounds",
    "haversine_m",
    "point_feature",
    "line_feature",
    "polygon_feature",
    "feature_collection",
    "OPEN_DATA_SOURCES",
    "OpenDataSource",
    "DataRequest",
    "plan_bathymetry_request",
    "plan_sodir_layer_request",
    "plan_layout_data_package",
    "execute",
    "attribution_block",
    "Node",
    "Line",
    "LineSize",
    "SurfLayout",
    "design_surf_layout",
    "select_line_size",
    "erosional_velocity_m_per_s",
    "inner_diameter_m",
    "plot_layout_map",
    "plot_reservoir_3d",
    "WellPath",
    "build_well_paths",
    "trajectory_warnings",
    "MAX_SCREENING_DOGLEG_DEG_PER_30M",
]

__version__ = "0.1.0"
