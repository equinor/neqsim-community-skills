import json

import pytest
from flare_helideck_dispersion import (
    BenchmarkScenario,
    StudySettings,
    run_study,
)
from flare_helideck_dispersion.results import (
    benchmark_points,
    build_results,
    validate_fragment,
    write_results_json,
)


@pytest.fixture(scope="module")
def fragment(coarse_study, wind, cases):
    from flare_helideck_dispersion import run_sensitivity

    sens = run_sensitivity(
        cases,
        wind,
        coarse_study.receptors,
        coarse_study.settings,
        tilt_scan_cases=["cold"],
        uncertainty_cases=["cold"],
        tilts_deg=(30.0, 60.0),
        n_samples=2,
        ranges={"tilt_deg": (40.0, 50.0)},
    )
    scen = [
        BenchmarkScenario(
            "cold 2 m/s", cases[1], 2.0, "illustrative", "test reference", 0.0
        )
    ]
    return build_results(coarse_study, [], sens, scen)


def test_conclusions_is_a_string_and_states_the_conditional_semantics(fragment):
    assert isinstance(fragment["conclusions"], str)
    assert "conditional on an unignited release" in fragment["conclusions"]
    assert "no annual frequency" in fragment["conclusions"]
    assert "CFD" in fragment["conclusions"]


def test_fragment_is_well_formed(fragment):
    assert validate_fragment(fragment) == []
    for key in (
        "key_results",
        "figure_captions",
        "figure_discussion",
        "tables",
        "assumptions",
        "data_gaps",
        "uncertainty",
        "risk_evaluation",
        "contributor_ranking",
        "ruled_out",
        "robustness",
        "conservatism",
        "discriminating_test",
        "evidence_against",
        "benchmark_validation",
    ):
        assert key in fragment, key
    assert isinstance(fragment["discriminating_test"], str)
    assert all(len(t["headers"]) <= 9 for t in fragment["tables"])


def test_headline_numbers_come_from_the_study(fragment, coarse_study):
    kr = fragment["key_results"]
    cold = coarse_study.summaries["cold"]["modes"]["briggs"]
    assert kr["cold_peak_any_path_pct_lfl"]["value"] == pytest.approx(
        cold["peak_pct_lfl_any_path"]
    )
    assert kr["cold_hours_ge20_any_path_pct"]["value"] == pytest.approx(
        cold["exceed_pct_hours"]["20"]["any_path"]
    )
    rows = {r[0]: r for r in fragment["tables"][0]["rows"]}
    assert rows["cold"][6] == pytest.approx(round(cold["peak_pct_lfl_any_path"], 1))


def test_both_criteria_are_reported_with_sources(fragment):
    crit = {c["name"]: c for c in fragment["acceptance_criteria"]}
    assert {"10 % LFL", "20 % LFL"} <= set(crit)
    assert all(c["source"] for c in crit.values())
    titles = [t["title"] for t in fragment["tables"]]
    assert any("criteria" in t.lower() for t in titles)
    exceed_table = next(
        t
        for t in fragment["tables"]
        if t["title"].startswith("Exceedance by criterion")
    )
    assert {row[1] for row in exceed_table["rows"]} == {10.0, 20.0}


def test_benchmark_validation_layout_and_computed_scenarios(fragment):
    bench = fragment["benchmark_validation"]
    assert isinstance(bench, dict) and isinstance(bench["points"], list)
    for p in bench["points"]:
        assert {"name", "reference_value", "neqsim_value", "status"} <= set(p)
    internal = [
        p for p in bench["points"] if p["type"] == "implementation verification"
    ]
    assert len(internal) >= 2 and all(p["status"] == "PASS" for p in internal)
    scenario = next(
        p
        for p in bench["points"]
        if p["name"].startswith("Helideck peak vs independent")
    )
    assert scenario["neqsim_value"] >= 0.0
    assert "model" in scenario["detail"] and "%" in scenario["detail"]


def test_benchmark_status_follows_classification(coarse_study, cases):
    cold = cases[1]
    hot = BenchmarkScenario("x", cold, 2.0, reference_pct_lfl_max=0.0)
    none = BenchmarkScenario("y", cold, 2.0)
    pts = benchmark_points(coarse_study, [hot, none])
    assert pts[-1]["status"] == "INFO"
    assert pts[-2]["status"] in ("PASS", "FAIL")


def test_annual_figure_needs_a_flameout_frequency(coarse_study):
    without = build_results(coarse_study, [])
    assert "annualised_exposure" not in without
    assert any(
        g["gap"].startswith("Flame-out") and g["status"] == "open"
        for g in without["data_gaps"]
    )
    with_freq = build_results(
        coarse_study, [], release_frequency_per_year=0.01, hours_per_release=5.0
    )
    assert with_freq["annualised_exposure"]["cold"][
        "release_hours_per_year"
    ] == pytest.approx(0.05)


def test_results_require_the_10_and_20_percent_thresholds(wind, coarse_geometry, cases):
    study = run_study(
        cases[:1],
        wind,
        coarse_geometry,
        StudySettings(modes=("briggs",), thresholds_pct_lfl=(5.0, 50.0)),
    )
    with pytest.raises(ValueError):
        build_results(study, [])


def test_validate_fragment_flags_problems():
    bad = {"conclusions": ["not a string"], "benchmark_validation": [{"name": "x"}]}
    problems = validate_fragment(bad)
    assert any("conclusions must be a string" in p for p in problems)
    assert any("benchmark_validation" in p for p in problems)


def test_write_results_json_merges(tmp_path, fragment):
    path = tmp_path / "results.json"
    path.write_text(
        json.dumps(
            {
                "key_results": {"existing": 1},
                "assumptions": ["old"],
                "conclusions": "old",
            }
        ),
        encoding="utf-8",
    )
    write_results_json(path, fragment, merge=True)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert (
        data["key_results"]["existing"] == 1
        and "cold_peak_any_path_pct_lfl" in data["key_results"]
    )
    assert data["assumptions"][0] == "old" and len(data["assumptions"]) > 1
    assert data["conclusions"] == fragment["conclusions"]
