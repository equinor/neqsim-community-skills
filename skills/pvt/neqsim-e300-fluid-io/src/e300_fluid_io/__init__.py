"""Read, write, and add water to Eclipse E300 fluid files for NeqSim.

Public API combines a pure-Python E300 format layer (no NeqSim required) with a
NeqSim bridge that loads E300 files into rigorous NeqSim fluids.
"""

from __future__ import annotations

from .format import (
    E300Fluid,
    WATER_E300_PARAMETERS,
    add_water,
    add_water_to_e300_file,
    parse_e300,
    read_e300_file,
    serialize_e300,
    write_e300_file,
)
from .neqsim_bridge import (
    neqsim_add_water,
    neqsim_available,
    neqsim_to_e300_string,
    read_e300_to_neqsim,
    write_neqsim_to_e300,
)

__all__ = [
    "E300Fluid",
    "WATER_E300_PARAMETERS",
    "add_water",
    "add_water_to_e300_file",
    "parse_e300",
    "read_e300_file",
    "serialize_e300",
    "write_e300_file",
    "neqsim_add_water",
    "neqsim_available",
    "neqsim_to_e300_string",
    "read_e300_to_neqsim",
    "write_neqsim_to_e300",
]
