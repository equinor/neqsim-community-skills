"""Find and cache ANP well-production files with a provenance record."""

from __future__ import annotations

import datetime as _dt
import hashlib
import html
import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urljoin

from .catalog import FAMILIES


def extract_links(page_html: str, family: str, base: Optional[str] = None) -> List[Dict[str, str]]:
    """List the data-file links of one family on an ANP open-data page.

    The page is the only reliable index: file names change between years, so a
    URL is never built from a pattern.

    Args:
        page_html: HTML of ``FAMILIES[family]["page"]``.
        family: Family key of :data:`anp_well_production.catalog.FAMILIES`.
        base: Base URL for relative links; defaults to the family page.

    Returns:
        List of ``{"url", "name"}`` in page order, without duplicates.

    Raises:
        KeyError: Unknown family.
    """
    spec = FAMILIES[family]
    base = base or spec["page"]
    seen, out = set(), []
    for href in re.findall(r'href="([^"]+)"', page_html, flags=re.IGNORECASE):
        href = html.unescape(href).strip()
        if spec["link_marker"] not in href or not href.lower().split("?")[0].endswith(spec["link_suffix"]):
            continue
        url = urljoin(base, href)
        if url in seen:
            continue
        seen.add(url)
        out.append({"url": url, "name": url.rsplit("/", 1)[-1]})
    return out


def _default_get(url: str, timeout: float) -> bytes:
    try:
        import requests  # type: ignore

        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.content
    except ImportError:  # pragma: no cover - exercised only without requests
        import urllib.request

        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
            return resp.read()


def download(
    url: str,
    cache_dir: str | Path,
    offline: bool = False,
    getter: Optional[Callable[[str, float], bytes]] = None,
    timeout: float = 300.0,
) -> Tuple[Path, Dict[str, Any]]:
    """Download one file into a task-local cache and write a provenance log.

    The log (``<file>.log.json``) holds the URL, retrieval time, byte count and
    SHA-256; copy it into the task ``SOURCES.md``.

    Args:
        url: File URL taken from :func:`extract_links`.
        cache_dir: Task folder for downloaded files.
        offline: Never touch the network; a missing file is an error.
        getter: Optional ``getter(url, timeout) -> bytes`` (used by tests).
        timeout: Network timeout in seconds.

    Returns:
        ``(path, log)``.

    Raises:
        FileNotFoundError: Offline and the file is not cached.
    """
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    path = cache / ("anp_%s_%s" % (key, url.rsplit("/", 1)[-1]))
    meta = path.with_name(path.name + ".log.json")
    if path.exists():
        log = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {"url": url}
        log["status"] = "cache"
        return path, log
    if offline:
        raise FileNotFoundError("Offline and not cached: %s" % url)
    raw = (getter or _default_get)(url, timeout)
    path.write_bytes(raw)
    log = {
        "url": url,
        "file": path.name,
        "retrieved_utc": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "status": "downloaded",
    }
    meta.write_text(json.dumps(log, indent=2), encoding="utf-8")
    return path, log
