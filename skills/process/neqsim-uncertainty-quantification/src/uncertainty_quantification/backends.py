"""Optional SALib and chaospy backends.

Neither is a hard dependency. The dependency-free core already gives Latin
hypercube sampling, percentiles and a one-at-a-time tornado; these backends add
what a hand-rolled study cannot do:

* **SALib** — Saltelli sampling and variance-based Sobol' indices. A tornado
  ranks parameters one at a time and is blind to interaction; Sobol' separates
  first-order from total-order effect, so an interaction shows up as
  ``ST >> S1``.
* **chaospy** — polynomial chaos expansion. Fits a surrogate from a small
  designed sample, then reads mean, variance and Sobol' indices off the
  coefficients, typically at one to two orders of magnitude fewer model
  evaluations than direct Monte Carlo.

Both are driven in **unit space**: SALib and chaospy see uniform ``[0, 1]``
inputs and each marginal is applied through its own inverse CDF. That keeps the
sampler independent of the marginals and avoids silently replacing a triangular
input with a uniform one.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Sequence

from .distributions import Distribution

SALIB_INSTALL_HINT = "python -m pip install SALib"
CHAOSPY_INSTALL_HINT = "python -m pip install chaospy"


class BackendUnavailableError(RuntimeError):
    """Raised when an optional backend is requested but not installed."""


def _try_import(module_name: str):
    try:
        return __import__(module_name)
    except ImportError:
        return None


def salib_available() -> bool:
    """True when SALib can be imported."""
    return _try_import("SALib") is not None


def chaospy_available() -> bool:
    """True when chaospy can be imported."""
    return _try_import("chaospy") is not None


def unit_problem(parameters: Sequence[Distribution]) -> Dict[str, Any]:
    """SALib problem definition in unit space, one uniform per parameter."""
    return {
        "num_vars": len(parameters),
        "names": [p.name for p in parameters],
        "bounds": [[0.0, 1.0] for _ in parameters],
    }


def to_parameter_values(
    parameters: Sequence[Distribution], unit_point: Sequence[float]
) -> Dict[str, float]:
    """Map one unit-space point onto engineering values through the marginals."""
    return {
        parameter.name: parameter.ppf(float(coordinate))
        for parameter, coordinate in zip(parameters, unit_point)
    }


def saltelli_samples(
    parameters: Sequence[Distribution],
    n: int,
    calc_second_order: bool = False,
    seed: Optional[int] = None,
) -> List[Dict[str, float]]:
    """Saltelli design mapped onto engineering values.

    The evaluation count is ``n * (num_vars + 2)`` without second-order terms,
    and ``n * (2 * num_vars + 2)`` with them. Budget for that before running a
    NeqSim model on it.
    """
    salib = _try_import("SALib")
    if salib is None:
        raise BackendUnavailableError(
            "SALib is not installed — {}".format(SALIB_INSTALL_HINT)
        )
    from SALib.sample import sobol as sobol_sample  # type: ignore

    problem = unit_problem(parameters)
    design = sobol_sample.sample(
        problem, n, calc_second_order=calc_second_order, seed=seed
    )
    return [to_parameter_values(parameters, row) for row in design]


def sobol_indices(
    parameters: Sequence[Distribution],
    outputs: Sequence[float],
    calc_second_order: bool = False,
) -> Dict[str, Any]:
    """Variance-based Sobol' indices from outputs of a Saltelli design.

    ``outputs`` must be in the order produced by :func:`saltelli_samples`.
    Returns first-order ``S1`` and total-order ``ST`` per parameter, plus their
    confidence intervals.
    """
    salib = _try_import("SALib")
    if salib is None:
        raise BackendUnavailableError(
            "SALib is not installed — {}".format(SALIB_INSTALL_HINT)
        )
    import numpy as np  # type: ignore
    from SALib.analyze import sobol as sobol_analyze  # type: ignore

    problem = unit_problem(parameters)
    analysis = sobol_analyze.analyze(
        problem, np.asarray(outputs, dtype=float), calc_second_order=calc_second_order
    )
    return {
        "method": "Sobol (SALib)",
        "parameters": [p.name for p in parameters],
        "S1": [float(v) for v in analysis["S1"]],
        "S1_conf": [float(v) for v in analysis["S1_conf"]],
        "ST": [float(v) for v in analysis["ST"]],
        "ST_conf": [float(v) for v in analysis["ST_conf"]],
    }


def morris_screening(
    parameters: Sequence[Distribution],
    model: Callable[[Dict[str, float]], float],
    trajectories: int = 10,
    levels: int = 4,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """Morris elementary-effects screening — cheap ranking for many parameters.

    Use it to decide which parameters are worth a full Sobol' or Monte Carlo
    budget; it separates negligible from influential, not first from total order.
    """
    salib = _try_import("SALib")
    if salib is None:
        raise BackendUnavailableError(
            "SALib is not installed — {}".format(SALIB_INSTALL_HINT)
        )
    import numpy as np  # type: ignore
    from SALib.analyze import morris as morris_analyze  # type: ignore
    from SALib.sample import morris as morris_sample  # type: ignore

    problem = unit_problem(parameters)
    design = morris_sample.sample(
        problem, trajectories, num_levels=levels, seed=seed
    )
    outputs = np.asarray(
        [model(to_parameter_values(parameters, row)) for row in design], dtype=float
    )
    analysis = morris_analyze.analyze(problem, design, outputs, num_levels=levels)
    return {
        "method": "Morris elementary effects (SALib)",
        "parameters": list(analysis["names"]),
        "mu_star": [float(v) for v in analysis["mu_star"]],
        "sigma": [float(v) for v in analysis["sigma"]],
        "evaluations": int(design.shape[0]),
    }


def fit_polynomial_chaos(
    parameters: Sequence[Distribution],
    model: Callable[[Dict[str, float]], float],
    order: int = 3,
    samples: Optional[int] = None,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """Fit a polynomial chaos surrogate in unit space and read statistics off it.

    Returns the surrogate, the joint distribution, mean, standard deviation, and
    first-order Sobol' indices, plus the number of model evaluations used.
    """
    chaospy = _try_import("chaospy")
    if chaospy is None:
        raise BackendUnavailableError(
            "chaospy is not installed — {}".format(CHAOSPY_INSTALL_HINT)
        )
    import chaospy as cp  # type: ignore
    import numpy as np  # type: ignore

    joint = cp.J(*[cp.Uniform(0.0, 1.0) for _ in parameters])
    expansion = cp.generate_expansion(order, joint)
    count = samples if samples is not None else 2 * len(expansion)
    design = joint.sample(count, rule="sobol", seed=seed) if seed is not None else joint.sample(
        count, rule="sobol"
    )
    design = np.atleast_2d(design)
    evaluations = np.asarray(
        [model(to_parameter_values(parameters, design[:, i])) for i in range(design.shape[1])],
        dtype=float,
    )
    surrogate = cp.fit_regression(expansion, design, evaluations)
    return {
        "method": "Polynomial chaos expansion (chaospy)",
        "order": order,
        "evaluations": int(design.shape[1]),
        "surrogate": surrogate,
        "joint": joint,
        "mean": float(cp.E(surrogate, joint)),
        "std": float(cp.Std(surrogate, joint)),
        "parameters": [p.name for p in parameters],
        "S1": [float(v) for v in np.atleast_1d(cp.Sens_m(surrogate, joint))],
    }


def sample_surrogate(
    fit: Dict[str, Any], n: int = 100000, seed: Optional[int] = None
) -> List[float]:
    """Draw a large cheap sample from a fitted polynomial chaos surrogate.

    This is where the saving appears: percentiles come from a huge surrogate
    sample while the true model was evaluated only ``fit["evaluations"]`` times.
    """
    chaospy = _try_import("chaospy")
    if chaospy is None:
        raise BackendUnavailableError(
            "chaospy is not installed — {}".format(CHAOSPY_INSTALL_HINT)
        )
    import numpy as np  # type: ignore

    joint = fit["joint"]
    design = np.atleast_2d(joint.sample(n, rule="random", seed=seed) if seed is not None else joint.sample(n, rule="random"))
    return [float(v) for v in np.atleast_1d(fit["surrogate"](*design))]
