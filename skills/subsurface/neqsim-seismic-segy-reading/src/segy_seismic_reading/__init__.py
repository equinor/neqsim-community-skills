"""Read SEG-Y seismic with equinor/segyio: geometry, coordinates, sections, fences, evidence."""

from .evidence import SCHEMA, scan_folder, to_evidence, write_evidence
from .geometry import DEFAULT_HEADER_BYTES, SegyGeometry, inspect_segy, open_segy, trace_coordinates
from .sections import (
    Section,
    densify_polyline,
    extract_fence,
    read_crossline,
    read_inline,
    read_slice,
    save_section_png,
    trace_at_xy,
    write_cube,
)

__all__ = [
    "DEFAULT_HEADER_BYTES",
    "SCHEMA",
    "Section",
    "SegyGeometry",
    "densify_polyline",
    "extract_fence",
    "inspect_segy",
    "open_segy",
    "read_crossline",
    "read_inline",
    "read_slice",
    "save_section_png",
    "scan_folder",
    "to_evidence",
    "trace_at_xy",
    "trace_coordinates",
    "write_cube",
    "write_evidence",
]
