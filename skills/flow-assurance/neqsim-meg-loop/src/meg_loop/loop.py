"""MEG hydrate-inhibition loop screening with NeqSim.

For a gas or gas-condensate well stream with condensed and formation water:

1. **Injection rate** - the lean MEG rate at which the NeqSim (SRK-CPA)
   hydrate equilibrium temperature of the whole inhibited stream at the
   design pressure equals the coldest operating temperature minus the hydrate
   margin (bisection on the rate).
2. **Rich MEG** - MEG weight fraction in the water phase at arrival, MEG
   lost to gas and hydrocarbon liquid (make-up), and a Hammerschmidt
   cross-check of the depression.
3. **Regeneration** - water boiled off to return rich to lean MEG, reboiler
   temperature (bubble point of lean MEG at the regenerator pressure) and duty
   from a NeqSim enthalpy balance.
4. **Salts** - formation-water salts accumulate in the loop; steady-state
   salt content for a reclaimer slipstream, the slipstream needed to stay
   under a limit, and the time to reach it without reclaiming.
5. **Lean quality** - injection rate and duty for other lean concentrations.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

NAN = float("nan")
M_WATER = 0.018015
M_MEG = 0.06207
HAMMERSCHMIDT_K = 1297.0  # deg C, MEG molar mass in g/mol


class MegInputError(ValueError):
    """Raised for invalid MEG loop inputs."""


@dataclass
class WellStream:
    """Gas or gas-condensate well stream.

    Attributes:
        components: NeqSim component names on any molar basis. Include the
            water carried as vapour (saturated gas) as ``water``.
        pseudo_components: Optional C7+ cuts ``(name, amount, kg/mol, g/cm3)``.
        flow_rate: Stream rate in ``flow_unit``.
        flow_unit: Any NeqSim stream unit, e.g. ``"MSm3/day"``, ``"kg/hr"``.
        formation_water_m3_d: Produced formation water, m3/day.
        formation_water_tds_mg_l: Total dissolved salts of the formation
            water, mg/L.
    """

    components: dict[str, float]
    flow_rate: float
    flow_unit: str = "MSm3/day"
    pseudo_components: list[tuple[str, float, float, float]] = field(
        default_factory=list
    )
    formation_water_m3_d: float = 0.0
    formation_water_tds_mg_l: float = 0.0

    def __post_init__(self) -> None:
        if self.flow_rate <= 0:
            raise MegInputError("flow_rate must be > 0")
        if any(not math.isfinite(v) or v < 0 for v in self.components.values()):
            raise MegInputError("component amounts must be >= 0")
        if self.formation_water_m3_d < 0 or self.formation_water_tds_mg_l < 0:
            raise MegInputError("formation water rate and TDS must be >= 0")
        if "MEG" in self.components:
            raise MegInputError("give the well stream without MEG; MEG is injected")


@dataclass
class HydrateDesign:
    """Hydrate design point.

    Attributes:
        pressure_bara: Pressure at the coldest point (usually shut-in or the
            highest pressure at the lowest temperature), bara.
        min_temperature_c: Lowest temperature the fluid can reach, deg C.
        margin_c: Required margin below the hydrate temperature, deg C.
        arrival_pressure_bara: Arrival (separator) pressure for rich MEG and
            losses.
        arrival_temperature_c: Arrival temperature, deg C.
    """

    pressure_bara: float
    min_temperature_c: float
    margin_c: float = 3.0
    arrival_pressure_bara: float = 50.0
    arrival_temperature_c: float = 20.0

    def __post_init__(self) -> None:
        if self.pressure_bara <= 0 or self.arrival_pressure_bara <= 0:
            raise MegInputError("pressures must be > 0")
        if self.margin_c < 0:
            raise MegInputError("margin_c must be >= 0")

    @property
    def target_temperature_c(self) -> float:
        """Hydrate temperature the inhibited stream must not exceed."""
        return self.min_temperature_c - self.margin_c


@dataclass
class Regeneration:
    """MEG regeneration and reclamation.

    Attributes:
        lean_meg_wt: Lean MEG weight fraction (MEG / (MEG + water)).
        regenerator_pressure_bara: Reboiler pressure, bara.
        rich_feed_temperature_c: Rich MEG temperature entering the regenerator.
        reclaimer_slipstream: Fraction of lean MEG sent through the salt
            reclaimer (0 = no reclaiming).
        salt_limit_wt: Maximum dissolved salt in lean MEG, weight fraction.
            The default (0.05) is a screening value; set it from the salt
            solubility for the actual salts and lean concentration.
        loop_inventory_m3: MEG loop inventory, for the time to reach the limit.
        lean_alternatives: Other lean concentrations to compare.
    """

    lean_meg_wt: float = 0.90
    regenerator_pressure_bara: float = 1.2
    rich_feed_temperature_c: float = 80.0
    reclaimer_slipstream: float = 0.0
    salt_limit_wt: float = 0.05
    loop_inventory_m3: float = 100.0
    lean_alternatives: Sequence[float] = (0.80, 0.85)

    def __post_init__(self) -> None:
        if not 0.5 <= self.lean_meg_wt < 1.0:
            raise MegInputError("lean_meg_wt must be within 0.5-1.0")
        if not 0.0 <= self.reclaimer_slipstream <= 1.0:
            raise MegInputError("reclaimer_slipstream must be 0-1")
        if not 0.0 < self.salt_limit_wt < 0.3:
            raise MegInputError("salt_limit_wt must be within 0-0.3")
        if any(not 0.5 <= w < 1.0 for w in self.lean_alternatives):
            raise MegInputError("lean alternatives must be within 0.5-1.0")


@dataclass(frozen=True)
class Finding:
    """One observation."""

    severity: str
    code: str
    message: str


@dataclass
class MegReport:
    """Result of :func:`assess_meg_loop`."""

    design: HydrateDesign
    regeneration: Regeneration
    results: dict[str, Any]
    alternatives: list[dict[str, Any]]
    findings: list[Finding] = field(default_factory=list)

    @property
    def highest_severity(self) -> str:
        """``high``, ``warning``, ``info`` or ``none``."""
        for level in ("high", "warning", "info"):
            if any(f.severity == level for f in self.findings):
                return level
        return "none"

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe summary."""

        def clean(value: Any) -> Any:
            if isinstance(value, float) and not math.isfinite(value):
                return None
            if isinstance(value, dict):
                return {k: clean(v) for k, v in value.items()}
            if isinstance(value, list | tuple):
                return [clean(v) for v in value]
            return value

        return clean(
            {
                "calculation_basis": "screening",
                "design": asdict(self.design),
                "regeneration": {
                    **asdict(self.regeneration),
                    "lean_alternatives": list(self.regeneration.lean_alternatives),
                },
                "highest_severity": self.highest_severity,
                "results": self.results,
                "alternatives": self.alternatives,
                "findings": [asdict(f) for f in self.findings],
            }
        )

    def to_markdown(self) -> str:
        """Short report."""
        r = self.results

        def fmt(value: Any, digits: int = 1) -> str:
            if isinstance(value, float):
                return f"{value:.{digits}f}" if math.isfinite(value) else "-"
            return str(value)

        rows = [
            ("Uninhibited hydrate temperature (C)", r.get("uninhibited_hydrate_c"), 1),
            ("Target hydrate temperature (C)", self.design.target_temperature_c, 1),
            ("Inhibited hydrate temperature (C)", r.get("inhibited_hydrate_c"), 1),
            ("Free water to inhibit (kg/h)", r.get("free_water_kg_h"), 0),
            ("Lean MEG injection (kg/h)", r.get("lean_meg_kg_h"), 0),
            ("Lean MEG injection (m3/d)", r.get("lean_meg_m3_d"), 1),
            ("Rich MEG in water at arrival (wt %)", r.get("rich_meg_wt_pct"), 1),
            (
                "Hammerschmidt wt % for the same depression",
                r.get("hammerschmidt_wt_pct"),
                1,
            ),
            ("MEG losses to gas and condensate (kg/d)", r.get("meg_loss_kg_d"), 1),
            (
                "Water boiled off in regeneration (kg/h)",
                r.get("water_evaporated_kg_h"),
                0,
            ),
            ("Reboiler temperature (C)", r.get("reboiler_temperature_c"), 1),
            ("Reboiler duty (kW)", r.get("reboiler_duty_kw"), 0),
            ("Salt entering the loop (kg/d)", r.get("salt_in_kg_d"), 0),
            ("Steady-state salt in lean MEG (wt %)", r.get("steady_salt_wt_pct"), 2),
            ("Minimum reclaimer slipstream (%)", r.get("min_slipstream_pct"), 1),
            ("Days to salt limit without reclaiming", r.get("days_to_salt_limit"), 0),
        ]
        lines = ["# MEG loop", "", "| Quantity | Value |", "| --- | ---: |"]
        lines += [
            f"| {label} | {fmt(value, d)} |"
            for label, value, d in rows
            if value is not None
        ]
        if self.alternatives:
            lines += [
                "",
                "## Lean MEG quality",
                "",
                "| Lean MEG (wt %) | Injection (kg/h) | Rich MEG (wt %) | Reboiler duty (kW) |",
                "| ---: | ---: | ---: | ---: |",
            ]
            for a in self.alternatives:
                lines.append(
                    f"| {a['lean_meg_wt'] * 100:.0f} | {fmt(a['lean_meg_kg_h'], 0)} | "
                    f"{fmt(a['rich_meg_wt_pct'])} | {fmt(a['reboiler_duty_kw'], 0)} |"
                )
        lines += ["", "## Findings", ""]
        for f in self.findings or [Finding("info", "none", "No issues flagged.")]:
            lines.append(f"- **{f.severity.upper()}** `{f.code}`: {f.message}")
        return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
def _j():
    try:
        from neqsim import jneqsim
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "neqsim is not installed: python -m pip install neqsim"
        ) from exc
    return jneqsim


def hammerschmidt_wt_fraction(depression_c: float) -> float:
    """MEG weight fraction in water for a hydrate depression (Hammerschmidt).

    ``dT = K w / (M (1 - w))`` with K = 1297 C and M = 62.07 g/mol.
    """
    if depression_c <= 0:
        return 0.0
    m = M_MEG * 1000.0
    return depression_c * m / (HAMMERSCHMIDT_K + depression_c * m)


def _stream_moles(stream: WellStream) -> dict[str, float]:
    """Component molar rates (mol/s) of the well stream from a NeqSim Stream."""
    j = _j()
    system = j.thermo.system.SystemSrkCPAstatoil(288.15, 1.01325)
    for name, amount in stream.components.items():
        if amount > 0:
            system.addComponent(name, float(amount))
    for name, amount, mw, density in stream.pseudo_components:
        system.addTBPfraction(name, float(amount), float(mw), float(density))
    system.setMixingRule(10)
    feed = j.process.equipment.stream.Stream("well", system)
    feed.setFlowRate(float(stream.flow_rate), stream.flow_unit)
    feed.run()
    fluid = feed.getFluid()
    total = float(fluid.getTotalNumberOfMoles())
    rates = {}
    for i in range(fluid.getPhase(0).getNumberOfComponents()):
        comp = fluid.getPhase(0).getComponent(i)
        rates[str(comp.getComponentName())] = float(comp.getz()) * total
    return rates


class _Model:
    """Builds inhibited systems for one well stream (mol/s basis)."""

    def __init__(self, stream: WellStream) -> None:
        self.j = _j()
        self.stream = stream
        self.rates = _stream_moles(stream)
        water_m3_s = stream.formation_water_m3_d / 86400.0
        self.formation_water_kg_s = water_m3_s * 1000.0
        self.formation_water_mol_s = self.formation_water_kg_s / M_WATER
        self.pseudo = {name for name, *_ in stream.pseudo_components}

    def system(
        self,
        lean_kg_s: float,
        lean_wt: float,
        temperature_c: float,
        pressure_bara: float,
    ):
        j = self.j
        system = j.thermo.system.SystemSrkCPAstatoil(
            273.15 + temperature_c, float(pressure_bara)
        )
        water = self.rates.get("water", 0.0) + self.formation_water_mol_s
        water += lean_kg_s * (1.0 - lean_wt) / M_WATER
        meg = lean_kg_s * lean_wt / M_MEG
        for name, rate in self.rates.items():
            if name == "water" or name in self.pseudo or name.endswith("_PC"):
                continue
            system.addComponent(name, rate)
        for name, _amount, mw, density in self.stream.pseudo_components:
            rate = self.rates.get(f"{name}_PC", self.rates.get(name, 0.0))
            system.addTBPfraction(name, rate, float(mw), float(density))
        system.addComponent("water", max(water, 1e-12))
        if meg > 0:
            system.addComponent("MEG", meg)
        system.setMixingRule(10)
        system.setMultiPhaseCheck(True)
        return system

    def hydrate_c(
        self, lean_kg_s: float, lean_wt: float, pressure_bara: float
    ) -> float:
        system = self.system(lean_kg_s, lean_wt, 10.0, pressure_bara)
        system.setHydrateCheck(True)
        self.j.thermodynamicoperations.ThermodynamicOperations(
            system
        ).hydrateFormationTemperature()
        return float(system.getTemperature()) - 273.15

    def arrival(
        self, lean_kg_s: float, lean_wt: float, design: HydrateDesign
    ) -> dict[str, float]:
        system = self.system(
            lean_kg_s,
            lean_wt,
            design.arrival_temperature_c,
            design.arrival_pressure_bara,
        )
        self.j.thermodynamicoperations.ThermodynamicOperations(system).TPflash()
        system.init(1)
        out = {"free_water_kg_s": 0.0, "rich_meg_wt": NAN, "meg_loss_kg_s": 0.0}
        for i in range(system.getNumberOfPhases()):
            phase = system.getPhase(i)
            moles = float(phase.getNumberOfMolesInPhase())
            water = float(phase.getComponent("water").getx()) * moles * M_WATER
            meg = (
                float(phase.getComponent("MEG").getx()) * moles * M_MEG
                if phase.hasComponent("MEG")
                else 0.0
            )
            if (water + meg) > 0 and water / max(
                moles * float(phase.getMolarMass()), 1e-30
            ) > 0.3:
                out["free_water_kg_s"] += water
                out["rich_meg_wt"] = meg / (meg + water) if (meg + water) > 0 else 0.0
            else:
                out["meg_loss_kg_s"] += meg
        return out


def _regeneration(
    rich_meg_kg_s: float, rich_water_kg_s: float, regen: Regeneration, lean_wt: float
):
    """Water to boil off, reboiler temperature and duty (kW)."""
    j = _j()
    lean_water = rich_meg_kg_s * (1.0 - lean_wt) / lean_wt
    evaporated = max(rich_water_kg_s - lean_water, 0.0)

    def solution(meg_kg: float, water_kg: float, temperature_c: float):
        system = j.thermo.system.SystemSrkCPAstatoil(
            273.15 + temperature_c, float(regen.regenerator_pressure_bara)
        )
        system.addComponent("water", max(water_kg / M_WATER, 1e-12))
        if meg_kg > 0:
            system.addComponent("MEG", meg_kg / M_MEG)
        system.setMixingRule(10)
        system.setMultiPhaseCheck(True)
        return system

    lean = solution(1.0 * lean_wt, 1.0 * (1 - lean_wt), 120.0)
    ops = j.thermodynamicoperations.ThermodynamicOperations(lean)
    ops.bubblePointTemperatureFlash()
    reboiler_c = float(lean.getTemperature()) - 273.15

    def enthalpy(system) -> float:
        j.thermodynamicoperations.ThermodynamicOperations(system).TPflash()
        system.init(3)
        return float(system.getEnthalpy("J"))

    h_rich = enthalpy(
        solution(rich_meg_kg_s, rich_water_kg_s, regen.rich_feed_temperature_c)
    )
    h_lean = enthalpy(solution(rich_meg_kg_s, lean_water, reboiler_c))
    h_vap = enthalpy(solution(0.0, evaporated, reboiler_c)) if evaporated > 0 else 0.0
    duty_kw = (h_lean + h_vap - h_rich) / 1000.0
    return evaporated, reboiler_c, duty_kw


def _solve_rate(
    model: _Model, lean_wt: float, design: HydrateDesign, max_kg_s: float
) -> float:
    target = design.target_temperature_c
    if model.hydrate_c(0.0, lean_wt, design.pressure_bara) <= target:
        return 0.0
    if model.hydrate_c(max_kg_s, lean_wt, design.pressure_bara) > target:
        return NAN
    low, high = 0.0, max_kg_s
    for _ in range(30):
        mid = 0.5 * (low + high)
        if model.hydrate_c(mid, lean_wt, design.pressure_bara) > target:
            low = mid
        else:
            high = mid
        if high - low < 1e-4 * max(high, 1e-6):
            break
    return high


def _case(
    model: _Model, lean_wt: float, design: HydrateDesign, regen: Regeneration
) -> dict:
    water_kg_s = model.arrival(0.0, lean_wt, design)["free_water_kg_s"]
    max_kg_s = max(20.0 * water_kg_s, 1.0)
    rate = _solve_rate(model, lean_wt, design, max_kg_s)
    case: dict[str, Any] = {"lean_meg_wt": lean_wt, "lean_meg_kg_h": rate * 3600.0}
    if not math.isfinite(rate):
        case.update(rich_meg_wt_pct=NAN, reboiler_duty_kw=NAN)
        return case
    arrival = model.arrival(rate, lean_wt, design)
    rich_meg = rate * lean_wt
    rich_water = arrival["free_water_kg_s"]
    evaporated, reboiler_c, duty = _regeneration(rich_meg, rich_water, regen, lean_wt)
    case.update(
        rich_meg_wt_pct=arrival["rich_meg_wt"] * 100.0,
        free_water_kg_h=water_kg_s * 3600.0,
        meg_loss_kg_d=arrival["meg_loss_kg_s"] * 86400.0,
        inhibited_hydrate_c=model.hydrate_c(rate, lean_wt, design.pressure_bara),
        water_evaporated_kg_h=evaporated * 3600.0,
        reboiler_temperature_c=reboiler_c,
        reboiler_duty_kw=duty,
    )
    return case


def assess_meg_loop(
    stream: WellStream,
    design: HydrateDesign,
    regeneration: Regeneration | None = None,
) -> MegReport:
    """Size MEG injection and regeneration for one well stream."""
    regen = regeneration or Regeneration()
    model = _Model(stream)
    uninhibited = model.hydrate_c(0.0, regen.lean_meg_wt, design.pressure_bara)
    base = _case(model, regen.lean_meg_wt, design, regen)
    results: dict[str, Any] = {"uninhibited_hydrate_c": uninhibited, **base}
    depression = uninhibited - design.target_temperature_c
    results["required_depression_c"] = depression
    results["hammerschmidt_wt_pct"] = hammerschmidt_wt_fraction(depression) * 100.0
    if math.isfinite(base["lean_meg_kg_h"]):
        density = 1100.0  # kg/m3, lean MEG around 90 wt %
        results["lean_meg_m3_d"] = base["lean_meg_kg_h"] * 24.0 / density
    salt_kg_s = (
        model.formation_water_kg_s / 1000.0 * stream.formation_water_tds_mg_l / 1000.0
    )
    results["salt_in_kg_d"] = salt_kg_s * 86400.0
    lean_kg_s = (
        base["lean_meg_kg_h"] / 3600.0 if math.isfinite(base["lean_meg_kg_h"]) else 0.0
    )
    if salt_kg_s > 0 and lean_kg_s > 0:
        results["min_slipstream_pct"] = (
            salt_kg_s / (regen.salt_limit_wt * lean_kg_s) * 100.0
        )
        if regen.reclaimer_slipstream > 0:
            results["steady_salt_wt_pct"] = (
                salt_kg_s / (regen.reclaimer_slipstream * lean_kg_s) * 100.0
            )
        inventory_kg = regen.loop_inventory_m3 * 1100.0
        results["days_to_salt_limit"] = (
            regen.salt_limit_wt * inventory_kg / salt_kg_s / 86400.0
        )
    alternatives = [
        _case(model, w, design, regen)
        for w in regen.lean_alternatives
        if abs(w - regen.lean_meg_wt) > 1e-6
    ]
    report = MegReport(design, regen, results, alternatives)
    _findings(report)
    return report


def _findings(report: MegReport) -> None:
    r, f, regen = report.results, report.findings, report.regeneration
    if r["uninhibited_hydrate_c"] <= report.design.target_temperature_c:
        f.append(
            Finding(
                "info",
                "no-inhibition-needed",
                "The uninhibited hydrate temperature is below the target; no MEG is needed "
                "at this design point.",
            )
        )
        return
    if not math.isfinite(r["lean_meg_kg_h"]):
        f.append(
            Finding(
                "high",
                "target-not-reached",
                f"No injection rate reaches the target hydrate temperature "
                f"{report.design.target_temperature_c:.1f} C with {regen.lean_meg_wt:.0%} "
                "lean MEG: raise the lean concentration, reduce the water, or combine "
                "with insulation or heating.",
            )
        )
        return
    rich = r.get("rich_meg_wt_pct", NAN)
    ham = r.get("hammerschmidt_wt_pct", NAN)
    if math.isfinite(rich) and math.isfinite(ham) and abs(rich - ham) > 8.0:
        f.append(
            Finding(
                "info",
                "hammerschmidt-deviation",
                f"NeqSim needs {rich:.0f} wt % MEG where Hammerschmidt gives {ham:.0f} wt %; "
                "Hammerschmidt is known to deviate at high concentrations.",
            )
        )
    if math.isfinite(rich) and rich > 70.0:
        f.append(
            Finding(
                "warning",
                "high-rich-meg",
                f"Rich MEG of {rich:.0f} wt % is close to the lean concentration; the loop "
                "regenerates little water per pass and viscosity rises at low temperature.",
            )
        )
    slip = r.get("min_slipstream_pct")
    if slip is not None:
        if regen.reclaimer_slipstream * 100.0 < slip:
            days = r.get("days_to_salt_limit", NAN)
            f.append(
                Finding(
                    (
                        "high"
                        if regen.reclaimer_slipstream > 0 or days < 365
                        else "warning"
                    ),
                    "salt-accumulation",
                    f"Formation-water salts ({r['salt_in_kg_d']:.0f} kg/day) need at least "
                    f"{slip:.1f} % of the lean MEG through the reclaimer to stay under "
                    f"{regen.salt_limit_wt:.0%} salt; the stated slipstream is "
                    f"{regen.reclaimer_slipstream:.1%}. Without reclaiming, the "
                    f"{regen.loop_inventory_m3:g} m3 inventory reaches the limit in "
                    f"{days:.0f} days.",
                )
            )
        f.append(
            Finding(
                "info",
                "divalent-salts",
                "Divalent ions (Ca, Mg, Fe, Ba) precipitate as carbonates and sulfates in "
                "the regeneration and pH-stabilised loop; pre-treat or remove them before "
                "the reboiler. Not quantified here.",
            )
        )
    loss = r.get("meg_loss_kg_d", NAN)
    if math.isfinite(loss) and loss > 0:
        f.append(
            Finding(
                "info",
                "meg-losses",
                f"MEG dissolved in gas and hydrocarbon liquid at arrival: {loss:.1f} kg/day "
                "make-up (excludes mechanical and regeneration losses).",
            )
        )
