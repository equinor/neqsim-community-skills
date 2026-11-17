"""Config-driven identification on historian files with an evidence record.

Example config::

    {
      "series": {"pv": {"path": "TIC.csv"}, "out": {"path": "TIC.CO.csv"}, "sp": {"path": "TIC.SP.csv"},
                 "load": {"path": "speed.csv", "sentinels": [-9999]}},
      "window": {"start": "2026-06-01", "end": "2026-07-01"},
      "timebase_s": 3600,
      "frozen_samples": 0,
      "analyses": {
        "loop": {"pv": "pv", "sp": "sp", "out": "out", "out_range": [0, 100], "controller_type": "Temperature"},
        "unit": {"output": "pv", "inputs": ["load"]}
      },
      "out_dir": "<task>/step2_analysis/dynamic_identification"
    }
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from .data import align, load_series, saturation
from .identify import identify_closed_loop, identify_pid, identify_unit
from .runtime import TsaUnavailable, find_assemblies

SCHEMA = "dynamic_identification_evidence.v1"


def _plot(times, measured: dict[str, np.ndarray], simulated: dict[str, np.ndarray], path: Path) -> str:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(len(measured), 1, figsize=(10, 2.6 * len(measured)), squeeze=False, sharex=True)
    for ax, (name, values) in zip(axes[:, 0], measured.items()):
        ax.plot(times, values, lw=0.8, color="#333333", label=f"{name} measured")
        if name in simulated:
            ax.plot(times, simulated[name], lw=0.9, color="#c0392b", label=f"{name} model")
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return str(path)


def _judge(name: str, result: dict[str, Any], dt: float, evidence: dict[str, Any]) -> None:
    """Mark a result usable or not, with the reasons, so that agents cannot pass on a meaningless fit."""
    fitting = result.get("fitting") or {}
    reasons = []
    total, bad = fitting.get("total_points") or 0, fitting.get("bad_points") or 0
    if not fitting.get("able_to_identify"):
        reasons.append("the solver could not identify a model")
    if total and bad / total > 0.5:
        reasons.append(f"{bad:.0f} of {total:.0f} points were bad and excluded")
    score = fitting.get("fit_score_pct")
    if score is not None and score < 0:
        reasons.append(f"fit score {score:.0f} % (worse than a constant)")
    solver = str(fitting.get("solver", "")).lower()
    if "no minimum found" in solver or "init heuristic" in solver:
        reasons.append("the solver found no minimum and returned its initial heuristic")
    if "time_constant_s" in result:
        tc, delay = result.get("time_constant_s") or 0.0, result.get("time_delay_s") or 0.0
        if tc < 2 * dt and delay < 2 * dt:
            evidence["warnings"].append(
                f"{name}: time constant and delay are below two samples ({dt:g} s): the dynamics are faster than "
                f"the data resolve; only the gain is meaningful")
    result["usable"] = not reasons
    if reasons:
        evidence["warnings"].append(f"{name}: not usable - " + "; ".join(reasons))


def run_identification(config: dict[str, Any]) -> dict[str, Any]:
    """Run the configured analyses; returns a ``dynamic_identification_evidence.v1`` record."""
    out_dir = Path(config["out_dir"]) if config.get("out_dir") else None
    evidence: dict[str, Any] = {"schema": SCHEMA, "status": "ok", "verification": "unverified", "warnings": [],
                                "missing": [], "sources": [], "results": {}, "outputs": {}}
    series = {}
    for role, spec in (config.get("series") or {}).items():
        try:
            series[role] = load_series(spec["path"], spec.get("column"), spec.get("time_column", "time"),
                                       spec.get("sentinels", ()))
            evidence["sources"].append({"role": role, "path": str(spec["path"]),
                                        "column": spec.get("column", "avg or second column")})
        except Exception as exc:  # noqa: BLE001 - reported
            evidence["missing"].append(f"series {role}: {exc}")
    if evidence["missing"] or not series:
        evidence["status"] = "blocked"
        return _finish(evidence, out_dir)
    window = config.get("window") or {}
    hold = [role for role, spec in (config.get("series") or {}).items() if spec.get("hold")]
    data = align(series, config.get("timebase_s"), window.get("start"), window.get("end"),
                 config.get("max_gap_s"), int(config.get("frozen_samples", 0)), hold)
    values, dt = data["values"], data["timebase_s"]
    evidence["data"] = {"timebase_s": dt, "start": str(data["times"][0]), "end": str(data["times"][-1]),
                        "samples": len(data["times"]), "bad_fraction": data["bad_fraction"]}
    for role, fraction in data["bad_fraction"].items():
        if fraction > 0.3:
            evidence["warnings"].append(f"{role}: {fraction:.0%} of the samples are bad or missing; if the tag is "
                                        f"stored by exception (compressed PI/IMS data, setpoints), set hold: true")
    analyses = config.get("analyses") or {}
    tsa_folder = find_assemblies()
    evidence["engine"] = {"name": "equinor/TimeSeriesAnalysis", "assemblies": str(tsa_folder) if tsa_folder else None}
    simulated: dict[str, np.ndarray] = {}
    try:
        if "loop" in analyses:
            loop = analyses["loop"]
            pv, sp, out = values[loop["pv"]], values[loop["sp"]], values[loop["out"]]
            result: dict[str, Any] = {}
            u_range = loop.get("out_range")
            if u_range:
                result["saturation"] = saturation(out, float(u_range[0]), float(u_range[1]),
                                                  float(loop.get("saturation_tolerance", 0.5)))
                for stop in ("min", "max"):
                    share = result["saturation"][f"at_{stop}_fraction"]
                    if share and share > 0.05:
                        evidence["warnings"].append(f"controller output is at its {stop} stop {share:.0%} of the "
                                                    f"time: the loop loses authority there, and those samples carry "
                                                    f"no dynamic information")
            pid = identify_pid(pv, sp, out, dt, loop.get("controller_type", "Unset"), u_range, loop.get("pv_range"))
            _judge("PID identification", pid, dt, evidence)
            result["pid"] = pid
            closed = identify_closed_loop(pv, sp, out, dt, loop.get("pid"))
            series_d = closed.pop("disturbance_series")
            _judge("closed-loop process model", closed, dt, evidence)
            result["process_closed_loop"] = closed
            if "uncertain" in closed["fitting"]["solver"].lower():
                evidence["warnings"].append(f"closed-loop identification: {closed['fitting']['solver']}")
            if np.nanstd(sp) < 1e-9:
                evidence["warnings"].append("the setpoint never changes in this window: the process gain is "
                                            "identified from disturbances alone and is less certain")
            if out_dir is not None:
                out_dir.mkdir(parents=True, exist_ok=True)
                np.savetxt(out_dir / "disturbance.csv",
                           np.column_stack([np.arange(len(series_d)) * dt,
                                            [np.nan if v is None else v for v in series_d]]),
                           delimiter=",", header="t_s,disturbance", comments="")
                evidence["outputs"]["disturbance"] = str(out_dir / "disturbance.csv")
            evidence["results"]["loop"] = result
        if "unit" in analyses:
            unit = analyses["unit"]
            inputs = {name: values[name] for name in unit["inputs"]}
            result = identify_unit(values[unit["output"]], inputs, dt, bool(unit.get("estimate_delay", True)),
                                   str(unit.get("method", "best")))
            y_sim = result.pop("y_sim", None)
            if y_sim is not None:
                simulated[unit["output"]] = np.array(y_sim, dtype=float)
            evidence["results"]["unit"] = result
            _judge("unit model", result, dt, evidence)
            loop_cfg = analyses.get("loop") or {}
            loop_roles = {loop_cfg.get(k) for k in ("pv", "sp", "out")} - {None}
            if unit["output"] in loop_roles and any(name in loop_roles for name in unit["inputs"]):
                evidence["warnings"].append("the unit model uses a loop's own controller output as input: under "
                                            "feedback the open-loop estimate is biased; use the closed-loop result")
            if not result["fitting"]["able_to_identify"]:
                evidence["warnings"].append("unit identification did not converge")
    except TsaUnavailable as exc:
        evidence["missing"].append(str(exc))
    except Exception as exc:  # noqa: BLE001 - an engine failure is a finding, not a crash
        first = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
        evidence["warnings"].append(f"the identification engine failed on this window ({first[:200]}); "
                                    f"try a longer window, another time base or fewer bad samples")
        evidence["engine_error"] = first[:500]
    if out_dir is not None and evidence["results"]:
        out_dir.mkdir(parents=True, exist_ok=True)
        evidence["outputs"]["plot"] = _plot(data["times"], values, simulated, out_dir / "identification.png")
    if evidence["missing"]:
        evidence["status"] = "blocked"
    evidence["required_checks"] = [
        "the window contains excitation (setpoint changes, load changes); flat data identifies nothing",
        "the time base resolves the dynamics: a time constant below about two samples is not identified",
        "results are compared with the controller configuration (tuning, ranges, direct or reverse action)",
    ]
    return _finish(evidence, out_dir)


def _finish(evidence: dict[str, Any], out_dir) -> dict[str, Any]:
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / "identification_evidence.json"
        path.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
        evidence["outputs"]["evidence"] = str(path)
    return evidence
