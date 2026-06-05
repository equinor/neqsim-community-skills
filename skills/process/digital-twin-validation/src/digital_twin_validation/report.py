from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from math import isfinite
from typing import Optional


@dataclass(frozen=True)
class Tolerance:
    """A tolerance specification.

    ``kind`` is ``"abs"`` (absolute, in the channel unit) or ``"pct"``
    (percentage of the measured value).
    """

    value: float
    kind: str = "abs"

    def __post_init__(self) -> None:
        if not isinstance(self.value, (int, float)) or not isfinite(self.value):
            raise ValueError("tolerance value must be a finite number")
        if self.value <= 0.0:
            raise ValueError("tolerance value must be positive")
        if self.kind not in ("abs", "pct"):
            raise ValueError("tolerance kind must be 'abs' or 'pct'")


@dataclass(frozen=True)
class ChannelSpec:
    """A channel to compare, with its tolerance and unit."""

    name: str
    tolerance: Tolerance
    unit: str = ""


@dataclass(frozen=True)
class ChannelResult:
    channel: str
    measured: Optional[float]
    simulated: Optional[float]
    difference: Optional[float]
    rel_pct: Optional[float]
    tolerance: Tolerance
    unit: str
    passed: Optional[bool]  # None means SKIP (missing data)


@dataclass
class PointResult:
    point_id: str
    channels: list[ChannelResult] = field(default_factory=list)

    @property
    def status(self) -> str:
        decided = [c for c in self.channels if c.passed is not None]
        if not decided:
            return "SKIP"
        return "PASS" if all(c.passed for c in decided) else "FAIL"


def check_tolerance(
    measured: float, simulated: float, tolerance: Tolerance
) -> tuple[bool, float, float]:
    """Return ``(passed, difference, rel_pct)`` for a single comparison."""
    difference = simulated - measured
    rel_pct = abs(difference) / (abs(measured) + 1e-12) * 100.0
    if tolerance.kind == "abs":
        passed = abs(difference) <= tolerance.value
    else:
        passed = rel_pct <= tolerance.value
    return passed, difference, rel_pct


def evaluate_point(
    point_id: str,
    measured: dict[str, float],
    simulated: dict[str, float],
    specs: list[ChannelSpec],
) -> PointResult:
    """Evaluate one operating point against a list of channel specs."""
    result = PointResult(point_id=point_id)
    for spec in specs:
        meas = measured.get(spec.name)
        sim = simulated.get(spec.name)
        if meas is None or sim is None:
            result.channels.append(ChannelResult(
                channel=spec.name, measured=meas, simulated=sim,
                difference=None, rel_pct=None, tolerance=spec.tolerance,
                unit=spec.unit, passed=None,
            ))
            continue
        passed, difference, rel_pct = check_tolerance(meas, sim, spec.tolerance)
        result.channels.append(ChannelResult(
            channel=spec.name, measured=meas, simulated=sim,
            difference=difference, rel_pct=rel_pct, tolerance=spec.tolerance,
            unit=spec.unit, passed=passed,
        ))
    return result


@dataclass
class ValidationReport:
    name: str = "validation"
    points: list[PointResult] = field(default_factory=list)

    def add(self, point: PointResult) -> None:
        self.points.append(point)

    @property
    def status(self) -> str:
        decided = [p for p in self.points if p.status != "SKIP"]
        if not decided:
            return "SKIP"
        return "PASS" if all(p.status == "PASS" for p in decided) else "FAIL"

    def pass_rate(self) -> Optional[float]:
        """Fraction of decided points that pass, or ``None`` if none decided."""
        decided = [p for p in self.points if p.status != "SKIP"]
        if not decided:
            return None
        passed = sum(1 for p in decided if p.status == "PASS")
        return passed / len(decided)

    def summary_rows(self) -> list[dict]:
        rows: list[dict] = []
        for point in self.points:
            for ch in point.channels:
                rows.append({
                    "point_id": point.point_id,
                    "channel": ch.channel,
                    "unit": ch.unit,
                    "measured": ch.measured,
                    "simulated": ch.simulated,
                    "difference": ch.difference,
                    "rel_pct": ch.rel_pct,
                    "tolerance": ch.tolerance.value,
                    "tolerance_kind": ch.tolerance.kind,
                    "passed": ch.passed,
                })
        return rows

    def to_html(self) -> str:
        rate = self.pass_rate()
        rate_str = "n/a" if rate is None else f"{rate * 100:.1f}%"
        head = (
            "<html><head><meta charset='utf-8'>"
            f"<title>{escape(self.name)} validation</title>"
            "<style>body{font-family:sans-serif;margin:1.5rem}"
            "table{border-collapse:collapse}td,th{border:1px solid #ccc;"
            "padding:4px 8px;text-align:right}th{background:#f0f0f0}"
            ".pass{color:#1b7f1b}.fail{color:#b00020}.skip{color:#888}</style></head><body>"
        )
        header = (
            f"<h1>{escape(self.name)}</h1>"
            f"<p>Overall: <b class='{self.status.lower()}'>{self.status}</b> "
            f"&nbsp; Pass rate: {rate_str}</p>"
        )
        thead = (
            "<table><tr><th>point</th><th>channel</th><th>unit</th>"
            "<th>measured</th><th>simulated</th><th>Δ</th><th>rel %</th>"
            "<th>tol</th><th>result</th></tr>"
        )
        body_rows = []
        for row in self.summary_rows():
            if row["passed"] is None:
                verdict, cls = "SKIP", "skip"
            elif row["passed"]:
                verdict, cls = "PASS", "pass"
            else:
                verdict, cls = "FAIL", "fail"

            def fmt(value: Optional[float]) -> str:
                return "" if value is None else f"{value:.3f}"

            tol = f"{row['tolerance']:g} {row['tolerance_kind']}"
            body_rows.append(
                f"<tr><td>{escape(str(row['point_id']))}</td>"
                f"<td>{escape(str(row['channel']))}</td>"
                f"<td>{escape(str(row['unit']))}</td>"
                f"<td>{fmt(row['measured'])}</td>"
                f"<td>{fmt(row['simulated'])}</td>"
                f"<td>{fmt(row['difference'])}</td>"
                f"<td>{fmt(row['rel_pct'])}</td>"
                f"<td>{escape(tol)}</td>"
                f"<td class='{cls}'>{verdict}</td></tr>"
            )
        return head + header + thead + "".join(body_rows) + "</table></body></html>"
