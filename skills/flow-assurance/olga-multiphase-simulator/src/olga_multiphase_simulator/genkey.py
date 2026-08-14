"""Minimal, non-destructive editing of OLGA genkey (``.genkey`` / ``.key``) input.

OLGA input is a keyword language::

    INTEGRATION ENDTIME=5 h, MAXDT=1 s, MINDT=0.001 s, STARTTIME=0 s
    PIPE LABEL=Pipe-1, DIAMETER=0.2 m, NSEGMENT=10, \\
         WALL="WALL-1"

Logical lines continue with a trailing backslash, ``!`` starts a comment, and a
keyword's arguments are comma-separated ``NAME=value`` pairs whose values may be
quoted or parenthesised lists carrying a unit.

This module reads and rewrites individual parameter values while leaving every
other byte of the file untouched, which is what a reproducible parametric study
needs. It is not a full genkey parser and does not validate physics — always run
:meth:`~olga_multiphase_simulator.runner.OlgaRunner.rule_check` on the result.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Mapping, Optional, Tuple

__all__ = [
    "GenkeyStatement",
    "iter_statements",
    "list_keywords",
    "get_parameter",
    "set_parameter",
    "apply_parameters",
    "parameter_overview",
    "write_variant",
]

_KEYWORD_RE = re.compile(r"^\s*(?P<keyword>[A-Za-z][A-Za-z0-9_]*)\b")


@dataclass(frozen=True)
class GenkeyStatement:
    """One logical genkey statement located in the raw file text."""

    keyword: str
    start: int
    end: int
    text: str


def iter_statements(text: str) -> Iterator[GenkeyStatement]:
    """Yield every logical statement in a genkey file, in file order.

    Continuation lines (trailing ``\\``) are folded into the parent statement and
    comment-only lines are skipped.
    """
    position = 0
    length = len(text)
    while position < length:
        line_end = text.find("\n", position)
        if line_end == -1:
            line_end = length
        start = position
        end = line_end
        # Fold continuation lines.
        while _continues(text[start:end]):
            if end >= length:
                break
            next_end = text.find("\n", end + 1)
            end = length if next_end == -1 else next_end
        statement_text = text[start:end]
        position = end + 1
        stripped = statement_text.lstrip()
        if not stripped or stripped.startswith("!"):
            continue
        match = _KEYWORD_RE.match(statement_text)
        if match is None:
            continue
        yield GenkeyStatement(
            keyword=match.group("keyword").upper(),
            start=start,
            end=end,
            text=statement_text,
        )


def _continues(segment: str) -> bool:
    stripped = segment.rstrip()
    return stripped.endswith("\\")


def list_keywords(text: str) -> List[str]:
    """Return the distinct keywords used in a genkey file, in first-seen order."""
    seen: List[str] = []
    for statement in iter_statements(text):
        if statement.keyword not in seen:
            seen.append(statement.keyword)
    return seen


def _find_statement(text: str, keyword: str, occurrence: int) -> GenkeyStatement:
    wanted = keyword.upper()
    matches = [s for s in iter_statements(text) if s.keyword == wanted]
    if not matches:
        raise KeyError(f"Keyword {keyword!r} not found in genkey input")
    try:
        return matches[occurrence]
    except IndexError as exc:
        raise KeyError(
            f"Keyword {keyword!r} occurs {len(matches)} time(s); occurrence {occurrence} requested"
        ) from exc


def _value_span(statement_text: str, parameter: str) -> Tuple[int, int]:
    """Return ``(start, end)`` of a parameter's value within a statement."""
    pattern = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(parameter.upper()) + r"\s*=\s*", re.IGNORECASE)
    match = pattern.search(statement_text)
    if match is None:
        raise KeyError(f"Parameter {parameter!r} not found in statement")
    index = match.end()
    depth = 0
    quote: Optional[str] = None
    while index < len(statement_text):
        char = statement_text[index]
        if quote is not None:
            if char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char in "([":
            depth += 1
        elif char in ")]":
            depth -= 1
        elif char == "," and depth <= 0:
            break
        elif char == "!" and depth <= 0:
            break
        index += 1
    return match.end(), index


def _clean_value(raw: str) -> str:
    """Collapse continuation markers and whitespace inside a captured value."""
    without_continuations = re.sub(r"\\\s*\n\s*", " ", raw)
    return re.sub(r"\s+", " ", without_continuations).strip()


def get_parameter(text: str, keyword: str, parameter: str, occurrence: int = 0) -> str:
    """Return a parameter value as written in the file (whitespace normalised).

    Args:
        text: Full genkey file content.
        keyword: Statement keyword, e.g. ``"INTEGRATION"`` (case-insensitive).
        parameter: Parameter name, e.g. ``"ENDTIME"`` (case-insensitive).
        occurrence: Which occurrence of ``keyword`` to read, 0-based.

    Raises:
        KeyError: If the keyword or the parameter is absent.
    """
    statement = _find_statement(text, keyword, occurrence)
    start, end = _value_span(statement.text, parameter)
    return _clean_value(statement.text[start:end])


def set_parameter(
    text: str,
    keyword: str,
    parameter: str,
    value: str,
    occurrence: int = 0,
) -> str:
    """Return a copy of ``text`` with one parameter value replaced.

    Args:
        text: Full genkey file content.
        keyword: Statement keyword, e.g. ``"INTEGRATION"``.
        parameter: Parameter name, e.g. ``"ENDTIME"``.
        value: Replacement value including its unit, e.g. ``"60 s"``.
        occurrence: Which occurrence of ``keyword`` to edit, 0-based.

    Raises:
        KeyError: If the keyword or the parameter is absent.
    """
    statement = _find_statement(text, keyword, occurrence)
    start, end = _value_span(statement.text, parameter)
    absolute_start = statement.start + start
    absolute_end = statement.start + end
    return text[:absolute_start] + str(value) + text[absolute_end:]


def apply_parameters(text: str, updates: Mapping[str, Mapping[str, str]]) -> str:
    """Apply several parameter overrides at once.

    Args:
        text: Full genkey file content.
        updates: ``{keyword: {parameter: value}}``; the first occurrence of each
            keyword is edited.

    Returns:
        The edited genkey content.
    """
    result = text
    for keyword, parameters in updates.items():
        for parameter, value in parameters.items():
            result = set_parameter(result, keyword, parameter, value)
    return result


def write_variant(
    source: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    updates: Mapping[str, Mapping[str, str]],
    encoding: str = "utf-8",
) -> Path:
    """Write a parameter variant of a genkey case next to its data files.

    Keep the variant in the same directory as the original so relative
    ``FILES PVTFILE=./x.tab`` references still resolve.

    Returns:
        The destination path.
    """
    source_path = Path(source)
    destination_path = Path(destination)
    text = source_path.read_text(encoding=encoding, errors="replace")
    destination_path.write_text(apply_parameters(text, updates), encoding=encoding)
    return destination_path


def parameter_overview(text: str, keyword: str, occurrence: int = 0) -> Dict[str, str]:
    """Return every ``NAME=value`` pair of one statement as a dictionary."""
    statement = _find_statement(text, keyword, occurrence)
    overview: Dict[str, str] = {}
    for match in re.finditer(r"(?<![A-Za-z0-9_])([A-Za-z][A-Za-z0-9_]*)\s*=", statement.text):
        name = match.group(1)
        start, end = _value_span(statement.text, name)
        overview[name.upper()] = _clean_value(statement.text[start:end])
    return overview
