"""Build the ``uncertainty`` block for ``results.json`` and the report.

The emitted shape is what ``step3_report/generate_report.py`` renders and what
``devtools/validate_task_results.py`` / ``neqsim.util.agentic.TaskResultValidator``
validate: ``p10 <= p50 <= p90`` ascending, an ``input_parameters`` table, and a
``tornado`` list whose columns are auto-detected from the first row.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from .distributions import Distribution
from .study import StudyResult, TornadoEntry
from .summary_stats import MINIMUM_SAMPLES_SIMULATION

#: Median drift between run halves, as a percent of the P10-P90 spread, above
#: which percentiles should not be quoted.
MAX_MEDIAN_DRIFT_PCT = 5.0


@dataclass
class UncertaintyReport:
    """Assemble the ``uncertainty`` block from a study result."""

    parameters: Sequence[Distribution]
    result: StudyResult
    output_name: str = "output"
    output_unit: str = ""
    tornado: list[TornadoEntry] = field(default_factory=list)
    simulation_engine: str = ""
    sensitivity: dict[str, Any] | None = None
    minimum_samples: int = MINIMUM_SAMPLES_SIMULATION

    @property
    def output_parameter(self) -> str:
        """Label used for the output distribution table."""
        if self.output_unit:
            return f"{self.output_name} ({self.output_unit})"
        return self.output_name

    def tornado_prefix(self) -> str:
        """Column prefix for the tornado table, derived from the output name."""
        token = self.output_name.strip().lower().split("(")[0].strip()
        token = "_".join(part for part in token.replace("-", " ").split() if part)
        return token or "output"

    def blockers(self) -> list[str]:
        """Reasons the uncertainty block should not be presented as converged."""
        issues: list[str] = []
        summary = self.result.summary
        if summary.count < self.minimum_samples:
            issues.append(
                f"{summary.count} samples is below the {self.minimum_samples}-sample minimum for a simulation-backed "
                "Monte Carlo"
            )
        if summary.drift_pct > MAX_MEDIAN_DRIFT_PCT:
            issues.append(
                f"median drifts {summary.drift_pct:.1f}% of the P10-P90 spread between run halves "
                f"(limit {MAX_MEDIAN_DRIFT_PCT:.1f}%) — increase the sample count"
            )
        if self.result.failures:
            issues.append(
                f"{self.result.failures} evaluation(s) failed and were dropped"
            )
        if not self.tornado:
            issues.append("no tornado sensitivity was produced")
        return issues

    def to_results_json(self) -> dict[str, Any]:
        """The ``uncertainty`` block."""
        summary = self.result.summary
        prefix = self.tornado_prefix()
        block: dict[str, Any] = {
            "method": f"Monte Carlo, {self.result.sampling_method.upper()} sampling",
            "sampling_method": self.result.sampling_method,
            "seed": self.result.seed,
            "simulation_engine": self.simulation_engine,
            "input_parameters": [p.to_dict() for p in self.parameters],
            "output_parameter": self.output_parameter,
            "percentile_convention": "p10 = 10th percentile (low estimate)",
        }
        block.update(summary.to_dict())
        block["tornado"] = [entry.to_row(prefix) for entry in self.tornado]
        block["model_evaluations"] = dict(self.result.cache_report)
        if self.result.failures:
            block["failed_evaluations"] = self.result.failures
        if self.sensitivity:
            block["global_sensitivity"] = {
                key: value
                for key, value in self.sensitivity.items()
                if key not in ("surrogate", "joint")
            }
        blockers = self.blockers()
        block["blockers"] = "; ".join(blockers) if blockers else "none"
        return block

    def to_markdown(self) -> str:
        """Markdown summary for a notebook cell or the report body."""
        summary = self.result.summary
        unit = f" {self.output_unit}" if self.output_unit else ""
        lines = [
            f"**{self.output_parameter}** — {summary.count} samples, {self.result.sampling_method.upper()} sampling.",
            "",
            "| Statistic | Value |",
            "| --- | --- |",
            f"| P10 (low) | {summary.p10:.6g}{unit} |",
            f"| P50 (median) | {summary.p50:.6g}{unit} |",
            f"| P90 (high) | {summary.p90:.6g}{unit} |",
            f"| Mean | {summary.mean:.6g}{unit} |",
            f"| Std. dev. | {summary.std:.6g}{unit} |",
            f"| P(negative) | {summary.prob_negative_pct:.1f} % |",
            f"| Median drift (% of P10-P90 spread) | {summary.drift_pct:.2f} % |",
        ]
        if self.tornado:
            lines += [
                "",
                "| Parameter | Low | High | Swing |",
                "| --- | --- | --- | --- |",
            ]
            for entry in self.tornado:
                lines.append(
                    f"| {entry.parameter} | {entry.output_low:.6g} | {entry.output_high:.6g} | {entry.swing:.6g} |"
                )
        cache = self.result.cache_report
        if cache.get("cache_hits"):
            lines += [
                "",
                "Model evaluations: {} technical (expensive), {} economic (cheap), "
                "{} served from cache.".format(
                    cache.get("technical_evaluations", 0),
                    cache.get("economic_evaluations", 0),
                    cache.get("cache_hits", 0),
                ),
            ]
        blockers = self.blockers()
        if blockers:
            lines += ["", "Blockers:"] + ["- " + b for b in blockers]
        return "\n".join(lines)
