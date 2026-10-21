"""Parse operator statements that use an indented label hierarchy with TOTAL rows.

Joint Interest Billing (JIB) spreadsheets, cost-recovery statements and many ERP
exports share one layout: the first N columns hold hierarchy labels that are
only written when they change, detail lines carry the numbers, and
``TOTAL <label>`` rows close each group. This module turns that layout into a
tidy table and checks that every TOTAL equals the sum of the detail lines it
closes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence

import pandas as pd


COUNT = "__detail_lines__"


def to_number(value: Any) -> Optional[float]:
    """Convert a spreadsheet cell to a float.

    Args:
        value: Cell content. Numbers, numeric strings with thousands separators
            and accounting negatives such as ``(1,250.5)`` are accepted.

    Returns:
        The numeric value, or ``None`` for blank or non-numeric cells.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace(",", "").replace(" ", "")
    try:
        number = float(text)
    except ValueError:
        return None
    return -number if negative else number


def _clean(value: Any) -> Optional[str]:
    """Return a stripped string label or ``None`` when blank."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass
class ParsedStatement:
    """Result of :func:`parse_hierarchical_rows`.

    Attributes:
        detail: One row per detail line with ``L0..Ln`` path labels, the
            deepest ``label``, any extra columns, the numeric columns and
            ``src_row`` (spreadsheet row number).
        totals: One row per TOTAL line with its ``level``, ``label``, path,
            numeric columns and, per numeric column ``<name>_expected``
            (sum of the detail lines the total closes).
        value_names: Names of the numeric columns.
    """

    detail: pd.DataFrame
    totals: pd.DataFrame
    value_names: list


def parse_hierarchical_rows(
    rows: Iterable[Sequence[Any]],
    label_cols: Sequence[int],
    value_cols: Mapping[str, int],
    extra_cols: Optional[Mapping[str, int]] = None,
    first_row: int = 1,
    total_prefix: str = "TOTAL",
) -> ParsedStatement:
    """Parse rows of a hierarchical statement into detail and total tables.

    Args:
        rows: Iterable of row sequences (0-based columns), e.g. from
            ``openpyxl`` ``iter_rows(values_only=True)``.
        label_cols: Column indexes of the hierarchy labels, outermost first.
        value_cols: Mapping of output name to numeric column index.
        extra_cols: Optional mapping of output name to a text column index that
            is kept on detail lines without participating in the hierarchy
            (for example an account number or AFE name).
        first_row: Spreadsheet row number of the first item in ``rows``.
        total_prefix: Case-insensitive prefix that marks a closing total row.

    Returns:
        A :class:`ParsedStatement` with the detail and total tables.

    Raises:
        ValueError: If ``label_cols`` or ``value_cols`` is empty.
    """
    if not label_cols or not value_cols:
        raise ValueError("label_cols and value_cols must not be empty")
    extra_cols = dict(extra_cols or {})
    names = list(value_cols)
    depth = len(label_cols)
    prefix = total_prefix.lower()
    current: list = [None] * depth
    acc = [dict.fromkeys(names + [COUNT], 0.0) for _ in range(depth)]
    siblings = [dict.fromkeys(names, 0.0) for _ in range(depth)]
    sibling_count = [0] * depth
    detail_rows: list = []
    total_rows: list = []

    def width_needed() -> int:
        return max(list(label_cols) + list(value_cols.values()) + list(extra_cols.values())) + 1

    need = width_needed()
    for offset, raw in enumerate(rows):
        row = list(raw) + [None] * max(0, need - len(raw))
        labels = [_clean(row[c]) for c in label_cols]
        values = {n: to_number(row[c]) for n, c in value_cols.items()}
        has_values = any(v is not None for v in values.values())
        total_level = next(
            (i for i, lab in enumerate(labels) if lab and lab.lower().startswith(prefix)),
            None,
        )
        for i, lab in enumerate(labels):
            if lab and i != total_level:
                current[i] = lab
                for j in range(i + 1, depth):
                    current[j] = None
                for j in range(i, depth):
                    acc[j] = dict.fromkeys(names + [COUNT], 0.0)
                for j in range(i + 1, depth):
                    siblings[j] = dict.fromkeys(names, 0.0)
                    sibling_count[j] = 0
                if i == 0:
                    siblings[0] = dict.fromkeys(names, 0.0)
                    sibling_count[0] = 0
        if not has_values:
            continue
        src_row = first_row + offset
        filled = {n: (v if v is not None else 0.0) for n, v in values.items()}
        if total_level is not None:
            record = {f"L{k}": current[k] for k in range(total_level)}
            record.update(
                level=total_level,
                label=labels[total_level],
                src_row=src_row,
                **filled,
            )
            for n in names:
                record[f"{n}_expected"] = acc[total_level][n]
            # A total with no detail lines since the previous total at its level
            # is a grand total of the sibling totals that preceded it.
            is_grand = (
                sibling_count[total_level] > 0
                and acc[total_level][COUNT] == 0
            )
            record["kind"] = "grand_total" if is_grand else "subtotal"
            if is_grand:
                for n in names:
                    record[f"{n}_expected"] = siblings[total_level][n]
                siblings[total_level] = dict.fromkeys(names, 0.0)
                sibling_count[total_level] = 0
            else:
                for n in names:
                    siblings[total_level][n] += filled[n]
                sibling_count[total_level] += 1
            total_rows.append(record)
            # Sibling groups often share one outer label (several TOTAL rows
            # under one CATEGORY), so only deeper labels are cleared.
            for j in range(total_level + 1, depth):
                current[j] = None
            for j in range(total_level, depth):
                acc[j] = dict.fromkeys(names + [COUNT], 0.0)
            continue
        record = {f"L{k}": current[k] for k in range(depth)}
        deepest = next((lab for lab in reversed(current) if lab), None)
        record["label"] = deepest
        for out, col in extra_cols.items():
            record[out] = _clean(row[col])
        record.update(src_row=src_row, **filled)
        detail_rows.append(record)
        for j in range(depth):
            acc[j][COUNT] += 1
            for n in names:
                acc[j][n] += filled[n]

    return ParsedStatement(
        detail=pd.DataFrame(detail_rows),
        totals=pd.DataFrame(total_rows),
        value_names=names,
    )


def check_subtotals(
    parsed: ParsedStatement, tol_abs: float = 1.0, tol_rel: float = 1e-6
) -> pd.DataFrame:
    """List TOTAL rows that do not equal the sum of their detail lines.

    Args:
        parsed: Output of :func:`parse_hierarchical_rows`.
        tol_abs: Absolute tolerance in the statement currency.
        tol_rel: Relative tolerance against the larger of reported/expected.

    Returns:
        Failing TOTAL rows with ``<name>_diff`` columns and ``max_abs_diff``,
        sorted by the largest absolute difference. Empty if all totals agree.
    """
    totals = parsed.totals.copy()
    if totals.empty:
        return totals
    diffs = []
    for n in parsed.value_names:
        totals[f"{n}_diff"] = totals[n] - totals[f"{n}_expected"]
        scale = totals[[n, f"{n}_expected"]].abs().max(axis=1)
        limit = (scale * tol_rel).clip(lower=tol_abs)
        totals[f"{n}_fail"] = totals[f"{n}_diff"].abs() > limit
        diffs.append(f"{n}_diff")
    totals["max_abs_diff"] = totals[diffs].abs().max(axis=1)
    failing = totals[totals[[f"{n}_fail" for n in parsed.value_names]].any(axis=1)]
    return failing.sort_values("max_abs_diff", ascending=False).reset_index(drop=True)
