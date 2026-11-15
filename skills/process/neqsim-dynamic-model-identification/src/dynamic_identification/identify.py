"""Dynamic model identification with TimeSeriesAnalysis: process model, PID parameters and closed-loop model."""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

import numpy as np

from .data import BAD_DATA_ID, to_tsa
from .runtime import load


def _api():
    load()
    import TimeSeriesAnalysis.Dynamic as dynamic  # type: ignore[import-not-found]
    from System import Array, Double  # type: ignore[import-not-found]

    return dynamic, Array, Double


def _arr(Array, Double, values: Sequence[float]):
    return Array[Double](to_tsa(values))


def _num(value) -> Optional[float]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v != BAD_DATA_ID else None


def _fitting(fitting) -> Dict[str, object]:
    return {
        "able_to_identify": bool(fitting.WasAbleToIdentify),
        "solver": str(fitting.SolverID),
        "fit_score_pct": _num(fitting.FitScorePrc),
        "r2_diff": _num(fitting.RsqDiff),
        "bad_points": _num(fitting.NFittingBadDataPoints),
        "total_points": _num(fitting.NFittingTotalDataPoints),
    }


def _dataset(dynamic, Array, Double, timebase_s: float, y: Sequence[float], inputs: Sequence[Sequence[float]],
             y_setpoint: Optional[Sequence[float]] = None):
    if not 1 <= len(inputs) <= 6:
        raise ValueError("TimeSeriesAnalysis takes one to six inputs")
    n = len(y)
    if any(len(u) != n for u in inputs) or (y_setpoint is not None and len(y_setpoint) != n):
        raise ValueError("all series must have the same length")
    ds = dynamic.UnitDataSet("neqsim")
    ds.SetU(*[_arr(Array, Double, u) for u in inputs])
    ds.Y_meas = _arr(Array, Double, y)
    if y_setpoint is not None:
        ds.Y_setpoint = _arr(Array, Double, y_setpoint)
    ds.CreateTimeStamps(float(timebase_s), None)
    return ds


def _unit_parameters(model, names: List[str]) -> Dict[str, object]:
    p = model.GetModelParameters()
    gains = [float(g) for g in p.LinearGains] if p.LinearGains is not None else []
    u0 = [float(v) for v in p.U0] if p.U0 is not None else []
    return {
        "gains": dict(zip(names, gains)),
        "gain_uncertainty": dict(zip(names, [float(g) for g in p.LinearGainUnc])) if p.LinearGainUnc else None,
        "time_constant_s": _num(p.TimeConstant_s),
        "time_delay_s": _num(p.TimeDelay_s),
        "bias": _num(p.Bias),
        "u0": dict(zip(names, u0)),
        "fitting": _fitting(p.Fitting),
        "model_form": "y = bias + sum(gain_i (u_i - u0_i)) through a first-order lag with time constant and delay",
        # delay and lag can trade off in the fit; their sum is the robust response time
        "t63_s": (_num(p.TimeDelay_s) or 0.0) + (_num(p.TimeConstant_s) or 0.0),
        "t95_s": (_num(p.TimeDelay_s) or 0.0) + 3.0 * (_num(p.TimeConstant_s) or 0.0),
    }


_UNIT_METHODS = {"auto": "Identify", "linear": "IdentifyLinear", "static": "IdentifyLinearAndStatic"}


def identify_unit(y: Sequence[float], inputs: Dict[str, Sequence[float]], timebase_s: float,
                  estimate_delay: bool = True, method: str = "best") -> Dict[str, object]:
    """Identify an open-loop process model (gain per input, time constant, time delay, bias).

    Use for an output driven by inputs that are not themselves set by feedback from that output. NaN marks bad
    samples; TimeSeriesAnalysis skips them.

    ``method``: ``auto`` (TimeSeriesAnalysis ``Identify``, which also tries curvature and static candidates),
    ``linear`` (``IdentifyLinear``, a linear dynamic model), ``static``, or ``best`` (default: run ``auto`` and
    ``linear`` and keep the higher fit score). ``auto`` can settle on a static model when a linear dynamic one fits
    the data better, so ``best`` is the safe default.
    """
    dynamic, Array, Double = _api()
    names = list(inputs)
    tried = ["auto", "linear"] if method == "best" else [method]
    candidates = []
    for name in tried:
        if name not in _UNIT_METHODS:
            raise ValueError(f"method must be one of {sorted(_UNIT_METHODS) + ['best']}")
        ds = _dataset(dynamic, Array, Double, timebase_s, y, [inputs[k] for k in names])
        result = getattr(dynamic.UnitIdentifier, _UNIT_METHODS[name])(ds, dynamic.FittingSpecs(None, None),
                                                                      bool(estimate_delay))
        model, fitted = result if isinstance(result, tuple) else (result, ds)
        out = _unit_parameters(model, names)
        out["method"] = name
        if fitted.Y_sim is not None:
            out["y_sim"] = [float(v) for v in fitted.Y_sim]
        candidates.append(out)
    score = [c["fitting"]["fit_score_pct"] if c["fitting"]["able_to_identify"] and
             c["fitting"]["fit_score_pct"] is not None else -math.inf for c in candidates]
    best = candidates[int(np.argmax(score))]
    if len(candidates) > 1:
        best["alternatives"] = [{k: c[k] for k in ("method", "gains", "time_constant_s", "time_delay_s")} |
                                {"fit_score_pct": c["fitting"]["fit_score_pct"]} for c in candidates if c is not best]
    return best


_CONTROLLER_TYPES = ("Unset", "Flow", "Pressure", "Level", "Temperature", "Duty", "AntiSurge")


def identify_pid(pv: Sequence[float], sp: Sequence[float], out: Sequence[float], timebase_s: float,
                 controller_type: str = "Unset", u_range: Optional[Sequence[float]] = None,
                 y_range: Optional[Sequence[float]] = None) -> Dict[str, object]:
    """Identify PI(D) parameters from measurement, setpoint and controller output.

    ``u_range`` and ``y_range`` give the controller's output and measurement ranges when known; Kp is then
    expressed in the controller's scaled units.
    """
    dynamic, Array, Double = _api()
    if controller_type not in _CONTROLLER_TYPES:
        raise ValueError(f"controller_type must be one of {_CONTROLLER_TYPES}")
    if u_range and y_range:
        scaling = dynamic.PidScaling(float(y_range[0]), float(y_range[1]), float(u_range[0]), float(u_range[1]), True)
    else:
        scaling = dynamic.PidScaling()
    identifier = dynamic.PidIdentifier(scaling, float(timebase_s), getattr(dynamic.PidControllerType,
                                                                          controller_type))
    ds = _dataset(dynamic, Array, Double, timebase_s, pv, [out], sp)
    result = identifier.Identify(ds, False, False)
    params = result[0] if isinstance(result, tuple) else result
    return {"kp": _num(params.Kp), "ti_s": _num(params.Ti_s), "td_s": _num(params.Td_s), "u0": _num(params.u0),
            "scaling": "controller ranges" if (u_range and y_range) else "engineering units (default scaling)",
            "fitting": _fitting(params.Fitting)}


def identify_closed_loop(pv: Sequence[float], sp: Sequence[float], out: Sequence[float], timebase_s: float,
                         pid: Optional[Dict[str, float]] = None, detect_frozen: bool = True) -> Dict[str, object]:
    """Identify the process model and the disturbance from closed-loop data (output driven by feedback).

    ``pid`` (``kp``, ``ti_s``, ``td_s``) can be the known tuning; without it TimeSeriesAnalysis estimates it.
    The disturbance is what the loop had to reject: the part of the measurement the process model does not
    explain.
    """
    dynamic, Array, Double = _api()
    pid_source = "given"
    if not pid:
        found = identify_pid(pv, sp, out, timebase_s)
        if not found["fitting"]["able_to_identify"] or found["kp"] is None:
            raise ValueError("closed-loop identification needs PID parameters and they could not be identified; "
                             "give pid={'kp':..., 'ti_s':...}")
        pid = {"kp": found["kp"], "ti_s": found["ti_s"] or 0.0, "td_s": found["td_s"] or 0.0}
        pid_source = "identified from the same data"
    ds = _dataset(dynamic, Array, Double, timebase_s, pv, [out], sp)
    params = dynamic.PidParameters()
    params.Kp = float(pid["kp"])
    params.Ti_s = float(pid.get("ti_s", 0.0))
    params.Td_s = float(pid.get("td_s", 0.0))
    handling = (dynamic.BadIndicesHandlingEnum.Internal_DetectBadDataAndFrozenData if detect_frozen
                else dynamic.BadIndicesHandlingEnum.Internal_DetectBadData)
    result = dynamic.ClosedLoopUnitIdentifier().Identify(ds, params, handling, 0)
    model, disturbance = result.Item1, result.Item2
    d = np.array([float(v) for v in disturbance], dtype=float) if disturbance is not None else np.array([])
    d[d == BAD_DATA_ID] = np.nan
    valid = d[np.isfinite(d)]
    out_params = _unit_parameters(model, ["controller_output"])
    out_params["pid_used"] = dict(pid, source=pid_source)
    out_params["disturbance"] = {
        "std": float(np.std(valid)) if len(valid) else None,
        "p05": float(np.percentile(valid, 5)) if len(valid) else None,
        "p95": float(np.percentile(valid, 95)) if len(valid) else None,
    }
    out_params["disturbance_series"] = [None if not math.isfinite(v) else float(v) for v in d]
    return out_params
