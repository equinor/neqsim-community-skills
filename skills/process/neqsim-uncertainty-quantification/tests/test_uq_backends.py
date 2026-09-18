from __future__ import annotations

import math

import pytest

from uncertainty_quantification import backends
from uncertainty_quantification.distributions import Triangular, Uniform

PARAMETERS = [
    Uniform(name="x1", low=-math.pi, high=math.pi),
    Uniform(name="x2", low=-math.pi, high=math.pi),
    Uniform(name="x3", low=-math.pi, high=math.pi),
]

salib_required = pytest.mark.skipif(
    not backends.salib_available(), reason="SALib is an optional backend"
)
chaospy_required = pytest.mark.skipif(
    not backends.chaospy_available(), reason="chaospy is an optional backend"
)


def ishigami(values):
    x1, x2, x3 = values["x1"], values["x2"], values["x3"]
    return math.sin(x1) + 7.0 * math.sin(x2) ** 2 + 0.1 * x3**4 * math.sin(x1)


def test_availability_checks_never_raise():
    assert isinstance(backends.salib_available(), bool)
    assert isinstance(backends.chaospy_available(), bool)


def test_unit_problem_is_uniform_in_every_dimension():
    problem = backends.unit_problem(PARAMETERS)
    assert problem["num_vars"] == 3
    assert problem["names"] == ["x1", "x2", "x3"]
    assert problem["bounds"] == [[0.0, 1.0]] * 3


def test_unit_points_are_mapped_through_the_marginals_not_used_raw():
    parameters = [Triangular(name="p", low=0.0, base_value=0.3, high=1.0)]
    values = backends.to_parameter_values(parameters, [0.5])
    assert values["p"] == pytest.approx(parameters[0].ppf(0.5))
    assert values["p"] != pytest.approx(0.5)


def test_missing_salib_raises_with_an_install_hint():
    if backends.salib_available():
        pytest.skip("SALib is installed; the unavailable path cannot be exercised")
    with pytest.raises(backends.BackendUnavailableError) as excinfo:
        backends.saltelli_samples(PARAMETERS, 8)
    assert "pip install SALib" in str(excinfo.value)


def test_missing_chaospy_raises_with_an_install_hint():
    if backends.chaospy_available():
        pytest.skip("chaospy is installed; the unavailable path cannot be exercised")
    with pytest.raises(backends.BackendUnavailableError) as excinfo:
        backends.fit_polynomial_chaos(PARAMETERS, ishigami)
    assert "pip install chaospy" in str(excinfo.value)


@salib_required
def test_saltelli_design_has_the_documented_evaluation_count():
    design = backends.saltelli_samples(PARAMETERS, 16, seed=1)
    assert len(design) == 16 * (len(PARAMETERS) + 2)
    assert set(design[0]) == {"x1", "x2", "x3"}


@salib_required
def test_sobol_indices_recover_the_analytical_ishigami_values():
    design = backends.saltelli_samples(PARAMETERS, 1024, seed=42)
    outputs = [ishigami(point) for point in design]
    indices = backends.sobol_indices(PARAMETERS, outputs)
    # Analytical: S1 = [0.3139, 0.4424, 0.0], ST[x3] = 0.2437.
    assert indices["S1"][0] == pytest.approx(0.3139, abs=0.06)
    assert indices["S1"][1] == pytest.approx(0.4424, abs=0.06)
    assert indices["S1"][2] == pytest.approx(0.0, abs=0.06)
    assert indices["ST"][2] == pytest.approx(0.2437, abs=0.06)


@salib_required
def test_sobol_reveals_an_interaction_a_tornado_cannot_see():
    design = backends.saltelli_samples(PARAMETERS, 1024, seed=42)
    outputs = [ishigami(point) for point in design]
    indices = backends.sobol_indices(PARAMETERS, outputs)
    assert indices["ST"][2] > 10.0 * max(indices["S1"][2], 1e-3)


@salib_required
def test_morris_screening_ranks_the_influential_parameters():
    result = backends.morris_screening(PARAMETERS, ishigami, trajectories=20, seed=3)
    assert result["parameters"] == ["x1", "x2", "x3"]
    assert result["evaluations"] > 0
    assert max(result["mu_star"]) > 0.0


@chaospy_required
def test_polynomial_chaos_recovers_the_ishigami_mean_cheaply():
    fit = backends.fit_polynomial_chaos(PARAMETERS, ishigami, order=6, seed=42)
    assert fit["mean"] == pytest.approx(3.5, abs=0.1)
    assert fit["std"] == pytest.approx(3.72, abs=0.3)


@chaospy_required
def test_surrogate_sampling_reproduces_the_surrogate_mean():
    fit = backends.fit_polynomial_chaos(PARAMETERS, ishigami, order=6, seed=42)
    sample = backends.sample_surrogate(fit, 20000, seed=7)
    assert sum(sample) / len(sample) == pytest.approx(fit["mean"], abs=0.2)
