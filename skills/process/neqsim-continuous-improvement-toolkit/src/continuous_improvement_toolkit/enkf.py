"""Ensemble Kalman parameter update and identifiability check (numpy only).

``enkf_update`` corrects an ensemble of model parameters with one set of measurements, given
the model predictions for each ensemble member (for example from NeqSim runs). The Java
``EnKFParameterEstimator`` does the same inside NeqSim; this helper is for stage scripts that
run the model themselves.

``identifiability`` tells, from a sensitivity (Jacobian) matrix, which parameters the
measurements can determine - calibrating an unidentifiable parameter only moves noise.
"""

import numpy as np


def enkf_update(ensemble, predictions, observations, obs_std, seed=0):
    """Return the updated ensemble (members x parameters).

    :param ensemble: array (N, p) of parameter samples
    :param predictions: array (N, m) of model predictions for each member
    :param observations: array (m,) of measured values
    :param obs_std: scalar or array (m,) of measurement standard deviations
    """
    x = np.atleast_2d(np.asarray(ensemble, dtype=float))
    h = np.atleast_2d(np.asarray(predictions, dtype=float))
    d = np.asarray(observations, dtype=float).ravel()
    n = x.shape[0]
    if h.shape[0] != n:
        raise ValueError("ensemble and predictions need the same number of members")
    r = np.diag(np.broadcast_to(np.asarray(obs_std, dtype=float), d.shape) ** 2)
    xa, ha = x - x.mean(axis=0), h - h.mean(axis=0)
    cxh = xa.T @ ha / (n - 1)
    chh = ha.T @ ha / (n - 1)
    gain = cxh @ np.linalg.inv(chh + r)
    rng = np.random.default_rng(seed)
    perturbed = d + rng.multivariate_normal(np.zeros(len(d)), r, size=n)
    return x + (perturbed - h) @ gain.T


def identifiability(jacobian, names=None, parameter_scale=None, rel_tol=1e-3):
    """Singular-value identifiability report of a sensitivity matrix (measurements x parameters)."""
    j = np.atleast_2d(np.asarray(jacobian, dtype=float))
    if parameter_scale is not None:
        j = j * np.asarray(parameter_scale, dtype=float)
    names = list(names) if names else ["p{}".format(i) for i in range(j.shape[1])]
    u, s, vt = np.linalg.svd(j, full_matrices=False)
    tol = rel_tol * (s[0] if len(s) else 0.0)
    rank = int(np.sum(s > tol))
    weak = []
    for i in range(rank, len(s)):
        direction = vt[i]
        weak.append({n: round(float(c), 3) for n, c in zip(names, direction) if abs(c) > 0.2})
    column_norm = np.linalg.norm(j, axis=0)
    return {"singular_values": s.tolist(),
            "condition_number": float(s[0] / s[-1]) if len(s) and s[-1] > 0 else float("inf"),
            "rank": rank, "n_parameters": j.shape[1],
            "identifiable": rank == j.shape[1],
            "unidentifiable_directions": weak,
            "sensitivity_norm": {n: float(v) for n, v in zip(names, column_norm)}}
