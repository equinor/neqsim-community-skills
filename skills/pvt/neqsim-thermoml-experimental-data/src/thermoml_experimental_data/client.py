"""Keyless, bounded client for the NIST/TRC ThermoML Archive.

Every call is an anonymous HTTPS GET to ``trc.nist.gov``. ``fetch`` is injectable so tests and offline runs never
touch the network. The archive is a public service without login; it is rate-limit friendly by design here
(a request cap per client, an on-disk cache, no crawling).
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .parser import ThermomlReport, parse_thermoml

Fetch = Callable[[str, float], bytes]
ARCHIVE_HOST = "https://trc.nist.gov"
SOURCE = "NIST/TRC ThermoML Archive"
USER_AGENT = "neqsim-thermoml-experimental-data/0.1 (+https://github.com/equinor/neqsim-community-skills)"
_DOI = re.compile(r"^10\.\d{4,9}/[A-Za-z0-9._;()/:\-]+$")


class ThermomlUnavailable(RuntimeError):
    """The archive answered with an error (for example the search API returns HTTP 503 when it is down)."""


def default_fetch(url: str, timeout: float = 60.0) -> bytes:
    """Perform a bounded GET and return the body."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https host
            return response.read()
    except urllib.error.HTTPError as error:
        raise ThermomlUnavailable(f"{url} -> HTTP {error.code}") from error


def validate_doi(doi: str) -> str:
    """Return the stripped DOI or raise ``ValueError`` (rejects anything that could alter the request path)."""
    candidate = (doi or "").strip()
    if not _DOI.match(candidate) or ".." in candidate:
        raise ValueError(f"not a plain DOI: {doi!r}")
    return candidate


def thermoml_url(doi: str) -> str:
    """URL of the ThermoML XML of an article, for example ``https://trc.nist.gov/ThermoML/10.1021/je3001427.xml``."""
    return f"{ARCHIVE_HOST}/ThermoML/{validate_doi(doi)}.xml"


@dataclass
class ReadRecord:
    """Provenance of one read for ``results.json`` and ``SOURCES.md``."""

    source: str
    url: str
    doi: str = ""
    cached: bool = False
    retrieved_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    note: str = "Public archive, no login. Cite the article DOI and NIST/TRC; do not redistribute the files."

    def to_dict(self) -> Dict[str, Any]:
        """Return the record as a plain dict."""
        return dict(self.__dict__)


class ThermomlClient:
    """Fetch and parse ThermoML articles by DOI."""

    def __init__(self, fetch: Fetch = default_fetch, cache_dir: Optional[Path] = None, *,
                 timeout: float = 60.0, max_requests: int = 50) -> None:
        self.fetch = fetch
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.timeout = timeout
        self.max_requests = max_requests
        self.requests = 0
        self.records: List[ReadRecord] = []

    def _get(self, url: str) -> bytes:
        if self.requests >= self.max_requests:
            raise RuntimeError(f"request cap of {self.max_requests} reached; raise max_requests deliberately")
        self.requests += 1
        return self.fetch(url, self.timeout)

    def get_xml(self, doi: str) -> bytes:
        """Return the ThermoML XML of a DOI, using the on-disk cache when configured."""
        url = thermoml_url(doi)
        cache_file = self.cache_dir / (validate_doi(doi).replace("/", "__") + ".xml") if self.cache_dir else None
        if cache_file is not None and cache_file.exists():
            self.records.append(ReadRecord(SOURCE, url, doi, cached=True))
            return cache_file.read_bytes()
        body = self._get(url)
        if cache_file is not None:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_bytes(body)
        self.records.append(ReadRecord(SOURCE, url, doi))
        return body

    def get_report(self, doi: str) -> ThermomlReport:
        """Fetch and parse one article."""
        return parse_thermoml(self.get_xml(doi))

    def search(self, query: str, page_size: int = 10, page: int = 0) -> List[Dict[str, Any]]:
        """Best-effort Lucene-style search (compound name, InChIKey, author) of the archive.

        Returns ``[{"doi", "title", "year", "journal", "compounds"}]``. The archive's search API is intermittently
        unavailable (HTTP 503); this raises ``ThermomlUnavailable`` then. Fall back to a DOI found through the
        archive's browse page or a literature search, and fetch it with ``get_report``.
        """
        if not query.strip() or re.search(r"[&\r\n]", query):
            raise ValueError("query must be non-empty and must not contain '&' or line breaks")
        context = json.dumps({"Citation": True, "data_summary": False, "Compound": True})
        url = (
            f"{ARCHIVE_HOST}/ThermoML-API/objects?query="
            + urllib.parse.quote(f"type:TRCTml4 AND ({query})")
            + f"&pageNum={int(page)}&pageSize={min(int(page_size), 50)}&sortFields=&requestContext="
            + urllib.parse.quote(context)
        )
        payload = json.loads(self._get(url).decode("utf-8"))
        self.records.append(ReadRecord(SOURCE, url))
        hits = []
        for item in payload.get("results", []):
            content = item.get("content", {})
            citation = content.get("Citation", {})
            hits.append({
                "doi": citation.get("sDOI", ""),
                "title": citation.get("sTitle", ""),
                "year": citation.get("yrPubYr", ""),
                "journal": citation.get("sPubName", ""),
                "compounds": [c.get("sCommonName", [""])[0] for c in content.get("Compound", [])],
            })
        return hits

    def provenance(self) -> List[Dict[str, Any]]:
        """All read records as dicts."""
        return [r.to_dict() for r in self.records]
