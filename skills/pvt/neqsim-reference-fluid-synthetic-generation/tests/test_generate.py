import pytest

from reference_fluid import (
    blend_compositions,
    generate_fluid_cases,
    match_split_factor,
)


def test_match_split_factor_finds_minimum():
    # Objective minimized at factor = 1.3 (a quadratic bowl).
    result = match_split_factor(lambda a: (a - 1.3) ** 2, low=0.5, high=3.0, tol=1e-5)
    assert result.converged
    assert result.factor == pytest.approx(1.3, abs=1e-3)
    assert result.objective == pytest.approx(0.0, abs=1e-6)


def test_match_split_factor_matches_target_scalar():
    # Forward model: predicted saturation pressure increases with the factor.
    def predicted_psat(alpha):
        return 150.0 + 40.0 * (alpha - 1.0)

    measured_psat = 170.0

    def objective(alpha):
        rel = (predicted_psat(alpha) - measured_psat) / measured_psat
        return rel * rel

    result = match_split_factor(objective, low=0.5, high=2.5, tol=1e-6)
    assert result.factor == pytest.approx(1.5, abs=1e-3)


def test_generate_fluid_cases():
    def builder(alpha):
        # Heavier tail as alpha decreases (toy builder).
        heavy = 0.05 / alpha
        return {"methane": 1.0 - heavy, "C7plus": heavy}

    cases = generate_fluid_cases([0.8, 1.0, 1.2], builder)
    assert len(cases) == 3
    assert cases[0]["C7plus"] > cases[2]["C7plus"]


def test_blend_compositions_by_molar_rate():
    well_a = {"methane": 0.90, "ethane": 0.10}
    well_b = {"methane": 0.60, "ethane": 0.40}
    result = blend_compositions([(3000.0, well_a), (1000.0, well_b)])
    assert result.total_molar_rate == pytest.approx(4000.0)
    assert sum(result.composition.values()) == pytest.approx(1.0)
    # 3:1 weighting -> methane between the two, closer to well A.
    assert result.composition["methane"] == pytest.approx(0.825, abs=1e-6)
    assert result.weights == (0.75, 0.25)


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        match_split_factor(lambda a: a, low=2.0, high=1.0)
    with pytest.raises(ValueError):
        generate_fluid_cases([], lambda a: {"methane": 1.0})
    with pytest.raises(ValueError):
        blend_compositions([])
    with pytest.raises(ValueError):
        blend_compositions([(-1.0, {"methane": 1.0})])
