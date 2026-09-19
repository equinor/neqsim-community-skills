from __future__ import annotations

import pytest

from uncertainty_quantification.sampling import (
    SamplingError,
    available_samplers,
    generate_unit_samples,
    halton,
    latin_hypercube,
    random_samples,
)


@pytest.mark.parametrize("method", ["random", "lhs", "halton"])
def test_every_sampler_returns_the_requested_shape(method):
    points = generate_unit_samples(20, 3, method, seed=1)
    assert len(points) == 20
    assert all(len(p) == 3 for p in points)


@pytest.mark.parametrize("method", ["random", "lhs", "halton"])
def test_every_sample_lies_in_the_unit_hypercube(method):
    for point in generate_unit_samples(50, 4, method, seed=7):
        assert all(0.0 <= c < 1.0 for c in point)


@pytest.mark.parametrize("method", ["random", "lhs", "halton"])
def test_sampling_is_reproducible_for_a_fixed_seed(method):
    assert generate_unit_samples(10, 2, method, seed=3) == generate_unit_samples(
        10, 2, method, seed=3
    )


def test_different_seeds_give_different_samples():
    assert random_samples(10, 2, seed=1) != random_samples(10, 2, seed=2)


def test_latin_hypercube_puts_exactly_one_point_in_each_stratum():
    n = 25
    for column in zip(*latin_hypercube(n, 3, seed=5)):
        strata = sorted(int(value * n) for value in column)
        assert strata == list(range(n))


def test_latin_hypercube_beats_random_on_marginal_coverage():
    n = 40
    lhs_mean = sum(p[0] for p in latin_hypercube(n, 1, seed=11)) / n
    random_mean = sum(p[0] for p in random_samples(n, 1, seed=11)) / n
    assert abs(lhs_mean - 0.5) < abs(random_mean - 0.5)


def test_halton_is_deterministic_and_starts_after_the_skip():
    first = halton(3, 2, skip=20)
    assert first == halton(3, 2, skip=20)
    assert first != halton(3, 2, skip=0)


def test_halton_first_dimension_is_the_van_der_corput_sequence():
    points = halton(4, 1, skip=1)
    assert [p[0] for p in points] == pytest.approx([0.5, 0.25, 0.75, 0.125])


def test_halton_refuses_more_dimensions_than_it_has_primes():
    with pytest.raises(SamplingError):
        halton(5, 200)


def test_unknown_sampler_lists_the_available_ones():
    with pytest.raises(SamplingError) as excinfo:
        generate_unit_samples(5, 2, "sobol")
    assert "lhs" in str(excinfo.value)


def test_non_positive_size_is_rejected():
    with pytest.raises(SamplingError):
        generate_unit_samples(0, 2, "lhs")
    with pytest.raises(SamplingError):
        generate_unit_samples(5, 0, "lhs")


def test_available_samplers_is_the_registry():
    assert available_samplers() == ["halton", "lhs", "random"]
