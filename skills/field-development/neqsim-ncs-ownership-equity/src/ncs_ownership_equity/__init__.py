"""Who owns NCS fields, discoveries and licences, and what that means for net economics."""

from .model import OwnershipError, OwnershipRecord, Stake, portfolio_net, scale
from .reader import OwnershipReader, PortfolioItem
from .sodir import LAYERS, SodirClient

__version__ = "0.1.0"

__all__ = [
           "LAYERS",
           "OwnershipError",
           "OwnershipReader",
           "OwnershipRecord",
           "PortfolioItem",
           "SodirClient",
           "Stake",
           "__version__",
           "portfolio_net",
           "scale",
]
