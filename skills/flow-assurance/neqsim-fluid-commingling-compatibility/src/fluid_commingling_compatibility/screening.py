"""Blend-sweep screening of two commingled fluids.

The fluids are blended at a grid of molar fractions, each blend is evaluated
(normally with NeqSim), and the sweep is scanned for the incompatibilities that
only appear in the mixture:

* asphaltene destabilisation by dilution with a lighter fluid (live-oil
  refractive index along the depressurisation path, plus de Boer),
* free gas that appears at the commingling point,
* a hydrate equilibrium temperature that exceeds both end members,
* sour-gas content of the separator gas above a limit,
* non-linear blending of the saturation pressure.

Severities are ``info``, ``warning`` and ``high``. The output is a screening
result: it ranks blends and points at the NeqSim calculation or laboratory test
that should confirm a concern. It is not a design verdict.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from .evaluator import BlendEvaluator, BlendProperties, EvaluationConditions
from .fluids import FluidSpec, FluidSpecError, blend

DEFAULT_FRACTIONS = tuple(i / 10 for i in range(11))

# Refractive-index stability classes (margin = RI_oil - RI_onset), as in NeqSim
# RefractiveIndexAsphalteneScreening#evaluateStability.
RI_CLASSES = (
    (0.03, "VERY_STABLE"),
    (0.02, "STABLE"),
    (0.01, "MARGINAL"),
    (0.0, "UNSTABLE"),
)
DE_BOER_ORDER = ("NO_PROBLEM", "SLIGHT_PROBLEM", "MODERATE_PROBLEM", "SEVERE_PROBLEM")
RELATIVE_RI_WARNING = 0.01
HYDRATE_NONMONOTONIC_C = 0.5
PSAT_NONLINEAR_FRACTION = 0.10


def classify_ri_margin(margin: float) -> str:
    """Stability class for a refractive-index margin (RI_oil - RI_onset)."""
    if not math.isfinite(margin):
        return "UNKNOWN"
    for threshold, label in RI_CLASSES:
        if margin > threshold:
            return label
    return "HIGHLY_UNSTABLE"


def estimate_onset_ri_from_sara(
    saturates: float, aromatics: float, resins: float, asphaltenes: float
) -> float:
    """Screening estimate of the asphaltene onset refractive index from SARA.

    Same public correlation as NeqSim
    ``RefractiveIndexAsphalteneScreening#estimateOnsetRIFromSARA``. Fractions
    are weight fractions and must sum to about one. A measured onset (titration)
    should replace this whenever one exists.
    """
    values = (saturates, aromatics, resins, asphaltenes)
    if any(not math.isfinite(v) or v < 0 for v in values):
        raise ValueError("SARA fractions must be finite and >= 0")
    if not 0.9 <= sum(values) <= 1.1:
        raise ValueError("SARA fractions must sum to about 1 (weight fractions)")
    sat, aro, res, asp = (v + 1e-10 for v in values)
    sa_ratio = sat / (sat + aro)
    ra_ratio = res / asp
    onset = (
        1.442
        + 0.10 * asp
        + 0.12 * (sa_ratio - 0.45)
        - 0.008 * min(max(ra_ratio - 1.5, 0.0), 6.0)
    )
    return max(1.42, min(1.55, onset))


@dataclass(frozen=True)
class Finding:
    """One screening observation."""

    severity: str
    code: str
    message: str


@dataclass
class ScreeningLimits:
    """Optional acceptance limits supplied by the user.

    Attributes:
        onset_ri: Measured asphaltene onset refractive index (P_RI) of the
            asphaltenic fluid. Enables an absolute stability class.
        min_operating_temperature_c: Lowest expected flowing temperature, deg C,
            for the hydrate margin.
        h2s_limit_ppm: Separator-gas H2S limit, ppm(mol).
        co2_limit_mol_pct: Separator-gas CO2 limit, mol %.
    """

    onset_ri: float | None = None
    min_operating_temperature_c: float | None = None
    h2s_limit_ppm: float | None = None
    co2_limit_mol_pct: float | None = None

    def __post_init__(self) -> None:
        if self.onset_ri is not None and not 1.3 <= self.onset_ri <= 1.7:
            raise ValueError("onset_ri must be within 1.3-1.7")


@dataclass
class CommingleReport:
    """Result of a commingling sweep."""

    fluid_a: str
    fluid_b: str
    conditions: EvaluationConditions
    limits: ScreeningLimits
    blends: list[BlendProperties]
    findings: list[Finding] = field(default_factory=list)
    worst_cases: dict[str, dict[str, float]] = field(default_factory=dict)
    onset_ri_source: str = "none"
    asphaltenic_side: str | None = None

    def carries_asphaltenes(self, props: BlendProperties) -> bool:
        """True when the blend contains the asphaltenic fluid."""
        if self.asphaltenic_side == "a":
            return props.fraction_b < 1.0
        if self.asphaltenic_side == "b":
            return props.fraction_b > 0.0
        return False

    @property
    def highest_severity(self) -> str:
        """``high``, ``warning``, ``info`` or ``none``."""
        for level in ("high", "warning", "info"):
            if any(f.severity == level for f in self.findings):
                return level
        return "none"

    def ri_margin(self, props: BlendProperties) -> float:
        """Absolute RI margin for one blend, NaN without an onset RI."""
        if self.limits.onset_ri is None or not self.carries_asphaltenes(props):
            return float("nan")
        return props.min_live_oil_ri - self.limits.onset_ri

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable summary (NaN becomes None)."""

        def clean(value: Any) -> Any:
            if isinstance(value, float) and not math.isfinite(value):
                return None
            if isinstance(value, dict):
                return {k: clean(v) for k, v in value.items()}
            if isinstance(value, list | tuple):
                return [clean(v) for v in value]
            return value

        rows = []
        for props in self.blends:
            row = asdict(props)
            row["free_gas_at_commingling"] = props.free_gas_at_commingling
            row["ri_margin"] = self.ri_margin(props)
            row["ri_stability"] = classify_ri_margin(row["ri_margin"])
            rows.append(row)
        return clean(
            {
                "fluid_a": self.fluid_a,
                "fluid_b": self.fluid_b,
                "basis": "mole fraction of fluid B in the blend",
                "calculation_basis": "screening",
                "conditions": asdict(self.conditions),
                "limits": asdict(self.limits),
                "onset_ri_source": self.onset_ri_source,
                "highest_severity": self.highest_severity,
                "findings": [asdict(f) for f in self.findings],
                "worst_cases": self.worst_cases,
                "blends": rows,
            }
        )

    def to_markdown(self) -> str:
        """Short markdown report: findings first, then the blend table."""
        lines = [
            f"# Commingling screening: {self.fluid_a} + {self.fluid_b}",
            "",
            (
                f"Commingling at {self.conditions.commingling_pressure_bara:.1f} "
                f"bara, {self.conditions.commingling_temperature_c:.1f} C. "
                f"Blend fraction x_B is the mole fraction of {self.fluid_b}. "
                "Screening-level result; confirm flagged blends with laboratory "
                "tests or detailed NeqSim models."
            ),
            "",
            "## Findings",
            "",
        ]
        if not self.findings:
            lines.append("- No incompatibility flagged in the swept range.")
        for f in self.findings:
            lines.append(f"- **{f.severity.upper()}** `{f.code}`: {f.message}")
        lines += [
            "",
            "## Blend sweep",
            "",
            (
                "| x_B | Psat (bara) | Phases | rho_oil (kg/m3) | min RI (at bara) "
                "| RI class | de Boer | HFT (C) | H2S (ppm) | CO2 (%) |"
            ),
            "| ---: | ---: | --- | ---: | --- | --- | --- | ---: | ---: | ---: |",
        ]

        def fmt(value: float, digits: int = 1) -> str:
            return f"{value:.{digits}f}" if math.isfinite(value) else "-"

        def ri_class(props: BlendProperties) -> str:
            if not self.carries_asphaltenes(props):
                return "n/a"
            return classify_ri_margin(self.ri_margin(props))

        def de_boer(props: BlendProperties) -> str:
            if not self.carries_asphaltenes(props):
                return "n/a"
            return props.de_boer_risk or "-"

        for p in self.blends:
            ri = (
                f"{p.min_live_oil_ri:.4f} ({p.min_live_oil_ri_pressure_bara:.0f})"
                if math.isfinite(p.min_live_oil_ri)
                else "-"
            )
            lines.append(
                f"| {p.fraction_b:.2f} | {fmt(p.saturation_pressure_bara)} | "
                f"{'+'.join(p.phases_at_commingling) or '-'} | "
                f"{fmt(p.liquid_density_kg_m3)} | {ri} | "
                f"{ri_class(p)} | {de_boer(p)} | "
                f"{fmt(p.hydrate_temperature_c)} | {fmt(p.separator_gas_h2s_ppm, 0)} | "
                f"{fmt(p.separator_gas_co2_mol_pct, 2)} |"
            )
        return "\n".join(lines) + "\n"


def _finite(values: Sequence[float]) -> list[float]:
    return [v for v in values if math.isfinite(v)]


def screen_commingling(
    fluid_a: FluidSpec,
    fluid_b: FluidSpec,
    conditions: EvaluationConditions,
    evaluator: BlendEvaluator,
    fractions: Sequence[float] = DEFAULT_FRACTIONS,
    limits: ScreeningLimits | None = None,
    sara: tuple[float, float, float, float] | None = None,
) -> CommingleReport:
    """Sweep blend fractions and flag mixture-only incompatibilities.

    Args:
        fluid_a: First fluid (x_B = 0 end member).
        fluid_b: Second fluid (x_B = 1 end member).
        conditions: Where and how each blend is evaluated.
        evaluator: Property backend, normally :class:`NeqSimBlendEvaluator`.
        fractions: Mole fractions of fluid B to evaluate. Both end members are
            always added.
        limits: Optional acceptance limits.
        sara: Optional SARA weight fractions of the asphaltenic fluid, used to
            estimate the onset RI when ``limits.onset_ri`` is not given.

    Returns:
        A :class:`CommingleReport`.
    """
    limits = limits or ScreeningLimits()
    grid = sorted({round(float(f), 6) for f in fractions} | {0.0, 1.0})
    if any(not 0.0 <= f <= 1.0 for f in grid):
        raise FluidSpecError("all fractions must be within 0-1")
    if len(grid) < 3:
        raise FluidSpecError("give at least one interior fraction")

    onset_source = "measured" if limits.onset_ri is not None else "none"
    if limits.onset_ri is None and sara is not None:
        limits = replace(limits, onset_ri=estimate_onset_ri_from_sara(*sara))
        onset_source = "SARA correlation"

    results = [evaluator.evaluate(blend(fluid_a, fluid_b, f), conditions) for f in grid]
    report = CommingleReport(
        fluid_a=fluid_a.label,
        fluid_b=fluid_b.label,
        conditions=conditions,
        limits=limits,
        blends=results,
        onset_ri_source=onset_source,
        asphaltenic_side=(
            "a" if fluid_a.asphaltenic else "b" if fluid_b.asphaltenic else None
        ),
    )
    _check_asphaltenes(report, fluid_a, fluid_b)
    _check_free_gas(report)
    _check_saturation_linearity(report)
    _check_hydrate(report)
    _check_sour_gas(report)
    for props in results:
        for note in props.notes:
            report.findings.append(
                Finding(
                    "info", "evaluation-note", f"x_B={props.fraction_b:.2f}: {note}"
                )
            )
    return report


def _check_asphaltenes(report: CommingleReport, a: FluidSpec, b: FluidSpec) -> None:
    findings = report.findings
    if a.asphaltenic and b.asphaltenic:
        findings.append(
            Finding(
                "info",
                "asphaltene-both-fluids",
                "Both fluids are marked asphaltenic; the relative check uses fluid A "
                "as reference.",
            )
        )
    if not (a.asphaltenic or b.asphaltenic):
        findings.append(
            Finding(
                "info",
                "asphaltene-not-assessed",
                "Neither fluid is marked asphaltenic; the refractive-index results "
                "are reported but not interpreted.",
            )
        )
        return
    reference_fraction = 0.0 if a.asphaltenic else 1.0
    carrier = [p for p in report.blends if report.carries_asphaltenes(p)]
    reference = next(p for p in report.blends if p.fraction_b == reference_fraction)
    ref_ri = reference.min_live_oil_ri
    candidates = [p for p in carrier if math.isfinite(p.min_live_oil_ri)]
    if not candidates:
        findings.append(
            Finding(
                "warning",
                "asphaltene-no-liquid",
                "No liquid phase was found for the asphaltene-carrying blends; "
                "stability could not be screened.",
            )
        )
        return
    worst = min(candidates, key=lambda p: p.min_live_oil_ri)
    report.worst_cases["asphaltene"] = {
        "fraction_b": worst.fraction_b,
        "min_live_oil_ri": worst.min_live_oil_ri,
        "at_pressure_bara": worst.min_live_oil_ri_pressure_bara,
        "delta_ri_vs_reference": worst.min_live_oil_ri - ref_ri,
    }

    if report.limits.onset_ri is not None:
        unstable = [
            p
            for p in candidates
            if classify_ri_margin(report.ri_margin(p))
            in ("UNSTABLE", "HIGHLY_UNSTABLE")
        ]
        marginal = [
            p
            for p in candidates
            if classify_ri_margin(report.ri_margin(p)) == "MARGINAL"
        ]
        ref_class = classify_ri_margin(report.ri_margin(reference))
        if unstable:
            span = f"{unstable[0].fraction_b:.2f}-{unstable[-1].fraction_b:.2f}"
            findings.append(
                Finding(
                    "high",
                    "asphaltene-onset-crossed",
                    f"Live-oil RI falls below the onset RI "
                    f"({report.limits.onset_ri:.3f}, {report.onset_ri_source}) for "
                    f"x_B {span}; worst at x_B={worst.fraction_b:.2f}, "
                    f"{worst.min_live_oil_ri_pressure_bara:.0f} bara. The "
                    f"asphaltenic fluid alone is {ref_class}. Confirm with an "
                    "onset titration or HPM test on the blend.",
                )
            )
        elif marginal:
            findings.append(
                Finding(
                    "warning",
                    "asphaltene-marginal",
                    f"RI margin is 0.01-0.02 for x_B "
                    f"{marginal[0].fraction_b:.2f}-{marginal[-1].fraction_b:.2f}.",
                )
            )
    delta = worst.min_live_oil_ri - ref_ri if math.isfinite(ref_ri) else float("nan")
    if (
        report.limits.onset_ri is None
        and math.isfinite(delta)
        and delta < -RELATIVE_RI_WARNING
    ):
        findings.append(
            Finding(
                "warning",
                "asphaltene-dilution",
                f"Blending lowers the minimum live-oil refractive index by "
                f"{-delta:.3f} relative to the asphaltenic fluid alone (worst at "
                f"x_B={worst.fraction_b:.2f}): the mixture is a poorer asphaltene "
                "solvent. Without an onset RI this is a relative indicator only; "
                "measure the onset RI of the asphaltenic fluid.",
            )
        )

    order = {name: i for i, name in enumerate(DE_BOER_ORDER)}
    ranked = [p for p in carrier if p.de_boer_risk in order]
    if ranked:
        worst_db = max(ranked, key=lambda p: order[p.de_boer_risk])
        ref_rank = order.get(reference.de_boer_risk or "", -1)
        if order[worst_db.de_boer_risk] > ref_rank and worst_db.de_boer_risk != (
            "NO_PROBLEM"
        ):
            findings.append(
                Finding(
                    "warning",
                    "de-boer-worse-than-host",
                    f"de Boer class worsens to {worst_db.de_boer_risk} at "
                    f"x_B={worst_db.fraction_b:.2f} (reference "
                    f"{reference.de_boer_risk}).",
                )
            )


def _check_free_gas(report: CommingleReport) -> None:
    gassy = [p for p in report.blends if p.free_gas_at_commingling]
    if not gassy:
        return
    ends = [p for p in report.blends if p.fraction_b in (0.0, 1.0)]
    first = min(p.fraction_b for p in gassy)
    if any(p.free_gas_at_commingling for p in ends):
        message = (
            f"Free gas exists at the commingling point from x_B={first:.2f}. "
            "Check slugging, separator gas capacity and manifold design."
        )
        severity = "info"
    else:
        message = (
            f"Neither fluid alone has free gas at the commingling point, but the "
            f"blend does from x_B={first:.2f}: gas breaks out on mixing."
        )
        severity = "warning"
    report.findings.append(Finding(severity, "free-gas-at-commingling", message))
    report.worst_cases["free_gas"] = {"first_fraction_b": first}


def _check_saturation_linearity(report: CommingleReport) -> None:
    by_fraction = {p.fraction_b: p for p in report.blends}
    end_a, end_b = by_fraction[0.0], by_fraction[1.0]
    if not all(
        math.isfinite(p.liquid_density_kg_m3) and not p.free_gas_at_commingling
        for p in (end_a, end_b)
    ):
        # A gas end member's saturation point is a dew point; a straight line
        # between a dew point and a bubble point means nothing.
        return
    pa, pb = end_a.saturation_pressure_bara, end_b.saturation_pressure_bara
    if not (math.isfinite(pa) and math.isfinite(pb)):
        return
    scale = max(abs(pa), abs(pb), 1.0)
    worst_dev, worst_f = 0.0, None
    for p in report.blends:
        if not math.isfinite(p.saturation_pressure_bara):
            continue
        linear = pa + (pb - pa) * p.fraction_b
        dev = p.saturation_pressure_bara - linear
        if abs(dev) > abs(worst_dev):
            worst_dev, worst_f = dev, p.fraction_b
    if worst_f is None:
        return
    report.worst_cases["saturation_nonlinearity"] = {
        "fraction_b": worst_f,
        "deviation_bara": worst_dev,
    }
    if abs(worst_dev) / scale > PSAT_NONLINEAR_FRACTION:
        report.findings.append(
            Finding(
                "info",
                "saturation-nonlinear",
                f"Blend saturation pressure departs {worst_dev:+.1f} bara from linear "
                f"interpolation at x_B={worst_f:.2f}; do not interpolate end-member "
                "PVT for allocation or hydraulics.",
            )
        )


def _check_hydrate(report: CommingleReport) -> None:
    values = [
        (p.fraction_b, p.hydrate_temperature_c)
        for p in report.blends
        if math.isfinite(p.hydrate_temperature_c)
    ]
    if not values:
        return
    worst_f, worst_t = max(values, key=lambda v: v[1])
    report.worst_cases["hydrate"] = {
        "fraction_b": worst_f,
        "hydrate_temperature_c": worst_t,
    }
    ends = [t for f, t in values if f in (0.0, 1.0)]
    if (
        ends
        and worst_f not in (0.0, 1.0)
        and worst_t > max(ends) + HYDRATE_NONMONOTONIC_C
    ):
        report.findings.append(
            Finding(
                "warning",
                "hydrate-blend-maximum",
                f"Hydrate temperature peaks at {worst_t:.1f} C for x_B={worst_f:.2f}, "
                f"above both end members (max {max(ends):.1f} C): size inhibition "
                "for the blend, not the individual fluids.",
            )
        )
    t_min = report.limits.min_operating_temperature_c
    if t_min is not None:
        short = [(f, t) for f, t in values if t >= t_min]
        if short:
            report.findings.append(
                Finding(
                    "high",
                    "hydrate-margin",
                    f"Hydrate temperature reaches {worst_t:.1f} C, at or above the "
                    f"minimum operating temperature {t_min:.1f} C, for "
                    f"{len(short)} of {len(values)} blends.",
                )
            )
    if any(p.free_water_assumed for p in report.blends):
        report.findings.append(
            Finding(
                "info",
                "hydrate-free-water-assumed",
                "Free water was assumed for dry blends in the hydrate check.",
            )
        )


def _check_sour_gas(report: CommingleReport) -> None:
    checks = (
        ("separator_gas_h2s_ppm", report.limits.h2s_limit_ppm, "H2S", "ppm"),
        ("separator_gas_co2_mol_pct", report.limits.co2_limit_mol_pct, "CO2", "mol %"),
    )
    for attr, limit, label, unit in checks:
        values = [
            (p.fraction_b, getattr(p, attr))
            for p in report.blends
            if math.isfinite(getattr(p, attr))
        ]
        if not values:
            continue
        worst_f, worst_v = max(values, key=lambda v: v[1])
        report.worst_cases[label.lower()] = {
            "fraction_b": worst_f,
            "value": worst_v,
        }
        if limit is None:
            continue
        over = [f for f, v in values if v > limit]
        if over:
            report.findings.append(
                Finding(
                    "high",
                    f"{label.lower()}-limit",
                    f"Separator-gas {label} exceeds {limit:g} {unit} for x_B "
                    f"{min(over):.2f}-{max(over):.2f} (max {worst_v:.3g} {unit}).",
                )
            )
