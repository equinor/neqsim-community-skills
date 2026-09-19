"""Public, deterministic produced-water and scale screening for NeqSim fluids.

This skill builds NeqSim-ready produced-water (brine) compositions and computes
screening-level scale saturation indices and water-mixing incompatibility. The
emitted ion mapping can be passed to the NeqSim ``ProducedWaterFluidBuilder``
to generate an electrolyte-CPA fluid for rigorous scale evaluation via
``ThermodynamicOperations.checkScalePotential``.
"""

from __future__ import annotations

from .builder import PRESETS, ProducedWater, ProducedWaterBuilder
from .scale import (
    MixIncompatibility,
    ScaleResult,
    ScaleScreener,
    ScaleScreening,
)

__all__ = [
    "PRESETS",
    "ProducedWater",
    "ProducedWaterBuilder",
    "ScaleScreener",
    "ScaleScreening",
    "ScaleResult",
    "MixIncompatibility",
]
