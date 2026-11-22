import json
import math

import numpy as np
import pytest
from active_learning_surrogate import (
    ActiveLearner,
    Parameter,
    Surrogate,
    SurrogateError,
    latin_hypercube,
    validate,
)

PARAMS = [Parameter("rate", 0.0, 100.0), Parameter("pressure", 20.0, 80.0)]


def power_model(values):
    """Smooth stand-in for a compressor-power response (kW)."""
    rate, pressure = values["rate"], values["pressure"]
    power = 2000.0 + 60.0 * rate * (80.0 / pressure) ** 0.6
    return {"power": power, "gas": 1.0 + 0.02 * rate}


def test_parameter_scaling_round_trip_and_log():
    p = Parameter("x", 10.0, 1000.0, log=True)
    assert p.to_unit(100.0) == pytest.approx(0.5)
    assert p.from_unit(p.to_unit(37.0)) == pytest.approx(37.0)
    with pytest.raises(SurrogateError):
        Parameter("x", 0.0, 1.0, log=True)
    with pytest.raises(SurrogateError):
        Parameter("x", 1.0, 1.0)


def test_latin_hypercube_is_stratified():
    points = latin_hypercube(10, 3, np.random.default_rng(0))
    for column in points.T:
        assert sorted(np.floor(column * 10).astype(int)) == list(range(10))


def test_global_mode_converges_with_few_evaluations():
    result = ActiveLearner(
        power_model, PARAMS, ["power", "gas"], tolerance=0.005, pool_size=500
    ).run()
    assert result.converged
    assert result.evaluations < 40
    report = validate(result.surrogate, power_model, n=30)
    assert report.normalised_rmse["power"] < 0.05
    assert report.coverage_2sigma["power"] >= 0.8


def test_limit_state_learns_the_capacity_boundary():
    limit = 6000.0
    learner = ActiveLearner(
        power_model,
        PARAMS,
        ["power"],
        mode="limit_state",
        limit_output="power",
        threshold=limit,
        pool_size=1000,
        max_evaluations=40,
    )
    result = learner.run()
    assert result.converged, result.stop_reason
    report = validate(result.surrogate, power_model, n=40, seed=11)
    assert report.classification_agreement >= 0.95
    # Exceedance probability over a uniform population matches brute force.
    rng = np.random.default_rng(3)
    population = [
        {"rate": r, "pressure": p}
        for r, p in zip(rng.uniform(0, 100, 4000), rng.uniform(20, 80, 4000))
    ]
    truth = np.mean([power_model(v)["power"] > limit for v in population])
    estimate = result.surrogate.exceedance_probability(population)
    assert estimate == pytest.approx(truth, abs=0.03)
    # Learning points cluster near the boundary rather than spreading evenly.
    added = result.responses[learner.initial_samples :]
    near = [abs(r["power"] - limit) < 0.15 * limit for r in added]
    assert np.mean(near) > 0.6


def test_failures_are_recorded_and_avoided():
    def flaky(values):
        if values["rate"] > 90.0:
            raise RuntimeError("flowsheet did not converge")
        if values["pressure"] < 22.0:
            return {"power": math.nan, "gas": 1.0}
        return power_model(values)

    result = ActiveLearner(flaky, PARAMS, ["power", "gas"], pool_size=500).run()
    assert result.failures >= 1
    assert len(result.failed_samples) == result.failures
    assert all(v["rate"] > 90 or v["pressure"] < 22 for v in result.failed_samples)
    assert result.evaluations == len(result.samples) + result.failures


def test_all_failures_raise():
    def broken(values):
        raise RuntimeError("no")

    with pytest.raises(SurrogateError):
        ActiveLearner(broken, PARAMS, ["power"], max_evaluations=8, pool_size=100).run()


def test_budget_stops_without_convergence():
    result = ActiveLearner(
        lambda v: {"y": math.sin(40 * v["rate"] / 100) * v["pressure"]},
        PARAMS,
        ["y"],
        tolerance=1e-6,
        max_evaluations=12,
        pool_size=200,
    ).run()
    assert not result.converged
    assert result.stop_reason == "budget exhausted"
    assert result.evaluations == 12


def test_as_model_feeds_a_monte_carlo_loop_and_json_round_trip(tmp_path):
    result = ActiveLearner(power_model, PARAMS, ["power"], pool_size=300).run()
    surrogate = result.surrogate
    fast = surrogate.as_model("power")
    value = fast({"rate": 50.0, "pressure": 40.0})
    assert value == pytest.approx(
        power_model({"rate": 50.0, "pressure": 40.0})["power"], rel=0.02
    )
    path = tmp_path / "s.json"
    surrogate.to_json(path)
    loaded = Surrogate.from_json(path)
    assert loaded.as_model("power")({"rate": 50.0, "pressure": 40.0}) == pytest.approx(
        value
    )
    assert json.loads(path.read_text())["format"].startswith("neqsim-active")
    assert surrogate.extrapolating({"rate": 150.0, "pressure": 40.0}) == ["rate"]
    summary = result.summary()
    assert summary["evaluations"] == result.evaluations
    json.dumps(summary)
    with pytest.raises(SurrogateError):
        surrogate.as_model("missing")
    with pytest.raises(SurrogateError):
        surrogate.predict({"rate": 1.0})


def test_invalid_set_up():
    with pytest.raises(SurrogateError):
        ActiveLearner(power_model, [], ["power"])
    with pytest.raises(SurrogateError):
        ActiveLearner(power_model, PARAMS, ["power"], mode="limit_state")
    with pytest.raises(SurrogateError):
        ActiveLearner(power_model, PARAMS, ["power"], mode="other")
    with pytest.raises(SurrogateError):
        ActiveLearner(power_model, PARAMS + PARAMS[:1], ["power"])
    with pytest.raises(SurrogateError):
        ActiveLearner(power_model, PARAMS, ["power"], max_evaluations=3)


def test_max_feasible_brackets_the_true_limit():
    result = ActiveLearner(
        power_model,
        PARAMS,
        ["power"],
        mode="limit_state",
        limit_output="power",
        threshold=6000.0,
        pool_size=1000,
        max_evaluations=40,
    ).run()
    found = result.surrogate.max_feasible("rate", {"pressure": 40.0})
    # power = 2000 + 60 rate (80/40)^0.6 = 6000  ->  rate = 4000 / (60 * 2^0.6)
    true_rate = 4000.0 / (60.0 * 2**0.6)
    assert found["best_estimate"] == pytest.approx(true_rate, rel=0.02)
    assert found["conservative"] <= found["best_estimate"] + 1e-9
    assert result.surrogate.max_feasible(
        "rate", {"pressure": 20.0}, "power", 1000.0
    ) == {"best_estimate": None, "conservative": None}
    with pytest.raises(SurrogateError):
        result.surrogate.max_feasible("rate", {})
    with pytest.raises(SurrogateError):
        result.surrogate.max_feasible("missing", {"pressure": 40.0})
