"""Gaussian-process Bayesian optimisation with expected improvement (numpy only).

For solve stages that tune a few bounded setpoints on an expensive NeqSim model: fit a GP to
the trials evaluated so far, then propose the candidate with the largest expected improvement.
The expected improvement is also what the stop rule needs as ``predicted_delta``.
"""

import math

import numpy as np


def _kernel(a, b, length, variance):
    d = (a[:, None, :] - b[None, :, :]) / length
    return variance * np.exp(-0.5 * np.sum(d * d, axis=2))


def fit_gp(x, y, bounds, length=0.3, noise=1e-6):
    """Fit a zero-mean GP on inputs scaled to the unit cube; returns a predict function."""
    x = np.atleast_2d(np.asarray(x, dtype=float))
    y = np.asarray(y, dtype=float).ravel()
    lo, hi = np.asarray(bounds, dtype=float).T
    span = np.where(hi > lo, hi - lo, 1.0)
    xs = (x - lo) / span
    mean, scale = float(np.mean(y)), float(np.std(y)) or 1.0
    ys = (y - mean) / scale
    k = _kernel(xs, xs, length, 1.0) + noise * np.eye(len(xs))
    chol = np.linalg.cholesky(k)
    alpha = np.linalg.solve(chol.T, np.linalg.solve(chol, ys))

    def predict(points):
        p = (np.atleast_2d(np.asarray(points, dtype=float)) - lo) / span
        ks = _kernel(p, xs, length, 1.0)
        mu = ks @ alpha
        v = np.linalg.solve(chol, ks.T)
        var = np.clip(1.0 - np.sum(v * v, axis=0), 1e-12, None)
        return mean + scale * mu, scale * np.sqrt(var)

    return predict


def expected_improvement(mu, sigma, best, maximize=True, xi=0.0):
    """Expected improvement of normal predictions over ``best``."""
    mu, sigma = np.asarray(mu, dtype=float), np.asarray(sigma, dtype=float)
    gain = (mu - best - xi) if maximize else (best - mu - xi)
    z = gain / sigma
    cdf = 0.5 * (1.0 + np.vectorize(math.erf)(z / math.sqrt(2.0)))
    pdf = np.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)
    return gain * cdf + sigma * pdf


def propose_next(x, y, bounds, maximize=True, n_candidates=2000, seed=0, length=0.3):
    """Return ``{"x": [...], "expected_improvement": ei, "predicted": mu}`` for the next trial."""
    rng = np.random.default_rng(seed)
    lo, hi = np.asarray(bounds, dtype=float).T
    candidates = lo + (hi - lo) * rng.random((int(n_candidates), len(lo)))
    predict = fit_gp(x, y, bounds, length=length)
    mu, sigma = predict(candidates)
    best = float(np.max(y) if maximize else np.min(y))
    ei = expected_improvement(mu, sigma, best, maximize)
    i = int(np.argmax(ei))
    return {"x": candidates[i].tolist(), "expected_improvement": float(ei[i]),
            "predicted": float(mu[i]), "predicted_std": float(sigma[i]), "best_so_far": best}
