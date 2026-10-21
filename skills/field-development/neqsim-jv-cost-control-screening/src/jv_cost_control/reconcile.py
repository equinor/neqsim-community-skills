"""Reconciliation, roll-forward and arithmetic identity checks."""

from __future__ import annotations

import ast
import operator
from dataclasses import dataclass
from typing import Mapping, Sequence, Tuple

import pandas as pd

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


def reconcile_tables(
    a: pd.DataFrame,
    b: pd.DataFrame,
    key: Sequence[str],
    value_a: str,
    value_b: str,
    tol_abs: float = 1.0,
    tol_rel: float = 0.0005,
    names: Tuple[str, str] = ("a", "b"),
) -> pd.DataFrame:
    """Reconcile two sources on a shared key.

    Args:
        a: First table (for example the JIB).
        b: Second table (for example a cost-recovery report).
        key: Key columns present in both tables.
        value_a: Value column in ``a``.
        value_b: Value column in ``b``.
        tol_abs: Absolute tolerance.
        tol_rel: Relative tolerance on the larger absolute value.
        names: Short source names used in column labels.

    Returns:
        Outer-joined table with ``diff`` and ``status`` (``MATCH``, ``DIFF``,
        ``ONLY_<a>`` or ``ONLY_<b>``), sorted by absolute difference.
    """
    left = a.groupby(list(key), dropna=False)[value_a].sum().rename(names[0]).reset_index()
    right = b.groupby(list(key), dropna=False)[value_b].sum().rename(names[1]).reset_index()
    merged = left.merge(right, on=list(key), how="outer", indicator=True)
    merged[[names[0], names[1]]] = merged[[names[0], names[1]]].fillna(0.0)
    merged["diff"] = merged[names[0]] - merged[names[1]]
    scale = merged[[names[0], names[1]]].abs().max(axis=1)
    limit = (scale * tol_rel).clip(lower=tol_abs)
    status = pd.Series("DIFF", index=merged.index)
    status[merged["diff"].abs() <= limit] = "MATCH"
    status[merged["_merge"] == "left_only"] = f"ONLY_{names[0]}"
    status[merged["_merge"] == "right_only"] = f"ONLY_{names[1]}"
    merged["status"] = status
    merged = merged.drop(columns="_merge")
    order = merged["diff"].abs().sort_values(ascending=False).index
    return merged.loc[order].reset_index(drop=True)


def rollforward_check(
    prior_ytd: pd.Series,
    current_month: pd.Series,
    current_ytd: pd.Series,
    tol_abs: float = 1.0,
) -> pd.DataFrame:
    """Check ``YTD(t) = YTD(t-1) + month(t)`` per line.

    Args:
        prior_ytd: YTD amounts from the previous statement, indexed by key.
        current_month: Current-month amounts, indexed by key.
        current_ytd: Current YTD amounts, indexed by key.
        tol_abs: Absolute tolerance.

    Returns:
        Table with ``expected_ytd``, ``diff`` and ``flag``; ``diff`` shows
        retroactive adjustments the operator posted to earlier months.
    """
    frame = pd.concat(
        {"prior_ytd": prior_ytd, "current_month": current_month, "current_ytd": current_ytd}, axis=1
    ).fillna(0.0)
    frame["expected_ytd"] = frame["prior_ytd"] + frame["current_month"]
    frame["diff"] = frame["current_ytd"] - frame["expected_ytd"]
    frame["flag"] = frame["diff"].abs() > tol_abs
    return frame.sort_values("diff", key=lambda s: s.abs(), ascending=False)


@dataclass
class IdentityResult:
    """Outcome of one arithmetic identity check.

    Attributes:
        name: Identity label.
        lhs: Left-hand side value.
        rhs: Right-hand side value.
        diff: ``lhs - rhs``.
        ok: Whether ``|diff|`` is within the tolerance.
        expression: The right-hand side expression text.
    """

    name: str
    lhs: float
    rhs: float
    diff: float
    ok: bool
    expression: str


def _evaluate(node: ast.AST, values: Mapping[str, float]) -> float:
    """Evaluate a restricted arithmetic expression tree.

    Args:
        node: AST node (BinOp, UnaryOp, Name or Constant only).
        values: Mapping of variable names to numbers.

    Returns:
        The numeric result.

    Raises:
        ValueError: On unsupported syntax or an unknown name.
    """
    if isinstance(node, ast.Expression):
        return _evaluate(node.body, values)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id not in values:
            raise ValueError(f"unknown name {node.id}")
        return float(values[node.id])
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_evaluate(node.left, values), _evaluate(node.right, values))
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = _evaluate(node.operand, values)
        return -value if isinstance(node.op, ast.USub) else value
    raise ValueError("unsupported expression")


def check_identities(
    values: Mapping[str, float],
    identities: Sequence[Tuple[str, str, str]],
    tol_abs: float = 2.0,
) -> list:
    """Verify arithmetic identities such as ``RC14 = RC10 + RC12 + RC13``.

    Args:
        values: Mapping of line code to value (for one column/party).
        identities: Items of ``(name, lhs_code, rhs_expression)``; the
            expression may use ``+ - * /``, parentheses, numbers and codes.
        tol_abs: Absolute tolerance (statement rounding).

    Returns:
        List of :class:`IdentityResult`; identities with missing codes are
        returned with ``ok=False`` and ``NaN`` values.
    """
    results = []
    for name, lhs_code, expression in identities:
        try:
            lhs = float(values[lhs_code])
            rhs = _evaluate(ast.parse(expression, mode="eval"), values)
        except (KeyError, ValueError, ZeroDivisionError):
            results.append(IdentityResult(name, float("nan"), float("nan"), float("nan"), False, expression))
            continue
        diff = lhs - rhs
        results.append(IdentityResult(name, lhs, rhs, diff, abs(diff) <= tol_abs, expression))
    return results
