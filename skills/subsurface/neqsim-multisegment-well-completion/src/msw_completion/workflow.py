"""Config-driven route: deck -> plain multi-segment wells -> completor -> device check -> zonal screening -> evidence.

Example config::

    {
      "deck": "<task>/step2_analysis/decks/BASE.DATA",
      "out_dir": "<task>/step2_analysis/completion",
      "design": {"completion": [...], "aicd": [{"number": 1, "strength": 2e-4, "x": 3.0, "y": 0.6}]},
      "parameter_source": "vendor datasheet X rev 2" | "illustrative",
      "fluid": {"components": {...}, "temperature_c": 110, "pressure_bara": 300, "fallback": {...}},
      "calibrate": {"device": {"type": "AICD", "number": 1}, "design_rate_rm3_day": 2.0, "design_dp_bar": 5.0},
      "check_rate_rm3_day": 2.0,
      "zones": [{"name": "heel", "productivity_index": 30, "water_fraction": 0.0, "gas_fraction": 0.6,
                 "devices": 40}],
      "screening": {"device": {"type": "AICD", "number": 1}, "bare_drawdown_bar": 5, "max_drawdown_bar": 40}
    }
"""

from __future__ import annotations

import copy
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from .case import DEVICE_KEYWORD, build_case
from .devices import (DEVICE_CLASSES, PhaseProperties, calibrate_strength, device_from_dict, pressure_drop_bar,
                      single_phase_drops)
from .msw import add_plain_msw, keyword_blocks, split_schedule
from .runner import CompletorUnavailable, read_device_layer, run_completor
from .screening import Zone, compare_at_same_oil

SCHEMA = "well_completion_evidence.v1"


def _device_table(design: Dict[str, Any], kind: str) -> List[Dict[str, Any]]:
    return design.get(DEVICE_KEYWORD[kind.upper()]) or []


def _device(design: Dict[str, Any], ref: Dict[str, Any]):
    kind = str(ref["type"]).upper()
    for row in _device_table(design, kind):
        if int(row["number"]) == int(ref["number"]):
            return device_from_dict(kind, row)
    raise ValueError(f"{kind} device {ref['number']} is not defined in the design")


def _properties(config: Dict[str, Any], evidence: Dict[str, Any]) -> Optional[PhaseProperties]:
    if config.get("phase_properties"):
        evidence["sources"].append({"item": "phase_properties", "source": config.get("phase_properties_source",
                                                                                     "user input")})
        return PhaseProperties(**config["phase_properties"])
    if config.get("fluid"):
        from .fluid import phase_properties_from_neqsim

        f = config["fluid"]
        result = phase_properties_from_neqsim(f.get("components"), f["temperature_c"], f["pressure_bara"],
                                              f.get("eos", "SRK"), f.get("fallback"), f.get("e300"), f.get("water"))
        evidence["sources"].append({"item": "phase_properties", "source": result["source"],
                                    "fallback_used": result["fallback_used"]})
        if result["fallback_used"]:
            evidence["warnings"].append(f"phases not formed at device conditions, values given by user: "
                                        f"{', '.join(result['fallback_used'])}")
        return result["properties"]
    return None


def _wsegdims_check(deck: str, layer: Dict[str, Dict[str, object]], evidence: Dict[str, Any]) -> None:
    head, _ = split_schedule(deck)
    blocks = keyword_blocks(head, "WSEGDIMS")
    if not blocks or not blocks[0][2]:
        evidence["warnings"].append("WSEGDIMS is missing from RUNSPEC; the simulator rejects multi-segment wells")
        return
    rec = blocks[0][2][0] + [None] * 3
    max_seg = int(rec[1]) if rec[1] else 0
    max_br = int(rec[2]) if rec[2] else 0
    for well, info in layer.items():
        if info["segments"] > max_seg or info["branches"] > max_br:
            evidence["warnings"].append(f"{well}: {info['segments']} segments and {info['branches']} branches "
                                        f"exceed WSEGDIMS {max_seg} {max_br}")


def _plot(devices: Dict[str, Any], props: PhaseProperties, path: Path, rate_max: float) -> Optional[str]:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None
    rates = [rate_max * i / 60 for i in range(1, 61)]
    fig, axes = plt.subplots(1, len(devices), figsize=(4.2 * len(devices), 3.6), squeeze=False)
    for ax, (label, device) in zip(axes[0], devices.items()):
        for phase, fr, color in (("oil", (1, 0, 0), "#2b6c3a"), ("water", (0, 1, 0), "#1f5fa8"),
                                 ("gas", (0, 0, 1), "#c0392b")):
            ax.plot(rates, [pressure_drop_bar(device, q, fr, props) for q in rates], color=color, label=phase)
        ax.set_title(label)
        ax.set_xlabel("Rate per device (rm3/day)")
        ax.set_ylabel("Pressure drop (bar)")
        ax.set_yscale("log")
        ax.grid(alpha=0.3, which="both")
        ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return str(path)


def run_completion_workflow(config: Dict[str, Any]) -> Dict[str, Any]:
    """Run the configured steps and return a ``well_completion_evidence.v1`` record."""
    out_dir = Path(config["out_dir"]) if config.get("out_dir") else None
    evidence: Dict[str, Any] = {"schema": SCHEMA, "status": "ok", "verification": "unverified", "sources": [],
                                "warnings": [], "missing": [], "outputs": {}, "steps": []}
    design = copy.deepcopy(config.get("design") or {})
    source = config.get("parameter_source")
    if not source:
        evidence["missing"].append("parameter_source: say where the device parameters come from (vendor "
                                   "datasheet, inflow-control team) or 'illustrative'")
    elif source == "illustrative":
        evidence["warnings"].append("device parameters are illustrative, not vendor data: results show behaviour "
                                    "only and must not be used for planning")
    evidence["parameter_source"] = source
    try:
        props = _properties(config, evidence)
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        props = None
        evidence["missing"].append(f"phase properties: {exc}")
    if config.get("calibrate"):
        cal = config["calibrate"]
        if props is None:
            evidence["missing"].append("calibrate needs phase_properties or fluid")
        else:
            ref = cal["device"]
            device = calibrate_strength(_device(design, ref), cal["design_rate_rm3_day"], cal["design_dp_bar"],
                                        props, tuple(cal.get("fractions", (1.0, 0.0, 0.0))))
            for row in _device_table(design, ref["type"]):
                if int(row["number"]) == int(ref["number"]):
                    row["strength"] = device.strength
            evidence["calibration"] = {"device": ref, "design_rate_rm3_day": cal["design_rate_rm3_day"],
                                       "design_dp_bar": cal["design_dp_bar"], "strength": device.strength}
            evidence["steps"].append("strength calibrated to the design point")

    deck_text = None
    if config.get("deck"):
        deck_path = Path(config["deck"])
        deck_text = deck_path.read_text(encoding="utf-8", errors="replace")
        evidence["sources"].append({"item": "deck", "path": str(deck_path)})
        has_msw = bool(keyword_blocks(split_schedule(deck_text)[1], "WELSEGS"))
        mode = config.get("add_plain_msw", "auto")
        if mode is True or (mode == "auto" and not has_msw):
            msw = config.get("msw", {})
            deck_text, infos = add_plain_msw(deck_text, msw.get("wells"), msw.get("diameter_m", 0.15),
                                             msw.get("roughness_m", 1.0e-4))
            evidence["plain_msw"] = infos
            evidence["steps"].append("plain multi-segment wells added from COMPDAT and the grid")
            if out_dir is not None:
                out_dir.mkdir(parents=True, exist_ok=True)
                path = out_dir / f"{deck_path.stem}_MSW{deck_path.suffix}"
                path.write_text(deck_text, encoding="utf-8")
                evidence["outputs"]["plain_msw_deck"] = str(path)
            evidence["warnings"].append("plain WELSEGS measured depths follow the connection cell centres; replace "
                                        "them with the planned trajectory when it exists")

    if design.get("completion") and deck_text is not None and source:
        case_text = build_case(design)
        if out_dir is None:
            evidence["missing"].append("out_dir is needed to write the completor case and deck")
        else:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "completor.case").write_text(case_text, encoding="utf-8")
            evidence["outputs"]["case_file"] = str(out_dir / "completor.case")
            stem = Path(config["deck"]).stem
            target = out_dir / f"{stem}_COMPLETOR{Path(config['deck']).suffix}"
            try:
                run = run_completor(case_text, deck_text, target)
                evidence["outputs"]["completor_deck"] = run["output"]
                evidence["completor_version"] = run["completor_version"]
                evidence["warnings"] += [f"completor: {w}" for w in run["warnings"]]
                layer = read_device_layer(Path(run["output"]).read_text(encoding="utf-8"))
                evidence["device_layer"] = layer
                _wsegdims_check(Path(run["output"]).read_text(encoding="utf-8"), layer, evidence)
                evidence["steps"].append("completor deck written")
            except CompletorUnavailable as exc:
                evidence["missing"].append(str(exc))
            except Exception as exc:  # noqa: BLE001 - completor errors name the well or keyword
                evidence["missing"].append(f"completor failed: {exc}")

    if props is not None:
        evidence["phase_properties"] = asdict(props)
        devices = {}
        for kind in DEVICE_CLASSES:
            if kind in DEVICE_KEYWORD:
                for row in _device_table(design, kind):
                    devices[f"{kind} {row['number']}"] = device_from_dict(kind, row)
        if devices:
            rate = float(config.get("check_rate_rm3_day", 1.0))
            evidence["device_check"] = {label: single_phase_drops(d, rate, props) for label, d in devices.items()}
            if out_dir is not None:
                png = _plot(devices, props, out_dir / "device_curves.png", 4.0 * rate)
                if png:
                    evidence["outputs"]["device_curves"] = png
    if config.get("zones") and config.get("screening"):
        if props is None:
            evidence["missing"].append("zonal screening needs phase_properties or fluid")
        else:
            s = config["screening"]
            zones = [Zone(**z) for z in config["zones"]]
            evidence["screening"] = compare_at_same_oil(zones, _device(design, s["device"]), props,
                                                        float(s["bare_drawdown_bar"]), float(s["max_drawdown_bar"]))
            evidence["steps"].append("zonal inflow compared at the bare oil rate")
            bare_rows = evidence["screening"]["bare"]["zones"]
            dev_rows = evidence["screening"]["with_devices"]["zones"]
            for zone, b, d in zip(zones, bare_rows, dev_rows):
                fo = zone.fractions[0]
                if fo < 0.5 and b["rate_rm3_day"] > 0 and d["rate_rm3_day"] > b["rate_rm3_day"]:
                    evidence["warnings"].append(
                        f"zone '{zone.name}' ({zone.gas_fraction:.0%} gas, {zone.water_fraction:.0%} water) produces "
                        f"more with devices than without: these device parameters do not choke it")
    if evidence["missing"]:
        evidence["status"] = "blocked"
    evidence["required_checks"] = [
        "device parameters from the vendor or the inflow-control team (not illustrative values)",
        "simulate the completor deck (OPM Flow or Eclipse) and compare with the bare-well case",
        "trajectory measured depths instead of cell-centre measured depths where a well plan exists",
    ]
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "completion_evidence.json"
        path.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
        evidence["outputs"]["evidence"] = str(path)
    return evidence
