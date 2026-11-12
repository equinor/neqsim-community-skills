"""Open OPM reservoir benchmark decks: catalog, bounded client and deck parser (keyless, no login)."""

from __future__ import annotations

from .catalog import CASES, EXTERNAL, case_names, get_case
from .client import OpmDataClient, TooLargeError, default_fetch
from .deck import (
    expand_repeats,
    include_paths,
    keyword_blocks,
    keyword_records,
    resolve_include,
    schedule_facts,
    summarize_deck,
    to_floats,
)

__all__ = [
    "CASES",
    "EXTERNAL",
    "OpmDataClient",
    "TooLargeError",
    "case_names",
    "default_fetch",
    "expand_repeats",
    "get_case",
    "include_paths",
    "keyword_blocks",
    "keyword_records",
    "resolve_include",
    "schedule_facts",
    "summarize_deck",
    "to_floats",
]
