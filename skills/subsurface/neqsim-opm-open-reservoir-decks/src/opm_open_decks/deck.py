"""Light-weight parser for ECLIPSE/OPM-style ``.DATA`` decks: summary, keyword tables and INCLUDE paths."""

from __future__ import annotations

import posixpath
import re
from typing import Any, Dict, List, Optional

_KEYWORD = re.compile(r"^[A-Z][A-Z0-9_]{1,7}$")
_SECTIONS = ("RUNSPEC", "GRID", "EDIT", "PROPS", "REGIONS", "SOLUTION", "SUMMARY", "SCHEDULE")
_UNITS = ("METRIC", "FIELD", "LAB", "PVT-M")
_PHASES = ("OIL", "GAS", "WATER", "DISGAS", "VAPOIL", "SOLVENT", "CO2STORE", "THERMAL")
_PVT_KEYWORDS = ("PVTO", "PVTG", "PVDG", "PVDO", "PVTW", "PVCDO", "DENSITY", "ROCK", "SWOF", "SGOF", "SWFN", "SGFN", "SOF3")


def strip_comments(text: str) -> List[str]:
    """Return the deck lines without ``--`` comments (a ``--`` inside quotes is kept)."""
    lines = []
    for raw in text.splitlines():
        out, quote = [], ""
        index = 0
        while index < len(raw):
            char = raw[index]
            if quote:
                if char == quote:
                    quote = ""
            elif char in "'\"":
                quote = char
            elif raw.startswith("--", index):
                break
            out.append(char)
            index += 1
        lines.append("".join(out).rstrip())
    return lines


def _blocks(lines: List[str], keyword: str) -> List[List[List[str]]]:
    blocks: List[List[List[str]]] = []
    for start, line in enumerate(lines):
        if line.strip() != keyword:
            continue
        body: List[str] = []
        for follow in lines[start + 1:]:
            if _KEYWORD.match(follow.strip()):
                break
            body.append(follow)
        records = [chunk.split() for chunk in " ".join(body).split("/")]
        while records and not records[-1]:
            records.pop()
        blocks.append(records)
    return blocks


def keyword_blocks(text: str, keyword: str) -> List[List[List[str]]]:
    """Return one record list per occurrence of ``keyword`` (schedule keywords repeat), see :func:`keyword_records`."""
    return _blocks(strip_comments(text), keyword)


def keyword_records(text: str, keyword: str) -> List[List[str]]:
    """Return the ``/``-terminated records after the first ``keyword`` as token lists.

    Reading stops at the next section or keyword line. An empty list in the result marks a table terminator
    (a lone ``/``), which separates PVT regions in ``PVTO``/``PVTG``/``SWOF``. Repeat tokens such as ``3*20`` are
    kept as written; use :func:`expand_repeats`. Returns ``[]`` when the keyword is absent. A data line made only of
    one unquoted upper-case word of 2-8 characters would be mistaken for a keyword.
    """
    blocks = _blocks(strip_comments(text), keyword)
    return blocks[0] if blocks else []


def expand_repeats(tokens: List[str]) -> List[str]:
    """Expand ``n*value`` tokens (``3*20`` becomes ``20 20 20``); ``n*`` (defaults) stays as ``1*``-style markers."""
    out: List[str] = []
    for token in tokens:
        match = re.fullmatch(r"(\d+)\*(.*)", token)
        if match:
            out.extend([match.group(2) or "*"] * int(match.group(1)))
        else:
            out.append(token)
    return out


def to_floats(tokens: List[str]) -> List[float]:
    """Convert tokens to floats after expanding repeats; raises ``ValueError`` on defaults or text."""
    return [float(t) for t in expand_repeats(tokens)]


def include_paths(text: str, after: Optional[str] = None) -> List[str]:
    """Return the paths named by ``INCLUDE`` and ``IMPORT`` keywords, in order, unquoted.

    With ``after="SCHEDULE"`` only includes that follow that section keyword are returned.
    """
    lines = strip_comments(text)
    if after:
        marker = next((i for i, line in enumerate(lines) if line.strip() == after), None)
        if marker is None:
            return []
        lines = lines[marker + 1:]
    paths: List[str] = []
    for index, line in enumerate(lines):
        if line.strip() in ("INCLUDE", "IMPORT"):
            for follow in lines[index + 1:index + 6]:
                match = re.search(r"['\"]([^'\"]+)['\"]", follow)
                if match:
                    paths.append(match.group(1))
                    break
                if follow.strip():
                    token = follow.split("/")[0].strip()
                    if token:
                        paths.append(token)
                        break
    return paths


def resolve_include(deck_path: str, include: str) -> str:
    """Resolve an INCLUDE path relative to the deck's directory; raises ``ValueError`` if it escapes the case."""
    base = posixpath.dirname(deck_path)
    resolved = posixpath.normpath(posixpath.join(base, include.replace("\\", "/")))
    if resolved.startswith("..") or resolved.startswith("/") or not re.fullmatch(r"[A-Za-z0-9_./\-]+", resolved):
        raise ValueError(f"INCLUDE path {include!r} leaves the case directory or has unsafe characters")
    return resolved


def schedule_facts(text: str) -> Dict[str, Any]:
    """Return wells (``WELSPECS``) and the number of ``TSTEP``/``DATES`` records found in schedule text."""
    wells: List[str] = []
    for block in keyword_blocks(text, "WELSPECS"):
        for record in block:
            if record:
                name = record[0].strip("'\"")
                if name not in wells:
                    wells.append(name)
    return {
        "wells": wells,
        "n_tstep_records": sum(len(b) for b in keyword_blocks(text, "TSTEP")),
        "n_dates_records": sum(len(b) for b in keyword_blocks(text, "DATES")),
    }


def summarize_deck(text: str) -> Dict[str, Any]:
    """Return units, phases, grid size, start date, wells, includes and PVT keywords of one deck file.

    Schedule data that sits in an INCLUDE file (as in Norne) is not read here; ``OpmDataClient.summary`` follows
    the includes that come after the ``SCHEDULE`` keyword and merges :func:`schedule_facts`.
    """
    lines = strip_comments(text)
    keywords = {line.strip() for line in lines if _KEYWORD.match(line.strip())}
    dimens = keyword_records(text, "DIMENS")
    start = keyword_records(text, "START")
    facts = schedule_facts(text)
    dims: Optional[List[int]] = None
    if dimens and len(dimens[0]) >= 3:
        dims = [int(float(v)) for v in dimens[0][:3]]
    return {
        "units": next((u for u in _UNITS if u in keywords), None),
        "phases": [p for p in _PHASES if p in keywords],
        "dimens": dims,
        "cells": dims[0] * dims[1] * dims[2] if dims else None,
        "start": " ".join(start[0]).replace("'", "") if start else None,
        "sections": [s for s in _SECTIONS if s in keywords],
        "wells": facts["wells"],
        "includes": include_paths(text),
        "schedule_includes": include_paths(text, after="SCHEDULE"),
        "pvt_keywords": [k for k in _PVT_KEYWORDS if k in keywords],
        "n_tstep_records": facts["n_tstep_records"],
        "n_dates_records": facts["n_dates_records"],
    }
