"""Packaged Brazil offshore infrastructure and market datasets (snapshot of 2026-10-14).

Every entry carries value, unit, source_id, confidence and as_of. A ``value`` of
``None`` or confidence ``UNKNOWN`` means "not found in a fetched public source",
never zero. Source ids are prefixed per file: ``INF-S<n>`` and ``MKT-S<n>``.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date
from functools import cache
from importlib import resources

INFRA_SECTIONS = ("pipelines", "plants", "tariffs", "market", "regulation")
MARKET_SECTIONS = ("market", "marketing", "cost_benchmarks", "fields", "declared")


@cache
def _load(name: str) -> dict:
    path = resources.files(__package__).joinpath("data", name)
    return json.loads(path.read_text(encoding="utf-8"))


def load_infrastructure() -> dict:
    """Return the infrastructure dataset: pipelines, plants, tariffs, market, regulation, sources."""
    return _load("brazil_gas_infrastructure.json")


def load_market() -> dict:
    """Return the market, marketing, cost-benchmark, host-field and declared-assumption dataset."""
    return _load("brazil_market_analogues.json")


def sources() -> dict[str, dict]:
    """Merged source table keyed by ``INF-S<n>`` and ``MKT-S<n>`` (MKT values are URL strings)."""
    merged: dict[str, dict] = {}
    for key, val in load_infrastructure()["sources"].items():
        merged[key] = dict(val)
    for key, val in load_market()["sources"].items():
        merged[key] = {"url": val} if isinstance(val, str) else dict(val)
    return merged


def source_url(source_id: str | None) -> str | None:
    """Resolve a source id to its URL or citation, or ``None`` when the id is empty or unknown."""
    if not source_id:
        return None
    entry = sources().get(source_id)
    return entry.get("url") if entry else None


def _entry_label(entry: dict) -> str:
    parts = [str(entry.get(k, "")) for k in ("name", "entity", "attribute")]
    return " ".join(p for p in parts if p).lower()


def iter_entries() -> Iterator[tuple[str, str, dict]]:
    """Yield ``(dataset, section, entry)`` for every entry of both datasets."""
    infra = load_infrastructure()
    for section in INFRA_SECTIONS:
        for entry in infra[section]:
            yield "infrastructure", section, entry
    market = load_market()
    for section in MARKET_SECTIONS:
        for entry in market[section]:
            yield "market", section, entry


def find(text: str, section: str | None = None) -> list[tuple[str, str, dict]]:
    """Case-insensitive substring search over entry name, entity and attribute."""
    needle = text.lower()
    return [
        (ds, sec, e)
        for ds, sec, e in iter_entries()
        if needle in _entry_label(e) and (section is None or sec == section)
    ]


def is_unknown(entry: dict) -> bool:
    """True when the entry records an explicit gap (confidence UNKNOWN or no value)."""
    if str(entry.get("confidence", "")).upper() == "UNKNOWN":
        return True
    if "value" in entry:
        return entry["value"] is None
    if "capacity" in entry:
        return entry["capacity"] is None
    return False


def unknown_entries() -> list[tuple[str, str, dict]]:
    """All entries that are explicit gaps. Quote them as UNKNOWN in any report."""
    return [(ds, sec, e) for ds, sec, e in iter_entries() if is_unknown(e)]


def dataset_age_days(today: date | None = None) -> int:
    """Days between the dataset ``as_of`` date and today; use it to warn that data is stale."""
    as_of = date.fromisoformat(load_infrastructure()["meta"]["as_of"])
    return ((today or date.today()) - as_of).days
