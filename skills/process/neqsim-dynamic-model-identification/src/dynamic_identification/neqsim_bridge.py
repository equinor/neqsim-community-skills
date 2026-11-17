"""Join NeqSim physics and identified dynamics (the pattern of the NeqSim x TimeSeriesAnalysis notebook).

Three uses:

1. **Physics before identification.** ``automation_evaluator`` runs a NeqSim ProcessSystem or ProcessModel at an
   observed operating point; ``physics_residuals`` turns measured minus NeqSim-expected values into calibrated,
   filtered residuals; ``two_residual_diagnosis`` separates a physical change (two independent signals move)
   from a measurement or model fault (one moves).
2. **Physics checks identification.** ``steady_gains`` takes central-difference gains from NeqSim with a step
   convergence check; ``compare_gains`` tests identified gains against them (sign and size).
3. **Replay.** ``simulate_unit`` runs an identified model forward on new inputs with the TimeSeriesAnalysis
   ``UnitModel`` (what-if replay and chronological hold-out validation).

NeqSim (JPype) and TimeSeriesAnalysis (pythonnet CoreCLR) run in the same Python process. Both start orders were
verified on Windows; on Linux load CoreCLR first, as the notebook does.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence

import numpy as np

Evaluate = Callable[[Mapping[str, float]], dict[str, float]]


def automation_evaluator(
    process, inputs: Mapping[str, str], outputs: Mapping[str, str]
) -> Evaluate:
    """Wrap a NeqSim process as ``evaluate({input: value}) -> {output: value}``.

    ``inputs`` and ``outputs`` map a name to ``"address|unit"``, for example
    ``{"flow": "feed.flowRate|kg/sec"}`` and ``{"power": "comp.power|kW"}``. Addresses come from
    ``process.getAutomation().getVariableList(unit)``. Each call sets the inputs, runs the process and reads the
    outputs; the caller owns the process object, so reuse one per thread.
    """
    automation = process.getAutomation()

    def split(spec: str) -> tuple[str, str]:
        address, _, unit = spec.partition("|")
        return address.strip(), unit.strip()

    def evaluate(values: Mapping[str, float]) -> dict[str, float]:
        for name, value in values.items():
            address, unit = split(inputs[name])
            automation.setVariableValue(address, float(value), unit)
        automation.run()
        out = {}
        for name, spec in outputs.items():
            address, unit = split(spec)
            out[name] = float(automation.getVariableValue(address, unit))
        return out

    return evaluate


def steady_gains(
    evaluate: Evaluate,
    base: Mapping[str, float],
    steps: Mapping[str, float],
    outputs: Sequence[str] | None = None,
) -> dict[str, object]:
    """Central-difference steady-state gains d(output)/d(input) at ``base``, with a half-step convergence check.

    The base point is restored at the end. ``relative_step_error`` above about 0.03 means the response is not
    linear over the step; use a smaller step or a local model per operating region.
    """
    names = list(base)

    def gains(scale: float) -> dict[str, dict[str, float]]:
        table: dict[str, dict[str, float]] = {}
        for name in names:
            h = float(steps[name]) * scale
            plus = evaluate({**base, name: base[name] + h})
            minus = evaluate({**base, name: base[name] - h})
            for out in outputs or list(plus):
                table.setdefault(out, {})[name] = (plus[out] - minus[out]) / (2.0 * h)
        return table

    full, half = gains(1.0), gains(0.5)
    evaluate(dict(base))
    errors = [
        abs(full[o][i] - half[o][i]) / max(abs(half[o][i]), 1e-9)
        for o in half
        for i in half[o]
    ]
    return {
        "gains": half,
        "relative_step_error": max(errors) if errors else 0.0,
        "base": dict(base),
        "steps": dict(steps),
    }


def compare_gains(
    identified: Mapping[str, float],
    physics: Mapping[str, float],
    tolerance: float = 0.3,
) -> dict[str, object]:
    """Compare identified gains of one output with NeqSim gains (same input names and units).

    A gain is ``consistent`` when the sign agrees and the ratio is within ``1 +/- tolerance``. A sign error or a
    ratio far from one points to a wrong tag, a unit or flow-basis mismatch, closed-loop bias or an unmodelled
    effect; it does not by itself say which.
    """
    rows = {}
    for name, value in identified.items():
        if name not in physics:
            continue
        ref = physics[name]
        ratio = value / ref if ref else math.inf
        rows[name] = {
            "identified": value,
            "neqsim": ref,
            "ratio": ratio,
            "consistent": (value * ref > 0) and abs(ratio - 1.0) <= tolerance,
        }
    return {
        "inputs": rows,
        "all_consistent": bool(rows) and all(r["consistent"] for r in rows.values()),
    }


def physics_residuals(
    measured: Mapping[str, Sequence[float]],
    expected: Mapping[str, Sequence[float]],
    calibration: slice,
    smoothing_samples: float = 1.5,
    threshold: float = 4.0,
) -> dict[str, dict[str, object]]:
    """Measured minus NeqSim-expected values, standardised on a healthy calibration window and low-pass filtered.

    Standardising on the calibration window removes a steady model offset and scales by the normal scatter. The
    filter is first order with time constant ``smoothing_samples``. ``flag`` marks samples whose filtered residual
    exceeds ``threshold``; it is an empirical threshold, not a probability. Check residual autocorrelation before
    choosing persistence rules.
    """
    result = {}
    alpha = 1.0 - math.exp(-1.0 / smoothing_samples) if smoothing_samples > 0 else 1.0
    for name, values in measured.items():
        r = np.asarray(values, dtype=float) - np.asarray(expected[name], dtype=float)
        base = r[calibration]
        base = base[np.isfinite(base)]
        if len(base) < 3:
            raise ValueError(
                f"{name}: the calibration window has fewer than three valid residuals"
            )
        z = (r - base.mean()) / (base.std(ddof=1) or 1.0)
        filtered = np.empty_like(z)
        state = 0.0
        for i, v in enumerate(z):
            state = state if not np.isfinite(v) else state + alpha * (v - state)
            filtered[i] = state
        result[name] = {
            "residual": r,
            "standardised": z,
            "filtered": filtered,
            "flag": np.abs(filtered) > threshold,
            "calibration_mean": float(base.mean()),
            "calibration_std": float(base.std(ddof=1)),
        }
    return result


def two_residual_diagnosis(
    primary_flag: Sequence[bool],
    secondary_flag: Sequence[bool],
    labels: tuple[str, str, str] = (
        "physical change candidate",
        "measurement or model candidate (primary only)",
        "within baseline",
    ),
) -> list[str]:
    """Label each sample: both residuals flagged, only the primary flagged, or neither.

    Example: compressor power (primary) and discharge temperature (secondary). Lower efficiency raises both; a
    power-meter bias moves power alone. The secondary signal must be measured independently and not fitted.
    """
    out = []
    for p, s in zip(primary_flag, secondary_flag):
        out.append(labels[0] if (p and s) else labels[1] if p else labels[2])
    return out


def simulate_unit(
    model: Mapping[str, object],
    inputs: Mapping[str, Sequence[float]],
    timebase_s: float,
) -> np.ndarray:
    """Run an identified unit model forward on new inputs (TimeSeriesAnalysis ``UnitModel.Iterate``).

    ``model`` is the dict returned by ``identify_unit`` or the closed-loop process model (gains and ``u0`` keyed by
    input name, ``time_constant_s``, ``time_delay_s``, ``bias``). Inputs are given in the same names. The model
    starts from steady state at the first sample.
    """
    from .runtime import load

    load()
    import TimeSeriesAnalysis.Dynamic as dynamic  # type: ignore[import-not-found]
    from System import Array, Double  # type: ignore[import-not-found]

    names = list(model["gains"])
    params = dynamic.UnitParameters()
    params.LinearGains = Array[Double]([float(model["gains"][n]) for n in names])
    params.U0 = Array[Double]([float(model.get("u0", {}).get(n, 0.0)) for n in names])
    params.UNorm = Array[Double]([1.0] * len(names))
    params.TimeConstant_s = float(model.get("time_constant_s") or 0.0)
    params.TimeDelay_s = float(model.get("time_delay_s") or 0.0)
    params.Bias = float(model.get("bias") or 0.0)
    unit = dynamic.UnitModel(params, "replay")
    columns = [np.asarray(inputs[n], dtype=float) for n in names]
    unit.WarmStart()
    out = np.empty(len(columns[0]))
    for k in range(len(out)):
        row = Array[Double]([float(c[k]) for c in columns])
        out[k] = float(unit.Iterate(row, float(timebase_s))[0])
    return out
