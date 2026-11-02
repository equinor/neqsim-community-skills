"""Read ANP well-level production open data into NeqSim-ready series.

Parses the four public ANP well-level file families (monthly rate files with fluid
data, monthly volume files with injection, zone rates, well status), merges
onshore, offshore and pre-salt files without double counting, builds well, field
and installation series with gas-liquid ratio and water cut, checks completeness
and data features, prepares decline-fit input and a declared fluid basis.
"""

from .catalog import FAMILIES, MODEL_READINESS, VERIFIED_ON, families, readiness
from .fetch import download, extract_links
from .fluid import (
    NEQSIM_COMPONENTS,
    fluid_basis,
    gas_composition,
    latest_fluid_basis,
    oil_density_kg_m3,
)
from .parse import (
    BBL_TO_M3,
    RATE_FIELDS,
    SCHEMAS,
    days_in_month,
    detect_schema,
    fold,
    load_records,
    normalize,
    parse_number,
    parse_period,
    read_table,
    read_table_bytes,
    read_zip,
)
from .series import (
    aggregate,
    completeness,
    cumulative,
    decline_series,
    expected_latest_period,
    merge_environments,
    producing_rate,
    ratios,
    reconcile,
    well_flags,
    well_history,
)

__all__ = [
    "BBL_TO_M3",
    "FAMILIES",
    "MODEL_READINESS",
    "NEQSIM_COMPONENTS",
    "RATE_FIELDS",
    "SCHEMAS",
    "VERIFIED_ON",
    "aggregate",
    "completeness",
    "cumulative",
    "days_in_month",
    "decline_series",
    "detect_schema",
    "download",
    "expected_latest_period",
    "extract_links",
    "families",
    "fluid_basis",
    "fold",
    "gas_composition",
    "latest_fluid_basis",
    "load_records",
    "merge_environments",
    "normalize",
    "oil_density_kg_m3",
    "parse_number",
    "parse_period",
    "producing_rate",
    "ratios",
    "read_table",
    "read_table_bytes",
    "read_zip",
    "readiness",
    "reconcile",
    "well_flags",
    "well_history",
]
