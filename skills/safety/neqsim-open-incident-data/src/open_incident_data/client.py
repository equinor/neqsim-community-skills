"""Bounded, keyless client for the BSEE raw-data zips (two allow-listed files, zip-bomb guard, provenance)."""

from __future__ import annotations

import hashlib
import io
import urllib.request
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .sources import HOST, SOURCES, TERMS

Fetch = Callable[[str, float, int], bytes]
USER_AGENT = "neqsim-open-incident-data/0.1 (+https://github.com/equinor/neqsim-community-skills)"
MAX_ZIP_BYTES = 20_000_000
MAX_MEMBER_BYTES = 60_000_000


class SourceError(RuntimeError):
    """The download is not the expected zip (the server answers HTML for unknown paths) or is too large."""


def default_fetch(url: str, timeout: float = 120.0, max_bytes: int = MAX_ZIP_BYTES) -> bytes:
    """Perform a GET and read at most ``max_bytes``; raises ``SourceError`` when the body is longer."""
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 " + USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed https host
        body = response.read(max_bytes + 1)
    if len(body) > max_bytes:
        raise SourceError(f"{url} is larger than {max_bytes} bytes")
    return body


@dataclass
class ReadRecord:
    """Provenance of one download for ``results.json`` and ``SOURCES.md``."""

    source: str
    url: str
    sha256: str
    size: int
    cached: bool = False
    terms: str = TERMS
    retrieved_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def to_dict(self) -> Dict[str, Any]:
        """Return the record as a plain dict."""
        return dict(self.__dict__)


class BseeClient:
    """Download and unpack the allow-listed BSEE files."""

    def __init__(self, fetch: Fetch = default_fetch, cache_dir: Optional[Path] = None, *, timeout: float = 120.0) -> None:
        self.fetch = fetch
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.timeout = timeout
        self.records: List[ReadRecord] = []

    def get_text(self, source: str) -> str:
        """Return the unpacked CSV text of ``source`` (``"investigations"`` or ``"structures"``)."""
        if source not in SOURCES:
            raise KeyError(f"unknown source {source!r}; choose from {sorted(SOURCES)}")
        spec = SOURCES[source]
        url = HOST + spec["path"]
        cache_file = self.cache_dir / (spec["path"].rsplit("/", 1)[1]) if self.cache_dir else None
        cached = cache_file is not None and cache_file.exists()
        body = cache_file.read_bytes() if cached else self.fetch(url, self.timeout, MAX_ZIP_BYTES)
        try:
            archive = zipfile.ZipFile(io.BytesIO(body))
        except zipfile.BadZipFile as error:
            raise SourceError(f"{url} did not return a zip file (the server sends HTML for a wrong path)") from error
        if cache_file is not None and not cached:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_bytes(body)
        member = next((n for n in archive.namelist() if n.replace("\\", "/").rsplit("/", 1)[-1] == spec["member"]), None)
        if member is None:
            raise SourceError(f"{spec['member']} missing from {url}; BSEE may have changed the file")
        info = archive.getinfo(member)
        if info.file_size > MAX_MEMBER_BYTES:
            raise SourceError(f"{spec['member']} unpacks to {info.file_size} bytes, above the limit")
        text = archive.read(info).decode("utf-8-sig", errors="replace")
        self.records.append(ReadRecord(source, url, hashlib.sha256(body).hexdigest(), len(body), cached))
        return text

    def provenance(self) -> List[Dict[str, Any]]:
        """All read records as dicts."""
        return [r.to_dict() for r in self.records]
