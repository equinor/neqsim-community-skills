"""NCS infrastructure network: open-data model of how Norwegian fields, pipelines,
processing plants and receiving terminals connect, plus read-only clients for
the open APIs it is built from and hand-offs to NeqSim Java classes."""

from .network import NcsNetwork, fields_by, haversine_km, iter_years, load_snapshot
from .open_api import (ENTSOG_NORWEGIAN_ENTRY_POINTS, SODIR_LAYERS, EntsogTransparency, SodirDataService,
                       SodirFactPages, summarise_entry_flows)
from .sources import SOURCE_REGISTRY, sources_for
from .transport_parser import Gazetteer, parse_transport_text

__version__ = "0.1.0"

__all__ = [
    "NcsNetwork", "load_snapshot", "fields_by", "haversine_km", "iter_years",
    "SodirDataService", "SodirFactPages", "EntsogTransparency", "summarise_entry_flows",
    "SODIR_LAYERS", "ENTSOG_NORWEGIAN_ENTRY_POINTS", "SOURCE_REGISTRY", "sources_for",
    "Gazetteer", "parse_transport_text", "__version__",
]
