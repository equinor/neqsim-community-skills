"""Advisory production loop: NeqSim/flowsheet sensitivities plan the moves, identified dynamics pace and verify them.

Lessons built in (from a full-plant replay where the plan matched full-model verification within 2 Sm3/d per day):

* ``response_time`` - first-order-plus-delay fits can trade lag for delay; the sum (delay + tau) is the robust quantity.
* ``gain_update`` - accept an identified gain only with enough moves, a good fit, a small uncertainty and a ratio to the
  physics gain inside a band; single moves and weak signals gave wrong updates.
* ``physics_gate`` - reject a model response with the wrong sign or more output than was fed in (solver branch jumps).
* ``sensitivity_matrix`` / ``plan_moves`` - linear plan from per-lever flowsheet cases; constraints already exceeded may
  not get worse; returns the binding constraints.
* ``schedule_moves`` - one step at a time, best first, spaced by the identified settling time.
* ``linear_soft_sensor`` - model sensitivities applied to measured inputs where the output itself is not measured.

Only numpy and pandas are needed; ``plan_moves`` uses SciPy (``pip install scipy``) when called.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Mapping, Optional, Tuple

import numpy as np
import pandas as pd


def response_time(model: Mapping[str, object]) -> Dict[str, float]:
    """63 % and 95 % response times (s) of an identified first-order-plus-delay model (``identify_unit`` output)."""
    tau = float(model.get("time_constant_s") or 0.0)
    delay = float(model.get("time_delay_s") or 0.0)
    return {
        "t63_s": delay + tau,
        "t95_s": delay + 3.0 * tau,
        "tau_s": tau,
        "delay_s": delay,
    }


def gain_update(
    identified: float,
    physics: float,
    n_moves: int,
    fit_pct: Optional[float],
    uncertainty: Optional[float] = None,
    min_moves: int = 2,
    min_fit_pct: float = 50.0,
    max_rel_uncertainty: float = 0.3,
    band: Tuple[float, float] = (0.5, 2.0),
    tolerance: float = 0.10,
) -> Dict[str, object]:
    """Decide whether an identified gain should replace the physics (planning) gain.

    Returns ``accept``, the gain to use and the reason. The physics gain is kept unless the evidence is strong:
    at least ``min_moves`` moves of the lever, fit at least ``min_fit_pct``, relative uncertainty at most
    ``max_rel_uncertainty`` (when given), ratio identified/physics inside ``band`` and different by more than
    ``tolerance``.
    """
    if n_moves < min_moves:
        return {
            "accept": False,
            "gain": physics,
            "reason": f"only {n_moves} move(s); need {min_moves}",
        }
    if fit_pct is None or not np.isfinite(fit_pct) or fit_pct < min_fit_pct:
        return {
            "accept": False,
            "gain": physics,
            "reason": f"fit {fit_pct} % below {min_fit_pct} %",
        }
    if (
        uncertainty is not None
        and identified != 0
        and abs(uncertainty / identified) > max_rel_uncertainty
    ):
        return {
            "accept": False,
            "gain": physics,
            "reason": f"gain uncertainty {abs(uncertainty / identified):.0%} too large",
        }
    if physics == 0:
        return {
            "accept": False,
            "gain": physics,
            "reason": "physics gain is zero; review the model before using data",
        }
    ratio = identified / physics
    if not band[0] <= ratio <= band[1]:
        return {
            "accept": False,
            "gain": physics,
            "reason": f"ratio {ratio:.2f} outside {band}: check model or confounding",
        }
    if abs(ratio - 1.0) <= tolerance:
        return {
            "accept": False,
            "gain": physics,
            "reason": f"ratio {ratio:.2f} within tolerance; physics confirmed",
        }
    return {
        "accept": True,
        "gain": identified,
        "reason": f"ratio {ratio:.2f} from {n_moves} moves, fit {fit_pct:.0f} %",
    }


def physics_gate(
    d_output: float,
    d_input: float,
    max_ratio: float = 1.5,
    require_same_sign: bool = True,
) -> Tuple[bool, str]:
    """Reject a model response that is not physically possible.

    ``d_input`` is what was added at the source (for example oil added at the wells) and ``d_output`` the model's
    change at the product (export oil). A wrong sign or more than ``max_ratio`` times the input marks a solver branch
    jump or an inconsistent case.
    """
    if d_input == 0:
        return (abs(d_output) < 1e-9, "no input change")
    if require_same_sign and np.sign(d_output) != np.sign(d_input):
        return False, f"wrong sign: {d_output:+.4g} for input {d_input:+.4g}"
    if abs(d_output) > max_ratio * abs(d_input):
        return False, f"output {abs(d_output / d_input):.1f}x the input"
    return True, "ok"


def sensitivity_matrix(
    base: Mapping[str, float],
    cases: Mapping[str, Tuple[float, Mapping[str, float]]],
    keys: Optional[Iterable[str]] = None,
) -> Dict[str, Dict[str, float]]:
    """Per-unit sensitivities from one-at-a-time flowsheet cases.

    ``cases`` maps lever -> (step, result) where result holds the same keys as ``base``. Keys missing from a case are
    taken as unchanged.
    """
    ks = list(keys) if keys is not None else list(base)
    return {
        lv: {k: (res.get(k, base[k]) - base[k]) / float(step) for k in ks}
        for lv, (step, res) in cases.items()
    }


def plan_moves(
    gains: Mapping[str, Mapping[str, float]],
    state: Mapping[str, float],
    objective: Mapping[str, float],
    limits: Mapping[str, float],
    bounds: Mapping[str, Tuple[float, float]],
) -> Dict[str, object]:
    """Best lever moves within limits (linear programme on the sensitivity matrix).

    ``objective`` weights keys of the gains (for example ``{"oil": 1, "gas": 0.001}``); ``limits`` gives upper limits
    on keys of ``state`` (for example equipment loads in %). A limit already exceeded becomes "no worse than now".
    Returns the moves, predicted state and the binding constraints. Needs SciPy.
    """
    from scipy.optimize import linprog

    levers = list(gains)
    c = [-sum(w * gains[lv].get(k, 0.0) for k, w in objective.items()) for lv in levers]
    rows, rhs, names = [], [], []
    for k, lim in limits.items():
        rows.append([gains[lv].get(k, 0.0) for lv in levers])
        rhs.append(max(lim, state[k]) - state[k])
        names.append(k)
    res = linprog(
        c,
        A_ub=rows or None,
        b_ub=rhs or None,
        bounds=[bounds[lv] for lv in levers],
        method="highs",
    )
    x = dict(zip(levers, res.x)) if res.success else {lv: 0.0 for lv in levers}
    pred = {
        k: state[k] + sum(gains[lv].get(k, 0.0) * x[lv] for lv in levers) for k in state
    }
    binding = [
        k
        for k, r, b in zip(names, rows, rhs)
        if b - sum(a * x[lv] for a, lv in zip(r, levers)) < 1e-6
    ]
    return {
        "moves": x,
        "objective_gain": float(-res.fun) if res.success else 0.0,
        "predicted": pred,
        "binding": binding,
        "status": res.message,
    }


def schedule_moves(
    moves: Mapping[str, float],
    value_per_unit: Mapping[str, float],
    max_step: float,
    settle_s: float,
    start_s: float = 0.0,
) -> List[Dict[str, float]]:
    """Split planned moves into steps of at most ``max_step``, largest value first, one every ``settle_s`` seconds."""
    steps = []
    for lv in sorted(moves, key=lambda q: -abs(value_per_unit.get(q, 0.0))):
        rem = float(moves[lv])
        while abs(rem) > 1e-9:
            st = float(np.sign(rem) * min(max_step, abs(rem)))
            steps.append({"lever": lv, "step": st})
            rem -= st
    for i, s in enumerate(steps):
        s["time_s"] = start_s + i * settle_s
    return steps


def linear_soft_sensor(
    anchor_value: float,
    anchor_inputs: Mapping[str, float],
    sensitivities: Mapping[str, float],
    measured: pd.DataFrame,
) -> pd.Series:
    """Estimate an unmeasured output from measured inputs: anchor + sum(sensitivity_i * (input_i - anchor_i)).

    Use model (for example NeqSim) sensitivities around an anchor operating point; re-anchor when composition or
    line-up changes. ``measured`` has one column per input name.
    """
    out = pd.Series(float(anchor_value), index=measured.index)
    for k, s in sensitivities.items():
        out = out + float(s) * (measured[k] - float(anchor_inputs[k]))
    return out
