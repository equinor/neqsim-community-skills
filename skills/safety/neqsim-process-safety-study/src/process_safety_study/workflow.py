"""Step registry of a process safety study: which skill or agent to call, the evidence needed, the gate and the traps."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Step:
    """One step of the study workflow."""

    id: str
    title: str
    skills: tuple[str, ...]
    agents: tuple[str, ...]
    evidence: tuple[str, ...]
    gate: str
    traps: tuple[str, ...]

    def as_dict(self) -> dict:
        """Return the step as a plain dictionary (tuples become lists)."""
        return {
            key: list(val) if isinstance(val, tuple) else val
            for key, val in asdict(self).items()
        }


STEPS: tuple[Step, ...] = (
    Step(
        "S00",
        "Scope and basis freeze",
        (
            "neqsim-task-workflow",
            "neqsim-jurisdiction-regulatory-basis",
            "neqsim-task-grill",
        ),
        ("process-safety-study-agent",),
        (
            "study scope (tie-in, modification, new facility)",
            "host installation and project phase",
            "jurisdiction",
        ),
        "Scope, host, phase and jurisdiction written down; open questions listed as data gaps.",
        ("Starting numbers before the acceptance criteria are named.",),
    ),
    Step(
        "S01",
        "Source drawings and data verification",
        (
            "neqsim-tie-in-pid-sketch",
            "neqsim-document-intelligence-extraction",
            "neqsim-technical-document-reading",
            "neqsim-pid-quality-review",
            "neqsim-pfd-layout-review",
        ),
        ("technical-document-intelligence-agent", "subsea-layout-screening-agent"),
        (
            "controlled P&IDs, line list, valve and instrument list",
            "the pressure/rate/temperature profile and its revision",
        ),
        "Every number carried into the study traces to a named document revision; `profile_gate` and `tag_anchor_gate` give MATCH.",
        (
            "Using a superseded or proxy pressure profile: compare it with the design-case source before use.",
            "Safety drawings that drift from the P&IDs: anchor every item to a tag, draw new items as proposals.",
        ),
    ),
    Step(
        "S02",
        "Governing requirements and document register",
        (
            "neqsim-standard-requirement-extraction",
            "neqsim-standards-lookup",
            "neqsim-document-intelligence-extraction",
        ),
        ("technical-document-intelligence-agent",),
        ("document number, edition, clause and read status per topic",),
        "`evidence_gate` run on the register; `claim_gate` run on every statement of compliance.",
        (
            "Claiming compliance from a title or an index entry: only text that was read counts.",
        ),
    ),
    Step(
        "S03",
        "Hazard identification",
        ("neqsim-hazid-fmea-eta-fta", "neqsim-process-safety"),
        ("process-safety-agent",),
        (
            "guide-word checklist per phase",
            "major accident hazard list",
            "SIMOPS interfaces",
        ),
        "Each scenario has a node, a hazard, a causing event and a link to a calculation step; gaps are listed.",
        ("A pre-populated worksheet is a prompt for the team, not a finding.",),
    ),
    Step(
        "S04",
        "Consequence and source terms",
        (
            "neqsim-consequence-analysis",
            "neqsim-release-source-terms",
            "neqsim-jet-fire-radiation-screening",
            "neqsim-gas-dispersion-distance-screening",
            "neqsim-h2s-safety-impact",
        ),
        ("process-safety-agent", "flare-helideck-dispersion-agent"),
        (
            "inventory, pressure, temperature and composition per release state",
            "hole sizes and isolation times",
        ),
        "Release rates agree with a hand calculation (`hand_calc_gate`); phase and validity range of the model stated.",
        (
            "Trusting a NeqSim release rate without a hand calculation or an independent model.",
            "A property that is not valid for the state (dense phase, two liquids) silently replaced by a factor.",
        ),
    ),
    Step(
        "S05",
        "Relief, blowdown and flare",
        (
            "neqsim-relief-flare-network",
            "neqsim-depressurization-mdmt",
            "neqsim-trapped-liquid-fire-rupture",
            "neqsim-relief-load-screening",
            "neqsim-depressurization-screening",
            "neqsim-psv-orifice-screening",
            "neqsim-flare-radiation-screening",
        ),
        ("process-safety-agent", "firewater-coverage-agent"),
        (
            "flare tip, header and knock-out drum data of the host",
            "relief and blowdown valve data",
            "governing relief cases",
            "existing or previous wells and inputs to the receiving separator or header (riser or inlet pressure, shut-in pressure, rates, choke dP) and what the relief basis was sized for",
            "current (not design) inflow for the blocked-outlet check",
            "scenario register: failed-open / IVO with and without choke collapse, choke collapse alone, blocked outlet per separator or header, gas blow-by, PSV failure, fire, hydrate plug, cold JT, each with study status (calculated, simple estimate, qualitative), valve states, limiting mechanism and governing yes or no",
            "installed valve Cv and capacity inputs with source and quality grade: choke Cv intact and collapsed and its opening, riser or production EV Cv and stroke time, PV Cv and maximum opening, PSV orifice and set pressure, line volumes, flare backpressure",
        ),
        "Loads checked against the flare and KO-drum capacity with a dynamic check; verified data separated from assumed; the new source compared with existing wells and inputs (ratio new to historical, effect on the failed-open or choke-collapse load); blocked outlet checked against current inflow with an explicit verdict; the relief chapter opens with a scenario register and an installed-Cv input table with sources, and a Cv sensitivity for failed-open and blocked outlet states what the relief rate depends on and what it does not.",
        (
            "Using an assumed knock-out drum volume: read the datasheet, then run the dynamic check.",
            "A lumped vapour-only blowdown model for a liquid-laden line understates the time and the flare peak.",
            "Concluding on a new source without comparing it with the existing wells and inputs to the receiving system, or sizing on design inflow: lower production today reduces blocked outlet but not failed-open or choke collapse, which usually governs when the new source pressure exceeds earlier wells.",
            "Presenting a relief rate without the scenario and valve states it belongs to, or without the installed choke Cv and dP behind it: the rate depends on the installed choke Cv, the actual dP and the stored inventory, so show the Cv inputs with sources (ASSUMED when unsourced) and a Cv sensitivity for failed-open and blocked outlet.",
        ),
    ),
    Step(
        "S06",
        "Transients and OLGA verification",
        (
            "neqsim-olga-multiphase-simulator",
            "neqsim-multiphase-flow-slug-screening",
            "neqsim-water-hammer",
        ),
        ("olga-simulation-agent", "flow-assurance-study-agent"),
        (
            "route profile, PVT tables, insulation, host boundary",
            "OLGA engine and licence status",
        ),
        "Screening values compared with the transient run with `conservatism_gate`; non-conservative rows carried to the report.",
        (
            "Screening models were non-conservative for severe slugging, restart peaks, pack-up time and pigging.",
            "Wells as a constant-rate source make pack-up pressures upper bounds.",
        ),
    ),
    Step(
        "S07",
        "SIL, LOPA and safety requirement specification",
        (
            "neqsim-process-safety",
            "neqsim-safety-function-coverage-screening",
            "neqsim-hazid-fmea-eta-fta",
        ),
        ("process-safety-agent",),
        (
            "demand rate and tolerable frequency",
            "failure data with source",
            "proof-test interval and coverage",
            "response-time budget",
        ),
        "Hazard-rate criterion and the SIL band both met with the stated test regime; data without a certificate stays a gap.",
        (
            "A SIL band without the hazard-rate criterion; crediting a layer that only works if the SIF closes fast enough.",
        ),
    ),
    Step(
        "S08",
        "Explosion and dispersion CFD",
        ("neqsim-cfd-coupling", "neqsim-gas-dispersion-distance-screening"),
        ("cfd-coupling-agent", "flare-helideck-dispersion-agent"),
        (
            "module geometry",
            "source terms",
            "scenario matrix",
            "verification and mesh evidence",
        ),
        "Verification and mesh study reported; a handful of scenarios is not an exceedance curve.",
        (
            "Presenting a screening CFD peak as a design load; no validation means the class is the result.",
        ),
    ),
    Step(
        "S09",
        "Quantitative risk assessment",
        ("neqsim-consequence-analysis", "neqsim-hazid-fmea-eta-fta"),
        ("process-safety-agent",),
        (
            "agreed QRA basis: criteria, models, leak frequencies, population, host baseline",
        ),
        "Basis frozen before numbers; result stated as increment or total; placeholders visible.",
        (
            "Running the QRA before the basis is agreed; reporting an increment on an unknown baseline as compliance.",
        ),
    ),
    Step(
        "S10",
        "HAZOP preparation",
        ("neqsim-hazop-node-pack", "neqsim-hazid-fmea-eta-fta"),
        ("process-safety-agent",),
        ("P&IDs with tags", "node definitions", "valve, instrument and line lists"),
        "Node pack with marked-up P&IDs and a `missing_evidence` list; placement rules run on the drawings.",
        (
            "Treating the node pack as the HAZOP; the facilitated session cannot be replaced.",
        ),
    ),
    Step(
        "S11",
        "Barriers and safety-critical elements",
        ("neqsim-safety-function-coverage-screening", "neqsim-hazop-node-pack"),
        ("process-safety-agent",),
        ("barrier elements and their performance standards", "test regime"),
        "Each barrier has an owner, a performance standard and a test; untestable barriers are flagged.",
        (
            "A barrier that cannot be tested on the drawing (no test line, no isolation).",
        ),
    ),
    Step(
        "S12",
        "ESD, PSD, fire and gas cause and effect",
        (
            "neqsim-hazop-node-pack",
            "neqsim-safety-function-coverage-screening",
            "neqsim-firewater-deluge-design",
        ),
        ("process-safety-agent", "firewater-coverage-agent"),
        (
            "cause and effect matrix with P&ID tags",
            "SIF list with sensor, logic and final element",
        ),
        "Every cause and effect cites tags that exist on the drawings; response chains close in the time budget.",
        (
            "Interlocks that block a legitimate start-up; single-transmitter initiators.",
        ),
    ),
    Step(
        "S13",
        "Reconcile carried values",
        ("neqsim-task-workflow",),
        ("process-safety-study-agent",),
        ("every quantity used by more than one workstream",),
        "`reconcile_values` reports no conflict above the tolerance, or each conflict is explained.",
        (
            "A follow-up that changes a number after later workstreams already quoted it.",
        ),
    ),
    Step(
        "S14",
        "Reporting and hand-off",
        (
            "neqsim-final-report-writing-style",
            "neqsim-standard-engineering-english",
            "neqsim-professional-reporting",
        ),
        ("process-safety-study-agent",),
        ("results with assumptions and data gaps", "register of unread documents"),
        "Conclusions carry their evidence status; data gaps have an owner; human review list is attached.",
        (
            "A pass without evidence; an unreviewed AI pre-review presented as a facilitated session.",
        ),
    ),
)


def workflow() -> list[dict]:
    """Return all steps as dictionaries in study order."""
    return [item.as_dict() for item in STEPS]


def step(step_id: str) -> dict:
    """Return one step by id.

    Raises:
        KeyError: if the id is unknown.
    """
    for item in STEPS:
        if item.id == step_id:
            return item.as_dict()
    raise KeyError(f"unknown step id {step_id!r}")


def skills_for(step_ids: list[str] | None = None) -> list[str]:
    """Return the sorted skill ids used by the given steps (all steps when None)."""
    chosen = [item for item in STEPS if step_ids is None or item.id in step_ids]
    return sorted({skill for item in chosen for skill in item.skills})


def agents_for(step_ids: list[str] | None = None) -> list[str]:
    """Return the sorted agent ids used by the given steps (all steps when None)."""
    chosen = [item for item in STEPS if step_ids is None or item.id in step_ids]
    return sorted({agent for item in chosen for agent in item.agents})
