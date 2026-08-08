from __future__ import annotations

import pytest

from uncertainty_quantification.models import (
    ModelError,
    SingleStageModel,
    StagedModel,
    build_model,
)


def _counting_stages():
    calls = {"technical": 0, "economic": 0}

    def technical(values):
        calls["technical"] += 1
        return values["a"] * 2.0

    def economic(intermediate, values):
        calls["economic"] += 1
        return intermediate + values["b"]

    return technical, economic, calls


def test_staged_model_caches_repeated_technical_inputs():
    technical, economic, calls = _counting_stages()
    model = StagedModel(technical, economic)
    model({"a": 1.0}, {"b": 1.0})
    model({"a": 1.0}, {"b": 2.0})
    model({"a": 1.0}, {"b": 3.0})
    assert calls["technical"] == 1
    assert calls["economic"] == 3
    assert model.cache_hits == 2


def test_staged_model_re_evaluates_when_the_technical_input_changes():
    technical, economic, calls = _counting_stages()
    model = StagedModel(technical, economic)
    model({"a": 1.0}, {"b": 0.0})
    model({"a": 2.0}, {"b": 0.0})
    assert calls["technical"] == 2
    assert model.cache_hits == 0


def test_staged_model_returns_the_composed_value():
    technical, economic, _ = _counting_stages()
    assert StagedModel(technical, economic)({"a": 3.0}, {"b": 1.0}) == pytest.approx(7.0)


def test_reset_clears_cache_and_counters():
    technical, economic, calls = _counting_stages()
    model = StagedModel(technical, economic)
    model({"a": 1.0}, {"b": 1.0})
    model.reset()
    model({"a": 1.0}, {"b": 1.0})
    assert calls["technical"] == 2
    assert model.cache_hits == 0


def test_cache_report_exposes_the_saving():
    technical, economic, _ = _counting_stages()
    model = StagedModel(technical, economic)
    for b in range(5):
        model({"a": 1.0}, {"b": float(b)})
    report = model.cache_report()
    assert report["technical_evaluations"] == 1
    assert report["economic_evaluations"] == 5
    assert report["cache_hits"] == 4


def test_single_stage_model_merges_both_parameter_groups():
    model = SingleStageModel(lambda values: values["a"] + values["b"])
    assert model({"a": 1.0}, {"b": 2.0}) == pytest.approx(3.0)
    assert model.cache_report()["cache_hits"] == 0


def test_build_model_selects_the_right_wrapper():
    assert isinstance(build_model(model=lambda v: 1.0), SingleStageModel)
    assert isinstance(
        build_model(technical=lambda v: 1.0, economic=lambda i, v: i), StagedModel
    )


def test_build_model_rejects_a_mixed_specification():
    with pytest.raises(ModelError):
        build_model(model=lambda v: 1.0, technical=lambda v: 1.0)


def test_build_model_rejects_a_half_specified_staged_model():
    with pytest.raises(ModelError):
        build_model(technical=lambda v: 1.0)
