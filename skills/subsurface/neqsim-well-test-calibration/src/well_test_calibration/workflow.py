"""Per-well calibration over its recent tests with a held-out acceptance check."""

from __future__ import annotations

from collections.abc import Callable, Sequence

import numpy as np

from .fit import fit_with_priors
from .gate import accept_calibration


def calibrate_well(cases: list[dict], predict: Callable[[dict, Sequence[float]], dict[str, float]],
                   prior: Sequence[float], prior_std: Sequence[float], bounds: Sequence[Sequence[float]],
                   sigma: dict[str, float], steps: Sequence[float] = None, iters: int = 4) -> dict[str, object]:
    """Fit the lift-model parameters of one well to its clean tests and decide whether to use them.

    ``cases``: one dict per test, oldest first, with measured observations (for example ``{"wht": 61.2, "dp": 145.0}``;
    use None for a missing one) and whatever ``predict`` needs. ``predict(case, theta)`` returns the model values for
    the same keys. ``sigma``: measurement standard deviation per key. The latest test is held out: the parameters are
    refitted without it and its error is compared with the prior's (``accept_calibration``). The final parameters use
    all tests.
    """
    keys = sorted(sigma)

    def residuals_for(subset):
        def fn(theta):
            r = []
            for c in subset:
                m = predict(c, theta)
                for k in keys:
                    if c.get(k) is not None and m.get(k) is not None:
                        r.append((m[k] - c[k]) / sigma[k])
            return np.array(r, dtype=float)
        return fn

    full = fit_with_priors(residuals_for(cases), prior, prior_std, bounds, steps, iters)
    validation = {}
    if len(cases) >= 2:
        held = fit_with_priors(residuals_for(cases[:-1]), prior, prior_std, bounds, steps, iters)
        last = cases[-1]
        mt, mp = predict(last, held.theta), predict(last, list(prior))
        for k in keys:
            if last.get(k) is not None and mt.get(k) is not None and mp.get(k) is not None:
                validation[k] = {"tuned": abs(mt[k] - last[k]), "prior": abs(mp[k] - last[k])}
    if validation:
        tuned = sum(v["tuned"] / sigma[k] for k, v in validation.items())
        prior_err = sum(v["prior"] / sigma[k] for k, v in validation.items())
    else:
        tuned = prior_err = None
    gate = accept_calibration(tuned, prior_err, full.identifiable, len(cases))
    return {"theta": full.theta if gate["accept"] else list(prior), "theta_fitted": full.theta, "accept": gate["accept"],
            "reason": gate["reason"], "identifiable": full.identifiable, "singular_values": full.singular_values,
            "objective": full.objective, "validation": validation, "n_tests": len(cases), "notes": full.notes}
