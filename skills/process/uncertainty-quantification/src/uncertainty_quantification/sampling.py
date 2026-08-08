"""Samplers producing points in the unit hypercube.

Each sampler returns ``n`` points of dimension ``dim`` with every coordinate in
``[0, 1)``. Marginals are applied afterwards through each distribution's inverse
CDF, so the choice of sampler is independent of the choice of distribution.

Latin hypercube and Halton both reduce the variance of a Monte Carlo estimate
relative to plain pseudo-random sampling, which matters when a single sample is
a full NeqSim flowsheet solve. True Sobol' / Saltelli sequences are delegated to
the optional SALib backend.
"""

from __future__ import annotations

import random
from typing import Callable, Dict, List, Optional, Sequence

Sample = List[float]

_PRIMES: Sequence[int] = (
    2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47, 53, 59, 61, 67, 71,
    73, 79, 83, 89, 97, 101, 103, 107, 109, 113,
)


class SamplingError(ValueError):
    """Raised for an unusable sampler request."""


def _check(n: int, dim: int) -> None:
    if n <= 0:
        raise SamplingError("n must be positive, got {}".format(n))
    if dim <= 0:
        raise SamplingError("dim must be positive, got {}".format(dim))


def random_samples(n: int, dim: int, seed: Optional[int] = None) -> List[Sample]:
    """Plain seeded pseudo-random sampling."""
    _check(n, dim)
    rng = random.Random(seed)
    return [[rng.random() for _ in range(dim)] for _ in range(n)]


def latin_hypercube(n: int, dim: int, seed: Optional[int] = None) -> List[Sample]:
    """Latin hypercube: one sample per stratum in every dimension.

    Guarantees the marginal of each input is covered evenly, which removes the
    clustering that makes a small pseudo-random Monte Carlo run unrepresentative.
    """
    _check(n, dim)
    rng = random.Random(seed)
    columns: List[List[float]] = []
    for _ in range(dim):
        strata = [(i + rng.random()) / n for i in range(n)]
        rng.shuffle(strata)
        columns.append(strata)
    return [[columns[d][i] for d in range(dim)] for i in range(n)]


def _radical_inverse(index: int, base: int) -> float:
    result = 0.0
    fraction = 1.0 / base
    while index > 0:
        index, digit = divmod(index, base)
        result += digit * fraction
        fraction /= base
    return result


def halton(n: int, dim: int, seed: Optional[int] = None, skip: int = 20) -> List[Sample]:
    """Deterministic low-discrepancy Halton sequence.

    ``seed`` shifts the start of the sequence so repeated studies can be varied;
    the sequence itself is deterministic. Correlation between the higher prime
    bases degrades the sequence above roughly ten dimensions — prefer Latin
    hypercube or the SALib backend beyond that.
    """
    _check(n, dim)
    if dim > len(_PRIMES):
        raise SamplingError(
            "halton supports up to {} dimensions, got {}".format(len(_PRIMES), dim)
        )
    offset = skip + (int(seed) if seed is not None else 0)
    return [
        [_radical_inverse(offset + i, _PRIMES[d]) for d in range(dim)] for i in range(n)
    ]


SAMPLERS: Dict[str, Callable[..., List[Sample]]] = {
    "random": random_samples,
    "lhs": latin_hypercube,
    "halton": halton,
}

#: Sampler used when a study does not choose one.
DEFAULT_SAMPLER = "lhs"


def available_samplers() -> List[str]:
    """Names accepted by :func:`generate_unit_samples`."""
    return sorted(SAMPLERS)


def generate_unit_samples(
    n: int, dim: int, method: str = DEFAULT_SAMPLER, seed: Optional[int] = None
) -> List[Sample]:
    """Generate ``n`` unit-hypercube points with the named sampler."""
    key = method.strip().lower()
    if key not in SAMPLERS:
        raise SamplingError(
            "unknown sampler '{}' — available: {}".format(
                method, ", ".join(available_samplers())
            )
        )
    return SAMPLERS[key](n, dim, seed)
