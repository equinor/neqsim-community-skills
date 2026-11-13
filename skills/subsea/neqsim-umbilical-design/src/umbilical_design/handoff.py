"""Write the study hand-off for an umbilical design: figures, key numbers, evidence status, open items."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from .figures import CHECK_LABELS, FigureMeta, render_all
from .layout import cross_section_layout
from .runner import DesignResult
from .spec import STATUS_DEFAULT, UmbilicalSpec

SCREENING_DEFAULTS = [
    ("Tube material", "super duplex, SMYS 550 MPa, E 200 GPa, usage factor 0.6 of SMYS, collapse safety factor 1.5, ovality 0.5 %"),
    ("Armour", "galvanised steel wires 4 mm, lay angle 15 deg, tensile strength 1400 MPa, allowable 40 %"),
    ("Sheaths and fillers", "inner sheath 2 mm, outer sheath 5 mm, polymer filler 950 kg/m3"),
    ("Fluids", "generic product properties for water-glycol, MEG, methanol and chemical (replace by product data sheets)"),
    ("Power cable", "copper, XLPE/EPR insulation by voltage class, conductor 90 C, no proximity effect or screen loss"),
    ("Catenary", "free hanging, touchdown offset half the water depth, tension amplification factor 1.3"),
]


def key_numbers(result: DesignResult) -> Dict[str, Dict[str, Any]]:
    """Flat ``{key: {value, unit, source}}`` map so that report numbers are traceable."""
    res = result.data["calculatedResults"]
    w = result.data["weight"]
    src = "umbilical_design.json"
    out: Dict[str, Dict[str, Any]] = {
        "umbilical_length_km": {"value": result.length_m / 1000.0, "unit": "km", "source": src},
        "umbilical_water_depth_m": {"value": result.water_depth_m, "unit": "m", "source": src},
        "umbilical_outer_diameter_mm": {"value": res["calculatedOuterDiameterMm"], "unit": "mm", "source": src},
        "umbilical_armor_layers": {"value": res["requiredArmorLayers"], "unit": "-", "source": src},
        "umbilical_dry_weight_kg_per_m": {"value": w["dryWeightPerMeterKgM"], "unit": "kg/m", "source": src},
        "umbilical_filled_weight_kg_per_m": {"value": w["filledWeightPerMeterKgM"], "unit": "kg/m", "source": src},
        "umbilical_submerged_weight_kg_per_m": {"value": w["submergedWeightPerMeterKgM"], "unit": "kg/m", "source": src},
        "umbilical_static_top_tension_kn": {"value": res["staticTopTensionKN"], "unit": "kN", "source": src},
        "umbilical_design_top_tension_kn": {"value": res["designTopTensionKN"], "unit": "kN", "source": src},
        "umbilical_armor_capacity_kn": {"value": res["armorCapacityKN"], "unit": "kN", "source": src},
        "umbilical_touchdown_bend_radius_m": {"value": res["touchdownBendRadiusM"], "unit": "m", "source": src},
        "umbilical_min_bend_radius_m": {"value": res["calculatedMinBendRadiusM"], "unit": "m", "source": src},
        "umbilical_max_collapse_utilization": {"value": res["maxCollapseUtilization"], "unit": "-", "source": src},
        "umbilical_max_burst_utilization": {"value": res["maxBurstUtilization"], "unit": "-", "source": src},
    }
    for e in result.fluid_lines:
        slug = e["name"].lower().replace(" ", "_")
        out["umbilical_%s_friction_drop_bar" % slug] = {"value": e["frictionDropBar"], "unit": "bar", "source": src}
        out["umbilical_%s_time90_min" % slug] = {"value": e["time90PercentS"] / 60.0, "unit": "min", "source": src}
    pt = result.data.get("powerTransmission")
    if pt:
        out["umbilical_power_loss_mw"] = {"value": pt["lossMW"], "unit": "MW", "source": src}
        out["umbilical_voltage_drop_percent"] = {"value": pt["voltageDropPercent"], "unit": "%", "source": src}
        out["umbilical_charging_current_a"] = {"value": pt["chargingCurrentA"], "unit": "A", "source": src}
    return out


def captions(result: DesignResult) -> Dict[str, str]:
    """Ready-to-paste captions with the headline numbers of this design."""
    res = result.data["calculatedResults"]
    w = result.data["weight"]
    n_lines = len(result.fluid_lines)
    km = result.length_m / 1000.0
    out = {
        "cross_section": (
            "Umbilical cross-section (to scale, element packing by circle placement): %d fluid lines, %d cables or "
            "fibres inside %d armour layer(s) and an outer sheath, overall diameter %.1f mm, %.1f kg/m in air "
            "(empty) and %.1f kg/m in seawater (filled)."
            % (n_lines, len(result.elements) - n_lines, res["requiredArmorLayers"], res["calculatedOuterDiameterMm"],
               w["dryWeightPerMeterKgM"], w["submergedWeightPerMeterKgM"])
        ),
        "hydraulics": (
            "Hydraulic and chemical lines over %.1f km: friction pressure drop against flow (dot = design flow) and the "
            "time for a topside pressure step to reach 90 %% at the subsea end, with the acoustic transit time as a lower "
            "bound." % km
        ),
        "mechanical": (
            "Free-hanging catenary in %.0f m water depth: static top tension %.1f kN (design %.1f kN) against an armour "
            "capacity of %.0f kN, touchdown bend radius %.0f m against a minimum bend radius of %.1f m; collapse "
            "utilisation %.2f and hoop-stress utilisation %.2f."
            % (result.water_depth_m, res["staticTopTensionKN"], res["designTopTensionKN"], res["armorCapacityKN"],
               res["touchdownBendRadiusM"], res["calculatedMinBendRadiusM"], res["maxCollapseUtilization"],
               res["maxBurstUtilization"])
        ),
        "checks": "Design checks of the umbilical: %s." % ("all pass" if result.accepted else "at least one check fails"),
        "on_a_page": "Umbilical on a page: cross-section and element schedule, design checks, line hydraulics, tension and bending, and power cable.",
    }
    pt = result.data.get("powerTransmission")
    if pt:
        out["electrical"] = (
            "Power cable against step-out distance for a %.2f MW load: voltage drop %.2f %% and loss %.3f MW at %.1f km; "
            "the cable charging current grows linearly with length (%.1f A at the design length)."
            % (pt["loadMW"], pt["voltageDropPercent"], pt["lossMW"], km, pt["chargingCurrentA"])
        )
    return out


def findings(result: DesignResult) -> List[str]:
    """Plain statements the reviewer should read first (failed checks, long response, packing)."""
    out: List[str] = []
    for key, ok in result.checks.items():
        if not ok:
            out.append("FAIL: %s." % CHECK_LABELS.get(key, key))
    slow = [l for l in result.fluid_lines if l["time90PercentS"] > 600.0 and l["type"] == "hydraulic"]
    for l in slow:
        out.append(
            "Hydraulic line '%s' needs %.0f min for 90 %% of a pressure step at the subsea end (valve response time "
            "requirement must be checked against the control-system specification)." % (l["name"], l["time90PercentS"] / 60.0)
        )
    heavy = [l for l in result.fluid_lines if l["type"] == "chemical" and l["frictionDropBar"] > 100.0]
    for l in heavy:
        out.append(
            "Chemical line '%s' has %.0f bar friction drop at its design flow; increase the inner diameter or reduce the "
            "rate." % (l["name"], l["frictionDropBar"])
        )
    lay = cross_section_layout(result)
    if lay["packing_ratio"] > 1.1:
        out.append(
            "Independent circle packing needs a %.0f %% larger bundle than the NeqSim packing estimate; check the bundle "
            "diameter, weight and bend radius." % ((lay["packing_ratio"] - 1.0) * 100.0)
        )
    pt = result.data.get("powerTransmission")
    if pt and abs(pt["voltageDropPercent"]) > 10.0:
        out.append("Power cable voltage drop %.1f %% is large; check conductor size and transmission voltage." % pt["voltageDropPercent"])
    return out


def write_handoff(
    result: DesignResult,
    out_dir: Path,
    spec: Optional[UmbilicalSpec] = None,
    meta: Optional[FigureMeta] = None,
    open_items: Optional[List[str]] = None,
    extra_sections: Optional[Dict[str, str]] = None,
) -> Dict[str, Path]:
    """Render the figures and write ``HANDOFF.md``, ``data/umbilical_design.json`` and ``data/key_numbers.json``."""
    out_dir = Path(out_dir)
    meta = meta or FigureMeta(title="Umbilical")
    figs = render_all(result, out_dir / "figures", meta)
    data_dir = out_dir / "data"
    result_path = result.save(data_dir / "umbilical_design.json")
    kn_path = data_dir / "key_numbers.json"
    kn_path.write_text(json.dumps(key_numbers(result), indent=1), encoding="utf-8")

    caps = captions(result)
    lines: List[str] = []
    lines.append("# HANDOFF: umbilical design (`%s`)" % out_dir.name)
    lines.append("")
    lines.append("Date: %s. **Basis version used = %s.** Screening-level design (NeqSim `UmbilicalMechanicalDesign`), not reviewed, not for construction." % (date.today().isoformat(), meta.basis_version))
    lines.append("")
    lines.append("## 1. Result")
    lines.append("")
    lines.append("Design checks: **%s**." % ("all pass" if result.accepted else "NOT all pass"))
    lines.append("")
    lines.append("| Check | Result |")
    lines.append("|---|---|")
    for key, ok in result.checks.items():
        lines.append("| %s | %s |" % (CHECK_LABELS.get(key, key), "PASS" if ok else "**FAIL**"))
    lines.append("")
    lines.append("## 2. Figures and captions")
    lines.append("")
    lines.append("| # | File | Caption (ready to paste) |")
    lines.append("|---|---|---|")
    for i, (name, path) in enumerate(figs.items(), start=1):
        rel = path.relative_to(out_dir).as_posix()
        lines.append("| %d | `%s` | %s |" % (i, rel, caps.get(name, "")))
    lines.append("")
    lines.append("## 3. Findings")
    lines.append("")
    items = findings(result)
    lines.extend(["- " + f for f in items] if items else ["- No check fails and no response, friction or packing flag was raised."])
    lines.append("")
    if spec is not None:
        lines.append("## 4. Input evidence")
        lines.append("")
        lines.append("| Input | Value | Status |")
        lines.append("|---|---|---|")
        lines.append("| Length | %.0f m | %s |" % (spec.length_m, spec.status("length")))
        lines.append("| Water depth | %.0f m | %s |" % (spec.water_depth_m, spec.status("water_depth")))
        for l in spec.lines:
            lines.append("| %s (%s) | ID %.2f mm, %.0f bar, %.2f m3/h | %s |" % (
                l.name, l.kind, l.inner_diameter_mm, l.design_pressure_bar, l.design_flow_m3_per_hr, spec.status("line:" + l.name)))
        for c in spec.cables:
            lines.append("| %s | %d cores, %.0f V | %s |" % (c.name, c.cores, c.voltage_v, spec.status("cable:" + c.name)))
        lines.append("")
    lines.append("## 5. Screening defaults used (status: %s)" % STATUS_DEFAULT)
    lines.append("")
    lines.append("| Item | Default |")
    lines.append("|---|---|")
    for k, v in SCREENING_DEFAULTS:
        lines.append("| %s | %s |" % (k, v))
    lines.append("")
    lines.append("## 6. Open items")
    lines.append("")
    base_open = [
        "Replace the screening defaults by the umbilical vendor data sheet and the governing specification before use in a design.",
        "Dynamic (riser) section, fatigue, torsion balance, crush and installation analysis are not part of this screening.",
        "J-tube pull-in, topside hang-off and the host interface are not designed here.",
    ]
    lines.extend(["- " + t for t in (open_items or []) + base_open])
    lines.append("")
    if extra_sections:
        for title, body in extra_sections.items():
            lines.append("## " + title)
            lines.append("")
            lines.append(body)
            lines.append("")
    lines.append("## Reproduce")
    lines.append("")
    lines.append("```")
    lines.append("python -m umbilical_design render --result data\\umbilical_design.json --out . --basis-version \"%s\"" % meta.basis_version)
    lines.append("```")
    handoff_path = out_dir / "HANDOFF.md"
    handoff_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    paths = dict(figs)
    paths["handoff"] = handoff_path
    paths["result"] = result_path
    paths["key_numbers"] = kn_path
    return paths
