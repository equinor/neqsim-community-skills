import numpy as np
import pytest
from active_learning_surrogate import GaussianProcess, GPError


def branin_unit(x):
    a = 15.0 * x[:, 0] - 5.0
    b = 15.0 * x[:, 1]
    return (
        (b - 5.1 / (4 * np.pi**2) * a**2 + 5 / np.pi * a - 6) ** 2
        + 10 * (1 - 1 / (8 * np.pi)) * np.cos(a)
        + 10
    )


def test_interpolates_and_is_uncertain_away_from_data():
    rng = np.random.default_rng(1)
    x = rng.random((30, 2))
    gp = GaussianProcess(seed=1).fit(x, branin_unit(x))
    mean, std = gp.predict(x)
    assert np.allclose(mean, branin_unit(x), atol=0.5)
    test = rng.random((200, 2))
    error = np.abs(gp.predict(test)[0] - branin_unit(test))
    assert np.median(error) < 0.1 * np.std(branin_unit(test))
    assert std.max() < gp.predict(np.array([[3.0, 3.0]]))[1][0]


def test_loo_q2_separates_good_from_poor_fits():
    rng = np.random.default_rng(2)
    x = rng.random((25, 1))
    smooth = GaussianProcess().fit(x, np.sin(3 * x[:, 0]))
    noisy = GaussianProcess().fit(x, rng.normal(size=25))
    assert smooth.loo_q2() > 0.99
    assert noisy.loo_q2() < 0.5


def test_irrelevant_input_gets_long_length_scale():
    rng = np.random.default_rng(3)
    x = rng.random((30, 2))
    gp = GaussianProcess().fit(x, np.sin(4 * x[:, 0]))
    lengths = gp.length_scales()
    assert lengths[1] > 3 * lengths[0]


def test_state_round_trip_reproduces_predictions():
    rng = np.random.default_rng(4)
    x = rng.random((12, 2))
    gp = GaussianProcess().fit(x, x[:, 0] ** 2 + x[:, 1])
    clone = GaussianProcess.from_state(gp.state())
    probe = rng.random((5, 2))
    assert np.allclose(gp.predict(probe)[0], clone.predict(probe)[0])
    assert np.allclose(gp.predict(probe)[1], clone.predict(probe)[1])


def test_constant_output_does_not_break():
    x = np.random.default_rng(5).random((6, 1))
    mean, _ = GaussianProcess().fit(x, np.full(6, 3.0)).predict([[0.5]])
    assert mean[0] == pytest.approx(3.0)


def test_invalid_training_data():
    with pytest.raises(GPError):
        GaussianProcess().fit(np.zeros((2, 1)), np.zeros(2))
    with pytest.raises(GPError):
        GaussianProcess().fit(np.zeros((4, 1)), np.array([0, 1, np.nan, 2]))
    with pytest.raises(GPError):
        GaussianProcess().predict([[0.1]])
