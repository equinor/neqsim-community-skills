from __future__ import annotations

import pytest

from uncertainty_quantification.distributions import Triangular, Uniform
from uncertainty_quantification.study import StudyError, UncertaintyStudy


def _linear_study(**kwargs):
    parameters = [
        Uniform(name="a", low=0.0, high=1.0),
        Uniform(name="b", low=0.0, high=10.0, kind="economic"),
    ]
    defaults = {
        "parameters": parameters,
        "model": lambda v: v["a"] + v["b"],
        "seed": 42,
    }
    defaults.update(kwargs)
    return UncertaintyStudy(**defaults)


def test_study_requires_at_least_one_parameter():
    with pytest.raises(StudyError):
        UncertaintyStudy(parameters=[], model=lambda v: 0.0)


def test_study_rejects_duplicate_parameter_names():
    with pytest.raises(StudyError):
        UncertaintyStudy(
            parameters=[Uniform(name="a", low=0, high=1), Uniform(name="a", low=0, high=2)],
            model=lambda v: 0.0,
        )


def test_parameters_split_into_technical_and_economic():
    study = _linear_study()
    assert [p.name for p in study.technical_parameters] == ["a"]
    assert [p.name for p in study.economic_parameters] == ["b"]


def test_run_produces_one_output_per_sample():
    result = _linear_study().run(50)
    assert result.count == 50
    assert len(result.samples) == 50


def test_run_is_reproducible_for_a_fixed_seed():
    assert _linear_study().run(30).outputs == _linear_study().run(30).outputs


def test_run_recovers_the_analytical_mean_of_a_linear_model():
    result = _linear_study().run(2000)
    assert result.summary.mean == pytest.approx(5.5, abs=0.15)


def test_percentiles_are_ascending():
    summary = _linear_study().run(500).summary
    assert summary.p10 < summary.p50 < summary.p90


def test_evaluate_requires_every_parameter():
    with pytest.raises(StudyError):
        _linear_study().evaluate({"a": 0.5})


def test_run_rejects_a_non_positive_sample_count():
    with pytest.raises(StudyError):
        _linear_study().run(0)


def test_a_failing_evaluation_aborts_the_run_by_default():
    def explode(values):
        raise RuntimeError("no convergence")

    with pytest.raises(RuntimeError):
        _linear_study(model=explode).run(5)


def test_skip_failures_drops_the_bad_samples_and_counts_them():
    def sometimes(values):
        if values["a"] > 0.5:
            raise RuntimeError("no convergence")
        return values["a"]

    result = _linear_study(model=sometimes).run(100, skip_failures=True)
    assert result.failures > 0
    assert result.count == 100 - result.failures


def test_a_study_where_everything_fails_raises():
    with pytest.raises(StudyError):
        _linear_study(model=lambda v: 1 / 0).run(5, skip_failures=True)


def test_staged_study_caches_the_technical_stage_across_economic_samples():
    from uncertainty_quantification.distributions import Deterministic

    parameters = [
        Deterministic(name="tech", unit="-", value=1.0),
        Uniform(name="econ", low=0.0, high=1.0, kind="economic"),
    ]
    study = UncertaintyStudy(
        parameters=parameters,
        technical=lambda v: v["tech"] * 2.0,
        economic=lambda intermediate, v: intermediate + v["econ"],
        seed=1,
    )
    result = study.run(40)
    assert result.cache_report["technical_evaluations"] == 1
    assert result.cache_report["cache_hits"] == 39


def test_a_continuous_technical_parameter_gives_no_cache_saving():
    study = UncertaintyStudy(
        parameters=[
            Uniform(name="tech", low=0.0, high=1.0),
            Uniform(name="econ", low=0.0, high=1.0, kind="economic"),
        ],
        technical=lambda v: v["tech"] * 2.0,
        economic=lambda intermediate, v: intermediate + v["econ"],
        seed=1,
    )
    result = study.run(30)
    assert result.cache_report["technical_evaluations"] == 30
    assert result.cache_report["cache_hits"] == 0


def test_tornado_reuses_the_cached_technical_stage_for_economic_rows():
    study = UncertaintyStudy(
        parameters=[
            Uniform(name="tech", low=0.0, high=1.0),
            Uniform(name="price", low=1.0, high=2.0, kind="economic"),
            Uniform(name="capex", low=1.0, high=2.0, kind="economic"),
        ],
        technical=lambda v: v["tech"] * 2.0,
        economic=lambda intermediate, v: intermediate * v["price"] - v["capex"],
        seed=1,
    )
    study.run(1)
    study.tornado()
    # Tornado: 2 'tech' rows need their own solve; the 4 economic rows all sit at
    # base tech, so they cost one solve plus three cache hits.
    assert study._model.cache_hits == 3
    assert study._model.technical_evaluations == 4
    assert study._model.economic_evaluations == 7


def test_tornado_is_ranked_by_descending_swing():
    parameters = [
        Uniform(name="small", low=0.0, high=1.0),
        Uniform(name="large", low=0.0, high=100.0),
    ]
    study = UncertaintyStudy(
        parameters=parameters, model=lambda v: v["small"] + v["large"], seed=1
    )
    entries = study.tornado()
    assert [e.parameter for e in entries] == ["large", "small"]
    assert entries[0].swing > entries[1].swing


def test_tornado_swing_matches_the_analytical_range():
    study = UncertaintyStudy(
        parameters=[Uniform(name="a", low=0.0, high=10.0)],
        model=lambda v: 2.0 * v["a"],
        seed=1,
    )
    entry = study.tornado()[0]
    assert entry.swing == pytest.approx(2.0 * (9.0 - 1.0))


def test_tornado_skips_a_parameter_with_no_range():
    from uncertainty_quantification.distributions import Deterministic

    study = UncertaintyStudy(
        parameters=[
            Uniform(name="a", low=0.0, high=1.0),
            Deterministic(name="fixed", value=3.0),
        ],
        model=lambda v: v["a"] + v["fixed"],
        seed=1,
    )
    assert [e.parameter for e in study.tornado()] == ["a"]


def test_tornado_row_uses_the_requested_output_prefix():
    row = _linear_study().tornado()[0].to_row("npv")
    assert "npv_low" in row
    assert "npv_high" in row
    assert "swing" in row
    assert "parameter" in row


def test_base_values_use_the_distribution_base_not_the_median():
    study = UncertaintyStudy(
        parameters=[Triangular(name="a", low=0.0, base_value=0.3, high=1.0)],
        model=lambda v: v["a"],
        seed=1,
    )
    assert study.base_values()["a"] == pytest.approx(0.3)
