"""Bounded, keyless client for the OPM ``opm-data`` open reservoir decks (anonymous GitHub raw/API GETs)."""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import catalog
from .deck import include_paths, resolve_include, schedule_facts, summarize_deck

Fetch = Callable[[str, float, int], bytes]
USER_AGENT = "neqsim-opm-open-reservoir-decks/0.1 (+https://github.com/equinor/neqsim-community-skills)"
DEFAULT_MAX_BYTES = 5_000_000
_SAFE_PATH = re.compile(r"^[A-Za-z0-9_./\-]+$")
_REF = re.compile(r"^[A-Za-z0-9_.\-]{1,80}$")


class TooLargeError(RuntimeError):
    """The file exceeds ``max_bytes``; raise the limit deliberately (some decks include 58 MB grids)."""


def default_fetch(url: str, timeout: float = 60.0, max_bytes: int = DEFAULT_MAX_BYTES) -> bytes:
    """Perform a GET and read at most ``max_bytes``; raises ``TooLargeError`` when the body is longer."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https hosts
        body = response.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise TooLargeError(f"{url} is larger than {max_bytes} bytes")
    return body


@dataclass
class ReadRecord:
    """Provenance of one read for ``results.json`` and ``SOURCES.md``."""

    case: str
    path: str
    url: str
    ref: str
    sha256: str
    size: int
    licence: str
    cached: bool = False
    retrieved_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def to_dict(self) -> Dict[str, Any]:
        """Return the record as a plain dict."""
        return dict(self.__dict__)


class OpmDataClient:
    """Fetch decks and include files of the catalog cases."""

    def __init__(self, fetch: Fetch = default_fetch, cache_dir: Optional[Path] = None, *, ref: str = "master",
                 timeout: float = 60.0, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
        if not _REF.match(ref):
            raise ValueError(f"unsafe git ref {ref!r}")
        self.fetch = fetch
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.ref = ref
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.records: List[ReadRecord] = []

    def resolve_ref(self) -> str:
        """Pin the client to the current head commit SHA of ``master`` (anonymous API call, 60 per hour per IP).

        Pinning makes a task reproducible: record the returned SHA in the results.
        """
        url = f"{catalog.API_HOST}/repos/{catalog.REPO}/commits/master"
        sha = json.loads(self.fetch(url, self.timeout, 1_000_000).decode("utf-8"))["sha"]
        if not _REF.match(sha):
            raise ValueError("unexpected commit id from the API")
        self.ref = sha
        return sha

    def url(self, case: str, path: str) -> str:
        """Raw URL of ``path`` inside the case directory (validated; no traversal)."""
        entry = catalog.get_case(case)
        if not _SAFE_PATH.match(path) or ".." in path.split("/") or path.startswith("/"):
            raise ValueError(f"unsafe path {path!r}")
        return f"{catalog.RAW_HOST}/{catalog.REPO}/{self.ref}/{entry['directory']}/{path}"

    def get_text(self, case: str, path: str, *, allow_large: bool = False) -> str:
        """Fetch one file of a case as text. Known large files need ``allow_large=True`` and a higher ``max_bytes``."""
        entry = catalog.get_case(case)
        known = entry["large_files"].get(path)
        if known and not allow_large:
            raise TooLargeError(f"{case}/{path} is {known} bytes; pass allow_large=True and raise max_bytes to fetch it")
        url = self.url(case, path)
        cache_file = (self.cache_dir / self.ref / entry["directory"] / path) if self.cache_dir else None
        cached = cache_file is not None and cache_file.exists()
        if cached:
            body = cache_file.read_bytes()
        else:
            body = self.fetch(url, self.timeout, self.max_bytes)
            if cache_file is not None:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_bytes(body)
        self.records.append(ReadRecord(case, path, url, self.ref, hashlib.sha256(body).hexdigest(), len(body),
                                       entry["licence"], cached))
        return body.decode("utf-8", errors="replace")

    def summary(self, case: str, deck: Optional[str] = None, *, follow_schedule: bool = True) -> Dict[str, Any]:
        """Fetch a deck (default: the case's first) and return :func:`summarize_deck` plus catalog facts.

        With ``follow_schedule`` the includes after the ``SCHEDULE`` keyword are read too (Norne keeps all wells in
        ``INCLUDE/BC0407_HIST01122006.SCH``), skipping any larger than ``max_bytes`` and listing them in
        ``schedule_includes_skipped``.
        """
        entry = catalog.get_case(case)
        name = deck or entry["decks"][0]
        result = summarize_deck(self.get_text(case, name))
        skipped: List[str] = []
        if follow_schedule:
            for include in result["schedule_includes"]:
                path = resolve_include(name, include)
                try:
                    facts = schedule_facts(self.get_text(case, path))
                except (TooLargeError, urllib.error.HTTPError, urllib.error.URLError):
                    skipped.append(path)
                    continue
                result["wells"] = result["wells"] + [w for w in facts["wells"] if w not in result["wells"]]
                result["n_tstep_records"] += facts["n_tstep_records"]
                result["n_dates_records"] += facts["n_dates_records"]
        result.update({"case": case, "deck": name, "title": entry["title"], "licence": entry["licence"],
                       "schedule_includes_skipped": skipped})
        return result

    def get_include(self, case: str, deck: str, include: str, *, allow_large: bool = False) -> str:
        """Fetch an INCLUDE file named in ``deck``, resolved relative to the deck directory."""
        return self.get_text(case, resolve_include(deck, include), allow_large=allow_large)

    def includes(self, case: str, deck: Optional[str] = None) -> List[str]:
        """Return the INCLUDE paths of a deck, resolved to case-relative paths."""
        name = deck or catalog.get_case(case)["decks"][0]
        return [resolve_include(name, p) for p in include_paths(self.get_text(case, name))]

    def provenance(self) -> List[Dict[str, Any]]:
        """All read records as dicts."""
        return [r.to_dict() for r in self.records]
