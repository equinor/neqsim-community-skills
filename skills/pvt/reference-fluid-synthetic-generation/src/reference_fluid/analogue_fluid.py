"""Build a defensible fluid basis when there is no PVT report.

A reservoir model needs a fluid long before anyone flies a sample to a
laboratory. The honest answer is not "assume a typical oil"; it is a basis in
which every number states where it came from, what it would take to retire it,
and how much the answer moves if it is wrong.

Three sources, in descending authority:

  measured    a number read from a well report, a test or a deck
  analogue    a nearby field in the same play at a comparable depth
  correlation a depth or temperature trend with no local anchor at all

Nothing here is a NeqSim calculation. It produces the *targets* that a rigorous
characterization is then tuned to -- saturation pressure, formation volume
factor and viscosity come from the equation of state, not from this module.

Plant-agnostic and offline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence

PROVENANCE_RANKS = {
    "correlation": 0,
    "analogue": 1,
    "derived": 2,
    "interpreted": 3,
    "measured": 4,
}

# --------------------------------------------------------------------------
# Reservoir conditions from depth
# --------------------------------------------------------------------------
#: Seabed temperature and geothermal gradient by sea area. Public regional
#: values; a logged bottom-hole temperature always outranks them.
THERMAL_DEFAULTS: dict[str, dict[str, float]] = {
    "north_sea": {"seabed_C": 5.0, "gradient_C_per_km": 36.0},
    "norwegian_sea": {"seabed_C": 3.0, "gradient_C_per_km": 38.0},
    "barents_sea": {"seabed_C": 2.0, "gradient_C_per_km": 33.0},
    "gulf_of_mexico": {"seabed_C": 4.0, "gradient_C_per_km": 25.0},
    "generic_offshore": {"seabed_C": 4.0, "gradient_C_per_km": 35.0},
}

#: Pore-pressure gradients. "hydrostatic" is the default ONLY because it is the
#: least-assuming choice, not because it is likely: deep Jurassic sections are
#: routinely overpressured, and getting this wrong moves the whole depletion path.
PRESSURE_GRADIENTS: dict[str, float] = {
    "hydrostatic": 0.1055,
    "mild_overpressure": 0.125,
    "strong_overpressure": 0.150,
    "lithostatic_approach": 0.180,
}

OVERPRESSURE_WARNING = (
    "A hydrostatic pore pressure is an assumption, not a default truth. On a "
    "deep Jurassic or HPHT section the real gradient is often 0.13-0.16 bar/m, "
    "and the difference is hundreds of bar. Until an RFT/MDT gradient exists, "
    "carry the pressure as a RANGE and say which end the design depends on."
)


def estimate_reservoir_conditions(
    *,
    datum_tvdss_m: float,
    water_depth_m: float = 0.0,
    sea_area: str = "generic_offshore",
    pressure_regime: str = "hydrostatic",
    measured_temperature_C: Optional[float] = None,
    measured_pressure_bara: Optional[float] = None,
) -> dict[str, Any]:
    """Temperature and pressure at a datum, with provenance on each.

    A measured value is passed through and labelled measured; only what is
    missing is estimated.
    """
    if datum_tvdss_m <= 0:
        raise ValueError("datum_tvdss_m must be a positive depth below mean sea level.")
    if sea_area not in THERMAL_DEFAULTS:
        raise ValueError(f"Unknown sea_area {sea_area!r}. Known: "
                         + ", ".join(sorted(THERMAL_DEFAULTS)))
    if pressure_regime not in PRESSURE_GRADIENTS:
        raise ValueError(f"Unknown pressure_regime {pressure_regime!r}. Known: "
                         + ", ".join(sorted(PRESSURE_GRADIENTS)))

    thermal = THERMAL_DEFAULTS[sea_area]
    below_mudline = max(datum_tvdss_m - water_depth_m, 0.0)
    estimated_t = thermal["seabed_C"] + thermal["gradient_C_per_km"] * below_mudline / 1000.0
    gradient = PRESSURE_GRADIENTS[pressure_regime]
    estimated_p = gradient * datum_tvdss_m
    hydrostatic_p = PRESSURE_GRADIENTS["hydrostatic"] * datum_tvdss_m

    record: dict[str, Any] = {
        "datum_tvdss_m": datum_tvdss_m,
        "water_depth_m": water_depth_m,
        "depth_below_mudline_m": below_mudline,
        "temperature_C": {
            "value": measured_temperature_C if measured_temperature_C is not None
            else round(estimated_t, 1),
            "provenance": "measured" if measured_temperature_C is not None else "correlation",
            "reference": f"{thermal['seabed_C']} degC seabed + "
                         f"{thermal['gradient_C_per_km']} degC/km ({sea_area})",
            "estimate_if_measured_supplied": round(estimated_t, 1),
        },
        "pressure_bara": {
            "value": measured_pressure_bara if measured_pressure_bara is not None
            else round(estimated_p, 1),
            "provenance": "measured" if measured_pressure_bara is not None else "correlation",
            "reference": f"{gradient} bar/m ({pressure_regime})",
            "estimate_if_measured_supplied": round(estimated_p, 1),
            "hydrostatic_bara": round(hydrostatic_p, 1),
        },
        "warnings": [OVERPRESSURE_WARNING],
    }
    if measured_pressure_bara is not None:
        overpressure = measured_pressure_bara - hydrostatic_p
        record["pressure_bara"]["overpressure_bar"] = round(overpressure, 1)
        record["pressure_bara"]["measured_gradient_bar_per_m"] = round(
            measured_pressure_bara / datum_tvdss_m, 4)
        if overpressure > 50.0:
            record["pressure_bara"]["note"] = (
                f"Overpressured by {overpressure:.0f} bar above hydrostatic. Any "
                "earlier hydrostatic assumption is refuted; re-check anything "
                "derived from it."
            )
    if measured_temperature_C is not None:
        record["temperature_C"]["deviation_from_correlation_C"] = round(
            measured_temperature_C - estimated_t, 1)
    return record


# --------------------------------------------------------------------------
# Fluid type
# --------------------------------------------------------------------------
#: Conventional boundaries on solution GOR. The bands overlap in reality, so
#: a fluid near a boundary is reported as such rather than forced into one side.
FLUID_TYPE_BANDS: tuple[dict[str, Any], ...] = (
    {"type": "heavy_oil", "gor_max": 20.0,
     "note": "Little dissolved gas; viscosity dominates everything."},
    {"type": "black_oil", "gor_max": 200.0,
     "note": "Standard PVTO/PVDG black-oil treatment is adequate."},
    {"type": "volatile_oil", "gor_max": 500.0,
     "note": "Bo above ~2 rm3/Sm3 and a strong composition change on depletion. "
             "Black oil is usable but a compositional check is worth doing."},
    {"type": "near_critical", "gor_max": 900.0,
     "note": "Black-oil tables are unreliable here; use a compositional model."},
    {"type": "gas_condensate", "gor_max": 20000.0,
     "note": "Retrograde liquid dropout. Needs vaporised oil (PVTG), not PVTO."},
    {"type": "dry_gas", "gor_max": float("inf"),
     "note": "No significant liquid; PVDG alone."},
)

BOUNDARY_FRACTION = 0.15


def classify_fluid_type(gor_sm3_sm3: float, api_degrees: Optional[float] = None) -> dict[str, Any]:
    """Name the fluid type from solution GOR, and say when it sits on a boundary."""
    if gor_sm3_sm3 < 0:
        raise ValueError("gor_sm3_sm3 cannot be negative.")
    previous_max = 0.0
    for band in FLUID_TYPE_BANDS:
        if gor_sm3_sm3 <= band["gor_max"]:
            span = band["gor_max"] - previous_max
            near_upper = (band["gor_max"] - gor_sm3_sm3) < BOUNDARY_FRACTION * span \
                if span not in (0, float("inf")) else False
            near_lower = (gor_sm3_sm3 - previous_max) < BOUNDARY_FRACTION * span \
                if span not in (0, float("inf")) else False
            record = {
                "fluid_type": band["type"],
                "gor_sm3_sm3": gor_sm3_sm3,
                "api_degrees": api_degrees,
                "modelling_note": band["note"],
                "on_boundary": bool(near_upper or near_lower),
            }
            if near_upper or near_lower:
                record["boundary_note"] = (
                    f"GOR {gor_sm3_sm3:.0f} sits within {int(BOUNDARY_FRACTION * 100)}% "
                    f"of a band edge, so the classification is not firm. Carry both "
                    "neighbouring types until a sample settles it."
                )
            if api_degrees is not None and band["type"] in ("black_oil", "volatile_oil") \
                    and api_degrees < 20.0:
                record["inconsistency"] = (
                    f"A GOR of {gor_sm3_sm3:.0f} with {api_degrees:.0f} degAPI is "
                    "internally inconsistent: light gas-rich oils are not that "
                    "dense. Check which of the two numbers is wrong."
                )
            return record
        previous_max = band["gor_max"]
    raise AssertionError("FLUID_TYPE_BANDS must end with an unbounded band.")


# --------------------------------------------------------------------------
# Analogues
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class FluidAnalogue:
    """One public analogue: a field whose fluid is a defensible stand-in."""

    name: str
    play: str
    depth_tvdss_m: float
    api_degrees: float
    gor_sm3_sm3: float
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "play": self.play,
                "depth_tvdss_m": self.depth_tvdss_m, "api_degrees": self.api_degrees,
                "gor_sm3_sm3": self.gor_sm3_sm3, "note": self.note}


def api_to_density(api_degrees: float) -> float:
    """Stock-tank oil density in kg/m3 from degAPI."""
    if api_degrees <= -131.5:
        raise ValueError("degAPI below -131.5 has no physical density.")
    return 141.5 / (api_degrees + 131.5) * 999.0


def density_to_api(density_kg_m3: float) -> float:
    """degAPI from stock-tank oil density in kg/m3."""
    if density_kg_m3 <= 0:
        raise ValueError("density must be positive.")
    return 141.5 / (density_kg_m3 / 999.0) - 131.5


def interpolate_by_depth(
    analogues: Sequence[FluidAnalogue],
    target_depth_tvdss_m: float,
    attribute: str,
) -> dict[str, Any]:
    """Read an attribute off the analogue depth trend.

    Deeper reservoirs in one play are generally lighter and gassier, so depth is
    the natural ordering variable. Outside the analogue depth span the result is
    CLAMPED rather than extrapolated, and says so: a linear GOR trend
    extrapolated past the deepest analogue produces nonsense quickly.
    """
    if not analogues:
        raise ValueError("At least one analogue is required.")
    ordered = sorted(analogues, key=lambda a: a.depth_tvdss_m)
    depths = [a.depth_tvdss_m for a in ordered]
    values = [getattr(a, attribute) for a in ordered]

    if target_depth_tvdss_m <= depths[0]:
        return {"value": values[0], "extrapolated": True, "clamped_to": ordered[0].name,
                "bracketing": [ordered[0].name],
                "note": "Shallower than every analogue; value clamped, not extrapolated."}
    if target_depth_tvdss_m >= depths[-1]:
        return {"value": values[-1], "extrapolated": True, "clamped_to": ordered[-1].name,
                "bracketing": [ordered[-1].name],
                "note": "Deeper than every analogue; value clamped, not extrapolated."}

    for index in range(len(ordered) - 1):
        low, high = ordered[index], ordered[index + 1]
        if low.depth_tvdss_m <= target_depth_tvdss_m <= high.depth_tvdss_m:
            span = high.depth_tvdss_m - low.depth_tvdss_m
            weight = 0.0 if span == 0 else (target_depth_tvdss_m - low.depth_tvdss_m) / span
            value = values[index] + weight * (values[index + 1] - values[index])
            return {"value": value, "extrapolated": False,
                    "bracketing": [low.name, high.name], "weight": round(weight, 3),
                    "note": f"Interpolated between {low.name} and {high.name}."}
    raise AssertionError("Depth fell outside every bracket despite the range checks.")


# --------------------------------------------------------------------------
# The basis
# --------------------------------------------------------------------------
@dataclass
class Assumption:
    """One assumption, and what would retire it."""

    identifier: str
    assumption: str
    basis: str
    impact: str
    retire_with: str
    retired: bool = False
    retired_by: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.identifier, "assumption": self.assumption,
                "basis": self.basis, "impact": self.impact,
                "retire_with": self.retire_with, "retired": self.retired,
                "retired_by": self.retired_by}


def build_analogue_fluid_basis(
    *,
    datum_tvdss_m: float,
    analogues: Sequence[FluidAnalogue],
    water_depth_m: float = 0.0,
    sea_area: str = "generic_offshore",
    pressure_regime: str = "hydrostatic",
    measured_temperature_C: Optional[float] = None,
    measured_pressure_bara: Optional[float] = None,
    measured_gor_sm3_sm3: Optional[float] = None,
    measured_api_degrees: Optional[float] = None,
    gor_uncertainty_fraction: float = 0.35,
    api_uncertainty_degrees: float = 3.0,
) -> dict[str, Any]:
    """Assemble a fluid basis with low/base/high cases and an assumption register.

    The output is the *input* to a characterization, not a fluid. Saturation
    pressure, Bo and viscosity are deliberately absent: they belong to the
    equation of state, and quoting a correlation value for them next to
    EOS-derived numbers invites someone to mix the two.
    """
    conditions = estimate_reservoir_conditions(
        datum_tvdss_m=datum_tvdss_m, water_depth_m=water_depth_m, sea_area=sea_area,
        pressure_regime=pressure_regime,
        measured_temperature_C=measured_temperature_C,
        measured_pressure_bara=measured_pressure_bara,
    )

    gor_trend = interpolate_by_depth(analogues, datum_tvdss_m, "gor_sm3_sm3")
    api_trend = interpolate_by_depth(analogues, datum_tvdss_m, "api_degrees")

    gor_base = measured_gor_sm3_sm3 if measured_gor_sm3_sm3 is not None else gor_trend["value"]
    api_base = measured_api_degrees if measured_api_degrees is not None else api_trend["value"]
    gor_provenance = "measured" if measured_gor_sm3_sm3 is not None else "analogue"
    api_provenance = "measured" if measured_api_degrees is not None else "analogue"

    # A measured value still carries uncertainty, but far less than a trend read.
    gor_spread = gor_uncertainty_fraction * (0.3 if gor_provenance == "measured" else 1.0)
    api_spread = api_uncertainty_degrees * (0.3 if api_provenance == "measured" else 1.0)

    cases = {}
    for label, gor, api in (
        ("low", gor_base * (1.0 - gor_spread), api_base - api_spread),
        ("base", gor_base, api_base),
        ("high", gor_base * (1.0 + gor_spread), api_base + api_spread),
    ):
        cases[label] = {
            "gor_sm3_sm3": round(gor, 1),
            "api_degrees": round(api, 1),
            "sto_density_kg_m3": round(api_to_density(api), 1),
            "fluid_type": classify_fluid_type(gor, api)["fluid_type"],
        }

    classification = classify_fluid_type(gor_base, api_base)

    register = [
        Assumption("F1", f"Solution GOR {gor_base:.0f} Sm3/Sm3",
                   ("measured value supplied" if gor_provenance == "measured"
                    else f"analogue depth trend, {gor_trend['note']}"),
                   "Sets Rs and Bo, so it sets the reservoir volume factor and the "
                   "gas handling capacity the facility must be sized for.",
                   "a laboratory PVT study on a downhole sample",
                   retired=gor_provenance == "measured",
                   retired_by="supplied measurement" if gor_provenance == "measured" else None),
        Assumption("F2", f"Stock-tank oil {api_base:.0f} degAPI",
                   ("measured value supplied" if api_provenance == "measured"
                    else f"analogue depth trend, {api_trend['note']}"),
                   "Sets the oil density and hence the in-place mass and the "
                   "revenue per standard cubic metre.",
                   "a stock-tank oil density measurement",
                   retired=api_provenance == "measured",
                   retired_by="supplied measurement" if api_provenance == "measured" else None),
        Assumption("F3", f"Reservoir temperature {conditions['temperature_C']['value']} degC",
                   conditions["temperature_C"]["reference"],
                   "Moves viscosity and the saturation pressure.",
                   "a logged bottom-hole temperature",
                   retired=conditions["temperature_C"]["provenance"] == "measured",
                   retired_by="supplied measurement"
                   if conditions["temperature_C"]["provenance"] == "measured" else None),
        Assumption("F4", f"Reservoir pressure {conditions['pressure_bara']['value']} bara",
                   conditions["pressure_bara"]["reference"],
                   "Sets the undersaturation and therefore whether a gas cap is "
                   "possible and how much depletion drive there is.",
                   "an RFT/MDT pressure gradient",
                   retired=conditions["pressure_bara"]["provenance"] == "measured",
                   retired_by="supplied measurement"
                   if conditions["pressure_bara"]["provenance"] == "measured" else None),
        Assumption("F5", "No H2S; CO2 and N2 at play-typical trace levels",
                   "no gas analysis supplied",
                   "Minor for PVT, decisive for materials selection and the export "
                   "specification.",
                   "gas chromatography of a separator sample"),
        Assumption("F6", "Single fluid system, no compositional grading with depth",
                   "no multi-depth sample set supplied",
                   "A graded column changes in-place volume and the contact depths.",
                   "PVT samples at more than one depth"),
    ]

    if gor_provenance == "analogue" and gor_trend["extrapolated"]:
        register.append(Assumption(
            "F7", f"GOR clamped to the {gor_trend['clamped_to']} analogue",
            "the target depth lies outside the analogue depth span",
            "The depth trend was NOT extrapolated. The true GOR is probably beyond "
            "the clamp, in the direction of the nearest analogue, so the base case "
            "is conservative in one direction only.",
            "an analogue at a comparable depth, or a sample"))

    unretired = [a for a in register if not a.retired]
    basis = {
        "conditions": conditions,
        "fluid_type": classification,
        "cases": cases,
        "trend_reads": {"gor_sm3_sm3": gor_trend, "api_degrees": api_trend},
        "analogues": [a.as_dict() for a in analogues],
        "assumption_register": [a.as_dict() for a in register],
        "open_assumptions": len(unretired),
        "provenance_summary": {
            "temperature": conditions["temperature_C"]["provenance"],
            "pressure": conditions["pressure_bara"]["provenance"],
            "gor": gor_provenance,
            "api": api_provenance,
        },
        "confidence": _confidence(conditions, gor_provenance, api_provenance),
        "next_step": (
            "Tune an equation of state to the base-case GOR and stock-tank density, "
            "then read saturation pressure, Bo and viscosity off the tuned fluid. "
            "Do not take those three from a correlation and mix them with EOS values."
        ),
    }
    return basis


def _confidence(conditions: Mapping[str, Any], gor_provenance: str,
                api_provenance: str) -> dict[str, Any]:
    sources = [conditions["temperature_C"]["provenance"],
               conditions["pressure_bara"]["provenance"],
               gor_provenance, api_provenance]
    measured = sum(1 for s in sources if s == "measured")
    if measured == len(sources):
        level, statement = "measured", "Every basis parameter is measured."
    elif measured >= 2:
        level = "partially_measured"
        statement = (f"{measured} of {len(sources)} basis parameters are measured; "
                     "the rest are analogue or correlation reads.")
    else:
        level = "synthetic"
        statement = (f"Only {measured} of {len(sources)} basis parameters are "
                     "measured. This is a synthetic fluid basis and any production "
                     "estimate built on it is a synthetic estimate.")
    return {"level": level, "measured_parameters": measured,
            "total_parameters": len(sources), "statement": statement}


def reconcile_with_measured(
    basis: Mapping[str, Any],
    measured: Mapping[str, float],
    *,
    tolerance_fraction: float = 0.10,
) -> dict[str, Any]:
    """Compare an earlier analogue basis against data that arrived later.

    Says plainly which assumptions the data confirmed and which it overturned,
    and by how much. An overturned parameter is not merely updated: anything
    derived from it has to be recomputed, and this record is the trigger.
    """
    keys = {
        "temperature_C": ("conditions", "temperature_C"),
        "pressure_bara": ("conditions", "pressure_bara"),
        "gor_sm3_sm3": ("cases", "base", "gor_sm3_sm3"),
        "api_degrees": ("cases", "base", "api_degrees"),
    }
    confirmed, overturned, unchecked = [], [], []
    for key, path in keys.items():
        if key not in measured:
            unchecked.append(key)
            continue
        node: Any = basis
        for step in path:
            node = node[step]
        assumed = node["value"] if isinstance(node, Mapping) else node
        actual = measured[key]
        deviation = abs(actual - assumed) / abs(actual) if actual else float("inf")
        entry = {"parameter": key, "assumed": assumed, "measured": actual,
                 "deviation_fraction": round(deviation, 4)}
        if deviation <= tolerance_fraction:
            confirmed.append(entry)
        else:
            entry["consequence"] = (
                f"Assumed {assumed}, measured {actual} -- off by "
                f"{100 * deviation:.0f}%. Recompute everything derived from it."
            )
            overturned.append(entry)

    return {
        "confirmed": confirmed,
        "overturned": overturned,
        "unchecked": unchecked,
        "tolerance_fraction": tolerance_fraction,
        "verdict": "analogue_basis_refuted" if overturned else "analogue_basis_supported",
        "note": (
            "A confirmed parameter validates the analogue method for this play. "
            "An overturned one invalidates every number downstream of it, not "
            "just the parameter itself."
        ),
    }


# --------------------------------------------------------------------------
# The GOR definition trap
# --------------------------------------------------------------------------
GOR_DEFINITIONS: dict[str, str] = {
    "single_stage_flash": (
        "Reservoir fluid flashed once to standard conditions. The largest of the "
        "three, because no intermediate stage retains light ends in the liquid."
    ),
    "black_oil_Rs_at_bubble_point": (
        "Rs of the saturated oil in a PVTO table -- what the simulator uses. "
        "Referenced to the saturated state, so it exceeds a flash from an "
        "undersaturated reservoir pressure."
    ),
    "separator_train": (
        "Sum of the stage gas volumes over stock-tank oil. The smallest of the "
        "three and the one a production test reports."
    ),
    "differential_liberation": (
        "Referenced to residual oil at reservoir temperature, not stock-tank oil "
        "at 15 degC, so it is not comparable to any of the above without conversion."
    ),
}


def reconcile_gor_definitions(values: Mapping[str, float],
                              *, quoted: Optional[float] = None) -> dict[str, Any]:
    """Report the spread between GOR definitions before one is quoted as *the* GOR.

    A single "GOR: 290" on a slide does not say which definition it is, and the
    definitions routinely differ by 20% on the same fluid. Matching a model to
    the wrong one biases every gas rate in the forecast.
    """
    known = {k: v for k, v in values.items() if k in GOR_DEFINITIONS}
    unknown = sorted(set(values) - set(GOR_DEFINITIONS))
    if not known:
        raise ValueError("Supply at least one recognised GOR definition. Known: "
                         + ", ".join(sorted(GOR_DEFINITIONS)))
    low, high = min(known.values()), max(known.values())
    spread = high - low
    record: dict[str, Any] = {
        "values": dict(known),
        "definitions": {k: GOR_DEFINITIONS[k] for k in known},
        "unrecognised": unknown,
        "spread": spread,
        "spread_fraction_of_max": round(spread / high, 4) if high else None,
    }
    if quoted is not None:
        matches = sorted(known, key=lambda k: abs(known[k] - quoted))
        record["quoted"] = quoted
        record["closest_definition"] = matches[0]
        record["closest_deviation"] = round(abs(known[matches[0]] - quoted), 3)
        record["ambiguous"] = len([k for k in known
                                   if abs(known[k] - quoted) < 0.05 * quoted]) > 1
        record["consequence"] = (
            f"The quoted GOR {quoted:g} is closest to '{matches[0]}'. The "
            f"definitions span {spread:g}, about "
            f"{100 * spread / high:.0f}% of the largest, so state which definition "
            "the model was matched to."
        )
    return record
