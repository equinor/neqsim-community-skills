"""Tests for the reservoir mercury estimation package (synthetic data only)."""

import math
import random

import pytest
from reservoir_mercury import (
    ShrinkageModel,
    classify_formation,
    cross_validate,
    distance_km,
    estimate_prospect,
    exceedance,
    find_analogues,
    interval_coverage,
    lognormal_quantiles,
    nice_range,
    nice_value,
    write_report,
)


def synthetic_tests(seed=3):
    """Wells in three age classes with a class effect, a temperature effect and well-to-well scatter."""
    rng = random.Random(seed)
    level = {
        "Lower Jurassic / Upper Triassic": 1.0,
        "Middle Jurassic": 0.3,
        "Upper Jurassic and younger": -0.4,
    }
    forms = {
        "Lower Jurassic / Upper Triassic": ("Tilje Fm.", "BAAT GP."),
        "Middle Jurassic": ("Garn Fm.", "FANGST GP."),
        "Upper Jurassic and younger": ("Draupne Fm.", "VIKING GP."),
    }
    rows = []
    for w in range(60):
        cls = list(level)[w % 3]
        t = 60 + 120 * rng.random()
        well_effect = rng.gauss(0, 0.6)
        for k in range(1 + w % 3):
            y = level[cls] + 0.01 * (t - 115) + well_effect + rng.gauss(0, 0.3)
            rows.append(
                {
                    "well": f"W{w}",
                    "wellbore": f"W{w}",
                    "field": f"F{w // 4}",
                    "source_class": cls,
                    "formation": forms[cls][0],
                    "group": forms[cls][1],
                    "province": f"P{w % 4}",
                    "res_T_C": t,
                    "lat": 60 + 0.05 * w,
                    "lon": 2 + 0.02 * w,
                    "y": y,
                    "hg": 10**y,
                    "operation": False,
                }
            )
    return rows


def registry_from(rows):
    cat, num = ("source_class", "province"), ("res_T_C",)
    cv = cross_validate(rows, "y", "well", cat, num, ridge=4.0)
    base = cross_validate(rows, "y", "well", (), (), ridge=4.0)
    model = ShrinkageModel(categorical=cat, numeric=num, ridge=4.0).fit(rows, "y")
    model.cv_sd = cv["rmse"]
    strip = lambda d: {k: v for k, v in d.items() if k != "predictions"}
    return (
        {
            "name": "synthetic",
            "created": "2026-01-01",
            "model": model.to_dict(),
            "model_name": "M",
            "cv_sd_log10": cv["rmse"],
            "n_tests": len(rows),
            "n_wells": 60,
            "cross_validation": {
                "M0 none": {"well_out": strip(base)},
                "M": {"well_out": strip(cv)},
            },
            "distribution": {"p10": 0.2, "p50": 2.0, "p90": 40.0},
            "discovery_level": {
                "offset_log10_over_test_prediction": 0.3,
                "sd_log10_about_prediction": 0.9,
            },
            "within_well_sd_log10": 0.3,
            "within_field_sd_log10": 0.7,
            "trace_limit_exceedance": 0.07,
        },
        cv,
        base,
    )


def test_model_recovers_class_and_temperature_effects_and_beats_the_mean():
    rows = synthetic_tests()
    registry, cv, base = registry_from(rows)
    model = ShrinkageModel.from_dict(registry["model"])
    eff = model.effects["source_class"]
    assert (
        eff["Lower Jurassic / Upper Triassic"]
        > eff["Middle Jurassic"]
        > eff["Upper Jurassic and younger"]
    )
    slope = model.numeric_coef["res_T_C"] / model.numeric_scale["res_T_C"]
    assert 0.006 < slope < 0.014
    assert cv["rmse"] < base["rmse"] - 0.1
    # an unseen category contributes nothing and is reported
    pred = model.predict({"source_class": "Devonian", "res_T_C": 115.0})
    assert (
        pred["unseen"] == ["source_class=Devonian"]
        and pred["contributions"]["source_class"] == 0.0
    )


def test_shrinkage_pulls_a_small_group_towards_the_mean():
    rows = [{"g": "big", "y": 0.0} for _ in range(30)] + [{"g": "small", "y": 2.0}]
    weak = ShrinkageModel(categorical=("g",), ridge=0.01).fit(rows, "y")
    strong = ShrinkageModel(categorical=("g",), ridge=5.0).fit(rows, "y")
    assert weak.predict({"g": "small"})["log10"] > 1.8
    assert strong.predict({"g": "small"})["log10"] < 0.8


def test_stratigraphy_lookup_handles_spelling_and_unknown_names():
    assert (
        classify_formation("Tilje Fm.")["source_class"]
        == "Lower Jurassic / Upper Triassic"
    )
    assert classify_formation("STØ")["group"] == "KAPP TOSCANA GP."
    assert classify_formation("Intra Draupne SS")["epoch"] == "Jurassic Late"
    assert classify_formation("Unknownite")["source_class"] is None


def test_helpers():
    assert nice_range(13.0, 180.0) == (10.0, 200.0)
    assert nice_range(0.6, 0.6) == (0.5, 1.0)
    assert [nice_value(v) for v in (1020.0, 217.0, 42.0, 0.75)] == [
        1000.0,
        200.0,
        50.0,
        1.0,
    ]
    cover = interval_coverage([-2.0, -0.5, 0.0, 0.4, 3.0], 1.0)
    assert cover == {"inside": 0.6, "above": 0.2, "below": 0.2}
    assert distance_km(60.0, 2.0, 61.0, 2.0) == pytest.approx(111.2, abs=0.5)
    assert exceedance(1.0, 1.0, 10.0) == pytest.approx(0.5)
    q = lognormal_quantiles(1.0, 1.0)
    assert q["p10"] == pytest.approx(10 ** (1 - 1.2816), rel=1e-3) and q["p90"] / q[
        "p50"
    ] == pytest.approx(q["p50"] / q["p10"])


def test_estimate_without_measurement_is_stated_for_the_highest_reading_in_the_discovery():
    rows = synthetic_tests()
    registry, _, _ = registry_from(rows)
    prospect = {
        "name": "Alpha",
        "lat": 61.0,
        "lon": 2.4,
        "formation": "Tilje",
        "res_T_C": 150.0,
        "res_P_bara": 500.0,
    }
    res = estimate_prospect(prospect, registry, rows)
    assert res["prospect"]["source_class"] == "Lower Jurassic / Upper Triassic"
    assert res["prospect"]["province"].startswith("P")
    st = res["statistical"]
    assert res["best_estimate"] == pytest.approx(
        st["highest_reading_in_discovery"]["p50"]
    )
    assert st["highest_reading_in_discovery"]["p50"] == pytest.approx(
        st["typical_test"]["p50"] * 10**0.3
    )
    assert res["p10"] < res["best_estimate"] < res["p90"]
    assert (
        res["recommended_range"]["low"]
        <= res["best_estimate"]
        <= res["recommended_range"]["high"]
    )
    assert 0.0 < res["probability_above"]["100"] < res["probability_above"]["10"] < 1.0
    assert res["analogues"][0]["match"] == "same formation"
    assert any(
        "Mineral-equilibrium limits not calculated" in g for g in res["data_gaps"]
    )
    young = estimate_prospect(
        {"name": "Beta", "formation": "Draupne", "res_T_C": 80.0}, registry, rows
    )
    assert young["best_estimate"] < res["best_estimate"]


def test_measurement_in_the_discovery_overrides_the_model_and_narrows_the_range():
    rows = synthetic_tests()
    registry, _, _ = registry_from(rows)
    prospect = {"name": "Gamma", "formation": "Garn", "res_T_C": 120.0}
    base = estimate_prospect(prospect, registry, rows)
    meas = estimate_prospect(prospect, registry, rows, measurements=[4.0, 22.0, 9.0])
    assert meas["best_estimate"] == 22.0 and meas["basis"].startswith(
        "highest gas reading"
    )
    assert meas["p90"] / meas["p10"] < base["p90"] / base["p10"]
    assert meas["recommended_range"] == {"low": 5.0, "high": 50.0}


def test_limits_cap_the_recommended_range_and_report_is_written(tmp_path):
    rows = synthetic_tests()
    registry, _, _ = registry_from(rows)
    limits = {
        "cinnabar_limit": 300.0,
        "trace_sulfide_limit": 0.9,
        "liquid_limit": 20.0,
        "trace_activity": 0.003,
        "buffered_h2s_ppm": 0.1,
        "separator_basis": "flash",
        "equation_of_state": "UMR-PRU-MC",
        "fluid_basis": "generic",
        "warnings": [],
    }
    res = estimate_prospect(
        {
            "name": "Delta 1",
            "formation": "Tilje",
            "res_T_C": 170.0,
            "res_P_bara": 600.0,
        },
        registry,
        rows,
        limits=limits,
    )
    assert res["recommended_range"]["high"] <= 20.0
    files = write_report(
        res,
        str(tmp_path),
        registry=registry,
        tests=rows,
        downstream={
            "route": "pipeline X",
            "risk": "High",
            "description": "No removal unit.",
            "source": "test",
        },
    )
    with open(files["markdown"], encoding="utf-8") as handle:
        text = handle.read()
    assert (
        "## 1 Summary" in text
        and "Consequence for the gas route" in text
        and "Delta 1" in text
    )
    assert math.isfinite(res["best_estimate"])


def test_analogues_prefer_formation_then_distance():
    rows = synthetic_tests()
    an = find_analogues(
        {
            "lat": 60.0,
            "lon": 2.0,
            "formation": "Garn",
            "group": "FANGST GP.",
            "source_class": "Middle Jurassic",
        },
        rows,
        count=5,
    )
    assert all(a["match"] == "same formation" for a in an)
    assert [a["distance_km"] for a in an] == sorted(a["distance_km"] for a in an)


def test_unknown_reservoir_age_highlights_no_tests(tmp_path):
    rows = synthetic_tests()
    registry, _, _ = registry_from(rows)
    res = estimate_prospect({"name": "Epsilon", "res_T_C": 120.0}, registry, rows)
    files = write_report(res, str(tmp_path), registry=registry, tests=rows)
    with open(files["markdown"], encoding="utf-8") as handle:
        text = handle.read()
    assert "no tests are highlighted" in text
    assert "same reservoir age class are highlighted" not in text
