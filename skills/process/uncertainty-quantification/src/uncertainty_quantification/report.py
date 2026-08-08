"""Build the ``uncertainty`` block for ``results.json`` and the report.

The emitted shape is what ``step3_report/generate_report.py`` renders and what
``devtools/validate_task_results.py`` / ``neqsim.util.agentic.TaskResultValidator``
validate: ``p10 <= p50 <= p90`` ascending, an ``input_parameters`` table, and a
``tornado`` list whose columns are auto-detected from the first row.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

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
    tornado: List[TornadoEntry] = field(default_factory=list)
    simulation_engine: str = ""
    sensitivity: Optional[Dict[str, Any]] = None
    minimum_samples: int = MINIMUM_SAMPLES_SIMULATION

    @property
    def output_parameter(self) -> str:
        """Label used for the output distribution table."""
        if self.output_unit:
            return "{} ({})".format(self.output_name, self.output_unit)
        return self.output_name

    def tornado_prefix(self) -> str:
        """Column prefix for the tornado table, derived from the output name."""
        token = self.output_name.strip().lower().split("(")[0].strip()
        token = "_".join(part for part in token.replace("-", " ").split() if part)
        return token or "output"

    def blockers(self) -> List[str]:
        """Reasons the uncertainty block should not be presented as converged."""
        issues: List[str] = []
        summary = self.result.summary
        if summary.count < self.minimum_samples:
            issues.append(
                "{} samples is below the {}-sample minimum for a simulation-backed "
                "Monte Carlo".format(summary.count, self.minimum_samples)
            )
        if summary.drift_pct > MAX_MEDIAN_DRIFT_PCT:
            issues.append(
                "median drifts {:.1f}% of the P10-P90 spread between run halves "
                "(limit {:.1f}%) — increase the sample count".format(
                    summary.drift_pct, MAX_MEDIAN_DRIFT_PCT
                )
            )
        if self.result.failures:
            issues.append(
                "{} evaluation(s) failed and were dropped".format(self.result.failures)
            )
        if not self.tornado:
            issues.append("no tornado sensitivity was produced")
        return issues

    def to_results_json(self) -> Dict[str, Any]:
        """The ``uncertainty`` block."""
        summary = self.result.summary
        prefix = self.tornado_prefix()
        block: Dict[str, Any] = {
            "method": "Monte Carlo, {} sampling".format(self.result.sampling_method.upper()),
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
        unit = " {}".format(self.output_unit) if self.output_unit else ""
        lines = [
            "**{}** — {} samples, {} sampling.".format(
                self.output_parameter, summary.count, self.result.sampling_method.upper()
            ),
            "",
            "| Statistic | Value |",
            "| --- | --- |",
            "| P10 (low) | {:.6g}{} |".format(summary.p10, unit),
            "| P50 (median) | {:.6g}{} |".format(summary.p50, unit),
            "| P90 (high) | {:.6g}{} |".format(summary.p90, unit),
            "| Mean | {:.6g}{} |".format(summary.mean, unit),
            "| Std. dev. | {:.6g}{} |".format(summary.std, unit),
            "| P(negative) | {:.1f} % |".format(summary.prob_negative_pct),
            "| Median drift (% of P10-P90 spread) | {:.2f} % |".format(summary.drift_pct),
        ]
        if self.tornado:
            lines += [
                "",
                "| Parameter | Low | High | Swing |",
                "| --- | --- | --- | --- |",
            ]
            for entry in self.tornado:
                lines.append(
                    "| {} | {:.6g} | {:.6g} | {:.6g} |".format(
                        entry.parameter, entry.output_low, entry.output_high, entry.swing
                    )
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
