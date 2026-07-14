import pytest

from pvt_regression import (
    RegressionTarget,
    regress_characterization_factor,
    weighted_ssr,
)


def test_weighted_ssr_zero_at_match():
    predicted = {"psat": 170.0, "gor": 250.0}
    targets = [RegressionTarget("psat", 170.0), RegressionTarget("gor", 250.0)]
    assert weighted_ssr(predicted, targets) == pytest.approx(0.0)


def test_weighted_ssr_respects_weight():
    predicted = {"psat": 187.0, "gor": 250.0}  # 10% high on psat
    low_weight = [RegressionTarget("psat", 170.0, weight=1.0), RegressionTarget("gor", 250.0)]
    high_weight = [RegressionTarget("psat", 170.0, weight=4.0), RegressionTarget("gor", 250.0)]
    assert weighted_ssr(predicted, high_weight) > weighted_ssr(predicted, low_weight)


def test_regress_fits_factor_to_multiple_targets():
    # Forward model: both targets improve toward alpha = 1.4.
    def forward(alpha):
        return {
            "psat": 150.0 + 50.0 * (alpha - 1.0),  # = 170 at alpha 1.4
            "sto_density": 800.0 + 25.0 * (alpha - 1.0),  # = 810 at alpha 1.4
        }

    targets = [
        RegressionTarget("psat", 170.0, weight=1.0),
        RegressionTarget("sto_density", 810.0, weight=1.0),
    ]
    result = regress_characterization_factor(forward, targets, low=0.5, high=2.5, tol=1e-6)
    assert result.converged
    assert result.factor == pytest.approx(1.4, abs=1e-3)
    assert abs(result.residuals["psat"]) < 1e-3
    assert result.objective < 1e-5


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        weighted_ssr({"psat": 170.0}, [RegressionTarget("gor", 250.0)])
    with pytest.raises(ValueError):
        weighted_ssr({"psat": 170.0}, [RegressionTarget("psat", 0.0)])
    with pytest.raises(ValueError):
        regress_characterization_factor(lambda a: {"psat": a}, [], low=0.5, high=2.5)
    with pytest.raises(ValueError):
        regress_characterization_factor(
            lambda a: {"psat": a}, [RegressionTarget("psat", 1.0)], low=2.0, high=1.0
        )
