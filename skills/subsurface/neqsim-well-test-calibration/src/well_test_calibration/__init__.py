"""Well-test calibration from raw test-separator measurements with NeqSim.

Turns one well test into model evidence: the well stream is recombined from the actual gas and oil volumes measured at
test-separator conditions (not from allocated standard rates), converted to stock tank through the real separation
train, and used to tune the well's lift model (heat-transfer coefficient U and head/holdup factor kH) with priors and a
held-out acceptance gate. A tuned lift model plus a downhole gauge then gives the well rate (virtual flow meter).
"""

from .fit import FitResult, fit_with_priors
from .gate import accept_calibration
from .raw import quality_flags, window_mean
from .recombine import recombine_separator_volumes, stock_tank_rates
from .vfm import rate_from_gauge
from .workflow import calibrate_well

__all__ = [
    "FitResult", "fit_with_priors", "accept_calibration", "window_mean", "quality_flags",
    "recombine_separator_volumes", "stock_tank_rates", "rate_from_gauge", "calibrate_well",
]
__version__ = "0.1.0"
