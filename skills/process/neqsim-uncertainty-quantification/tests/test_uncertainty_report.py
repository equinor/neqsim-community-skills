from __future__ import annotations

import pytest

from uncertainty_quantification.distributions import Triangular, Uniform
from uncertainty_quantification.report import UncertaintyReport
from uncertainty_quantification.study import UncertaintyStudy

PARAMETERS = [
    Triangular(name="GIP", unit="GSm3", low=100.0, base_value=135.0, high=170.0),
    Uniform(name="Gas price", unit="NOK/Sm3", low=0.8, high=2.5, kind="economic"),
]


def _report(n: int = 400, **kwargs) -> UncertaintyReport:
    study = UncertaintyStudy(
        parameters=PARAMETERS,
        output_name="NPV",
        output_unit="MNOK",
        seed=42,
        technical=lambda v: v["GIP"] * 0.55,
        economic=lambda volume, v: volume * v["Gas price"] * 1000.0 - 100000.0,
        simulation_engine="staged test model",
    )
    result = study.run(n)
    defaults = {
        "parameters": PARAMETERS,
        "result": result,
        "output_name": "NPV",
        "output_unit": "MNOK",
        "tornado": study.tornado(),
        "simulation_engine": study.simulation_engine,
    }
    defaults.update(kwargs)
    return UncertaintyReport(**defaults)


def test_block_percentiles_are_ascending_as_the_gate_requires():
    block = _report().to_results_json()
    assert block["p10"] <= block["p50"] <= block["p90"]


def test_block_declares_the_percentile_convention():
    assert "10th percentile" in _report().to_results_json()["percentile_convention"]


def test_block_carries_the_input_parameter_table():
    params = _report().to_results_json()["input_parameters"]
    assert [p["name"] for p in params] == ["GIP", "Gas price"]
    assert params[0]["unit"] == "GSm3"


def test_block_carries_a_tornado_with_a_consistent_column_set():
    tornado = _report().to_results_json()["tornado"]
    assert tornado
    first_keys = set(tornado[0])
    assert all(set(row) == first_keys for row in tornado)
    assert "parameter" in first_keys
    assert "swing" in first_keys


def test_tornado_columns_are_named_after_the_output():
    tornado = _report().to_results_json()["tornado"]
    assert "npv_low" in tornado[0]
    assert "npv_high" in tornado[0]


def test_output_parameter_label_includes_the_unit():
    assert _report().to_results_json()["output_parameter"] == "NPV (MNOK)"


def test_block_reports_the_sampling_method_and_seed():
    block = _report().to_results_json()
    assert block["sampling_method"] == "lhs"
    assert block["seed"] == 42


def test_block_reports_honest_model_evaluation_counts():
    evaluations = _report().to_results_json()["model_evaluations"]
    # GIP is continuous, so every Monte Carlo sample needs its own technical solve.
    assert evaluations["technical_evaluations"] == evaluations["economic_evaluations"]
    assert evaluations["cache_hits"] == 0


def test_a_thin_run_is_blocked_on_the_sample_minimum():
    report = _report(n=50)
    assert any("minimum" in b for b in report.blockers())
    assert report.to_results_json()["blockers"] != "none"


def test_a_sufficient_converged_run_has_no_blockers():
    assert _report(n=400).blockers() == []


def test_a_run_without_a_tornado_is_blocked():
    assert any("tornado" in b for b in _report(tornado=[]).blockers())


def test_markdown_shows_the_percentiles_and_the_tornado():
    text = _report().to_markdown()
    assert "P10 (low)" in text
    assert "P50 (median)" in text
    assert "| GIP |" in text


def test_markdown_reports_the_cache_saving_when_it_happened():
    from uncertainty_quantification.distributions import Deterministic

    parameters = [
        Deterministic(name="GIP", unit="GSm3", value=135.0),
        Uniform(name="Gas price", unit="NOK/Sm3", low=0.8, high=2.5, kind="economic"),
    ]
    study = UncertaintyStudy(
        parameters=parameters,
        output_name="NPV",
        output_unit="MNOK",
        seed=42,
        technical=lambda v: v["GIP"] * 0.55,
        economic=lambda volume, v: volume * v["Gas price"] * 1000.0 - 100000.0,
    )
    result = study.run(200)
    report = UncertaintyReport(
        parameters=parameters,
        result=result,
        output_name="NPV",
        output_unit="MNOK",
        tornado=study.tornado(),
    )
    assert "served from cache" in report.to_markdown()


def test_global_sensitivity_is_included_without_unserialisable_objects():
    report = _report()
    report.sensitivity = {"method": "Sobol", "S1": [0.4, 0.6], "surrogate": object()}
    block = report.to_results_json()["global_sensitivity"]
    assert block["method"] == "Sobol"
    assert "surrogate" not in block


def test_block_is_json_serialisable():
    import json

    json.dumps(_report().to_results_json())
