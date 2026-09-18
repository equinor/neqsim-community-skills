"""PVT regression of a characterization factor against measured data.

Plant-agnostic, dependency-free helpers to regress a single split /
characterization factor against several weighted PVT or separator targets
(saturation pressure, GOR, stock-tank-oil density, formation volume factor).
The forward model is injected, mirroring FluidMagic's ``measured``/``weights``
regression and NeqSim's characterization workflow.
"""

from pvt_regression.regression import (
    RegressionResult,
    RegressionTarget,
    regress_characterization_factor,
    weighted_ssr,
)

__all__ = [
    "RegressionResult",
    "RegressionTarget",
    "regress_characterization_factor",
    "weighted_ssr",
]
