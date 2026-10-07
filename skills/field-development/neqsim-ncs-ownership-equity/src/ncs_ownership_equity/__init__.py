"""Who owns NCS fields, discoveries and licences, and what that means for net economics."""

from .model import OwnershipError, OwnershipRecord, Stake, portfolio_net, scale
from .reader import OwnershipReader, PortfolioItem
from .sodir import LAYERS, SodirClient

__version__ = "0.1.0"

__all__ = ["OwnershipReader", "OwnershipRecord", "Stake", "PortfolioItem", "OwnershipError", "portfolio_net",
           "scale", "SodirClient", "LAYERS", "__version__"]
