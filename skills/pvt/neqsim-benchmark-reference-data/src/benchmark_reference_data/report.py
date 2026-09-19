"""Aggregate benchmark results into the ``benchmark_validation`` report block.

The output shape is the keyed-object form that both the task-report generator
(``step3_report/generate_report.py``) and the CI gate
(``devtools/validate_task_results.py`` / ``neqsim.util.agentic.TaskResultValidator``)
accept. ``to_results_json_list`` produces the array form for consumers that
prefer it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .comparison import (
    STATUS_FAIL,
    STATUS_INFO,
    STATUS_PASS,
    STATUS_WARN,
    BenchmarkResult,
)

#: A task report must show at least this many independent comparison points.
MINIMUM_POINTS = 3

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    return _SLUG_RE.sub("_", text.strip().lower()).strip("_") or "case"


@dataclass
class BenchmarkReport:
    """A set of benchmark results plus the roll-up the report and gate need."""

    results: List[BenchmarkResult] = field(default_factory=list)
    title: str = "Benchmark validation"
    description: str = ""

    def add(self, result: BenchmarkResult) -> "BenchmarkReport":
        """Append one result and return self so calls can be chained."""
        self.results.append(result)
        return self

    def extend(self, results: List[BenchmarkResult]) -> "BenchmarkReport":
        """Append several results and return self."""
        self.results.extend(results)
        return self

    def counts(self) -> Dict[str, int]:
        """Number of results per status."""
        tally = {STATUS_PASS: 0, STATUS_WARN: 0, STATUS_FAIL: 0, STATUS_INFO: 0}
        for result in self.results:
            tally[result.status] = tally.get(result.status, 0) + 1
        return tally

    @property
    def overall_status(self) -> str:
        """FAIL beats WARN beats PASS; an empty or purely informational set is INFO."""
        tally = self.counts()
        if tally[STATUS_FAIL]:
            return STATUS_FAIL
        if tally[STATUS_WARN]:
            return STATUS_WARN
        if tally[STATUS_PASS]:
            return STATUS_PASS
        return STATUS_INFO

    def graded_points(self) -> int:
        """Number of results that actually graded the model (not INFO)."""
        return sum(1 for r in self.results if r.status != STATUS_INFO)

    def meets_minimum_points(self, minimum: int = MINIMUM_POINTS) -> bool:
        """True when enough graded comparisons exist to satisfy the task rules."""
        return self.graded_points() >= minimum

    def sources_used(self) -> List[str]:
        """Distinct reference source keys, in first-seen order."""
        seen: List[str] = []
        for result in self.results:
            if result.source_key not in seen:
                seen.append(result.source_key)
        return seen

    def citations(self) -> List[str]:
        """Distinct citation strings for the report's reference list."""
        seen: List[str] = []
        for result in self.results:
            if result.citation and result.citation not in seen:
                seen.append(result.citation)
        return seen

    def blockers(self, minimum: int = MINIMUM_POINTS) -> List[str]:
        """Reasons the benchmark block should not be presented as validated."""
        issues: List[str] = []
        if not self.meets_minimum_points(minimum):
            issues.append(
                "only {} graded comparison(s); at least {} are required".format(
                    self.graded_points(), minimum
                )
            )
        failed = [r.name for r in self.results if r.status == STATUS_FAIL]
        if failed:
            issues.append("failed comparisons: {}".format(", ".join(failed)))
        dependent = [r.name for r in self.results if not r.independent]
        if dependent:
            issues.append(
                "reference not independent of the model basis: {}".format(
                    ", ".join(dependent)
                )
            )
        return issues

    def to_results_json(self) -> Dict[str, object]:
        """Keyed-object ``benchmark_validation`` block for ``results.json``.

        Summary fields are kept scalar so the report generator renders them as a
        readable row rather than a nested repr.
        """
        block: Dict[str, object] = {}
        used: Dict[str, int] = {}
        for result in self.results:
            key = _slug(result.name)
            used[key] = used.get(key, 0) + 1
            if used[key] > 1:
                key = "{}_{}".format(key, used[key])
            block[key] = result.to_dict()
        tally = self.counts()
        blockers = self.blockers()
        block["summary"] = {
            "description": self.description or self.title,
            "status": self.overall_status,
            "points": len(self.results),
            "graded_points": self.graded_points(),
            "passed": tally[STATUS_PASS],
            "warned": tally[STATUS_WARN],
            "failed": tally[STATUS_FAIL],
            "informational": tally[STATUS_INFO],
            "sources": ", ".join(self.sources_used()),
            "blockers": "; ".join(blockers) if blockers else "none",
        }
        return block

    def to_results_json_list(self) -> List[Dict[str, object]]:
        """Array form of the same block."""
        entries = []
        for result in self.results:
            payload = result.to_dict()
            payload["what"] = result.name
            entries.append(payload)
        return entries

    def to_markdown(self, max_note_chars: Optional[int] = 80) -> str:
        """Markdown table for a notebook cell or the report body."""
        header = (
            "| Case | Property | Model | Reference | Dev. % | Tol. % | Status |\n"
            "| --- | --- | --- | --- | --- | --- | --- |\n"
        )
        rows = []
        for result in self.results:
            deviation = (
                "-" if result.deviation_pct is None else "{:+.3g}".format(result.deviation_pct)
            )
            rows.append(
                "| {} | {} | {:.6g} {} | {:.6g} {} | {} | {:.3g} | {} |".format(
                    result.name,
                    result.property_name,
                    result.model_value,
                    result.unit,
                    result.reference_value,
                    result.unit,
                    deviation,
                    result.tolerance_pct,
                    result.status,
                )
            )
        table = header + "\n".join(rows)
        summary = "\n\nOverall: **{}** ({} graded of {} points).".format(
            self.overall_status, self.graded_points(), len(self.results)
        )
        blockers = self.blockers()
        if blockers:
            summary += "\n\nBlockers:\n" + "\n".join("- " + b for b in blockers)
        if max_note_chars:
            notes = [
                "- {}: {}".format(r.name, r.note[:max_note_chars])
                for r in self.results
                if r.note
            ]
            if notes:
                summary += "\n\nNotes:\n" + "\n".join(notes)
        return table + summary
