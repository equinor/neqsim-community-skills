import pytest
from flare_helideck_dispersion import (
    ModelParameters,
    Receptors,
    StudySettings,
    evaluate,
    monte_carlo,
    run_sensitivity,
    tilt_scan,
    tornado,
)

RANGES = {"tilt_deg": (40.0, 50.0), "mass_flow_scale": (0.8, 1.2)}


def test_evaluate_matches_study_and_rejects_unknown_parameter(
    coarse_study, wind, cases
):
    case = cases[1]
    base = evaluate(case, wind, coarse_study.receptors, coarse_study.settings)
    study_peak = coarse_study.summaries["cold"]["modes"]["briggs"][
        "peak_pct_lfl_any_path"
    ]
    assert base["peak_any_path"] == pytest.approx(study_peak, rel=1e-12)
    with pytest.raises(ValueError):
        evaluate(
            case, wind, coarse_study.receptors, coarse_study.settings, {"nonsense": 1.0}
        )


def test_tilt_scan_is_sorted_includes_base_and_flat_tip_exposes_deck(
    coarse_study, wind, cases
):
    rows = tilt_scan(
        cases[1], wind, coarse_study.receptors, coarse_study.settings, (20.0, 70.0)
    )
    tilts = [r["tilt_deg"] for r in rows]
    assert tilts == sorted(tilts)
    assert coarse_study.settings.params.tilt_deg in tilts
    by_tilt = {r["tilt_deg"]: r for r in rows}
    # cold dense gas reaches the deck more easily when the tip is flat
    assert by_tilt[20.0]["helideck_peak"] > by_tilt[70.0]["helideck_peak"]


def test_tornado_sorted_by_swing(coarse_study, wind, cases):
    rows = tornado(
        cases[1], wind, coarse_study.receptors, coarse_study.settings, RANGES
    )
    swings = [r["swing_hours20"] for r in rows]
    assert swings == sorted(swings, reverse=True)
    assert {r["parameter_key"] for r in rows} == set(RANGES)


def test_monte_carlo_is_reproducible_with_seed(coarse_study, wind, cases):
    args = (cases[1], wind, coarse_study.receptors, coarse_study.settings, 3, 7, RANGES)
    a, b = monte_carlo(*args), monte_carlo(*args)
    assert a == b
    c = monte_carlo(
        cases[1], wind, coarse_study.receptors, coarse_study.settings, 3, 8, RANGES
    )
    assert c != a
    assert a["monte_carlo_n"] == 3 and a["seed"] == 7
    p = a["hours_ge20_pct"]
    assert p["p10"] <= p["p50"] <= p["p90"]


def test_run_sensitivity_layout(coarse_study, wind, cases):
    out = run_sensitivity(
        cases,
        wind,
        coarse_study.receptors,
        coarse_study.settings,
        tilt_scan_cases=["cold"],
        uncertainty_cases=["cold"],
        tilts_deg=(30.0, 60.0),
        n_samples=2,
        ranges=RANGES,
    )
    assert set(out) == {"tilt_scan", "cold"}
    assert set(out["cold"]) >= {"base", "tornado", "monte_carlo_n", "hours_ge20_pct"}


def test_parameter_copy_keeps_other_values():
    p = ModelParameters(tilt_deg=30.0).replace(wind_exponent=0.2)
    assert (p.tilt_deg, p.wind_exponent) == (30.0, 0.2)
    assert StudySettings(params=p).to_dict()["params"]["wind_exponent"] == 0.2
    assert Receptors  # imported for API completeness
