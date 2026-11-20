"""Tests of the H2S estimate with a synthetic well table and a stand-in buffer (no NeqSim, no measured data)."""

import math

import pytest
from reservoir_h2s import (
    CARBONATE,
    CONTINENTAL,
    MARINE,
    UNKNOWN,
    build_sections,
    calibrate,
    class_of,
    classify_setting,
    correlation_buffer,
    estimate_prospect,
    formation_key,
    haaland_ppm,
    load_registry,
    nice_value,
    ordinal,
    pct,
    save_registry,
    write_report,
)


def fake_buffer(temperature_c, pressure_bara, co2_molpct, fluid_type="gas"):
    """Buffer stand-in: temperature correlation with a CO2 exponent of 0.37 and a weak pressure effect."""
    value = (
        haaland_ppm(temperature_c)
        * (co2_molpct / 2.0) ** 0.37
        * (pressure_bara / 400.0) ** -0.15
    )
    return {
        "reservoir_fluid_ppm": value * 1.02,
        "separator_gas_ppm": value,
        "h2s_fugacity_bar": value * 1.0e-6 * pressure_bara * 0.6,
        "siderite_margin_log10": 1.5,
        "pyrite_margin_log10": 1.0,
        "separator_basis": "stand-in",
        "fluid_basis": "stand-in",
        "fluid_type": fluid_type,
        "equation_of_state": "none",
        "warnings": [],
    }


def synthetic_wells():
    """Forty marine wells scattered a factor 1.5 about the buffer, four red-bed wells a factor 8 below."""
    wells = []
    for i in range(40):
        temp = 70.0 + 3.0 * i
        co2 = 0.8 + 0.1 * (i % 9)
        model = fake_buffer(temp, 100.0 + 4.0 * temp, co2)["separator_gas_ppm"]
        wells.append(
            {
                "wellbore": f"NO 99/1-{i + 1}",
                "field": f"FIELD{i // 4}",
                "formation": ("Garn Fm.", "Ile Fm.", "Brent Gp.")[i % 3],
                "lat": 61.0 + 0.05 * i,
                "lon": 2.0 + 0.02 * i,
                "res_T_C": temp,
                "res_P_bara": 100.0 + 4.0 * temp,
                "co2_molpct": co2,
                "measured_ppm": model * 1.5 ** math.sin(1.7 * i),
                "model_ppm": model,
                "haaland_ppm": haaland_ppm(temp),
                "detected": True,
            }
        )
    for i in range(4):
        temp = 110.0 + 10.0 * i
        model = fake_buffer(temp, 450.0, 2.0)["separator_gas_ppm"]
        wells.append(
            {
                "wellbore": f"NO 98/2-{i + 1}",
                "formation": "Skagerrak Fm.",
                "lat": 58.0,
                "lon": 2.5,
                "res_T_C": temp,
                "res_P_bara": 450.0,
                "co2_molpct": 2.0,
                "measured_ppm": model / 8.0 * 1.3 ** ((-1) ** i),
                "model_ppm": model,
                "haaland_ppm": haaland_ppm(temp),
                "detected": True,
            }
        )
    for i in range(3):
        wells.append(
            {
                "wellbore": f"NO 97/3-{i + 1}",
                "formation": "Garn Fm.",
                "res_T_C": 60.0 + 5 * i,
                "model_ppm": 0.2 + 0.5 * i,
                "detected": False,
            }
        )
    return wells


@pytest.fixture(scope="module")
def registry():
    return calibrate(synthetic_wells(), name="synthetic", created="2026-01-01")


def test_setting_from_formation_name():
    assert classify_setting("Garn Fm.") == MARINE
    assert classify_setting("ROTLIEGENDES GP.") == CONTINENTAL
    assert classify_setting("Skagerrak Fm.; Hugin Fm.") == CONTINENTAL
    assert classify_setting("Tor Fm.") == CARBONATE
    assert classify_setting("Tofte Fm.") == MARINE  # 'tor' must match a whole word only
    assert classify_setting(None) == UNKNOWN
    assert classify_setting("Garn Fm.", "continental (Triassic-Permian)") == CONTINENTAL
    assert formation_key("Lunde Formation") == "lunde"


def test_calibration_finds_offset_and_scatter_per_setting(registry):
    marine = registry["classes"][MARINE]
    red = registry["classes"][CONTINENTAL]
    assert registry["n_wells"] == 44
    assert abs(marine["offset_log10"]) < 0.06
    assert 0.08 < marine["sd_log10"] < 0.2
    assert red["offset_log10"] == pytest.approx(-math.log10(8.0), abs=0.05)
    # four wells: the range must be wider than their own scatter alone
    assert (
        red["sd_prediction_log10"]
        > red["sd_log10"]
        >= registry["pooled_sd_log10"] - 1e-12
    )
    assert registry["non_detects"]["wells"] == 3
    assert registry["non_detects"]["buffer_below_1_ppm"] == 2
    assert 0.6 <= registry["well_out"]["inside_p10_p90"] <= 1.0
    assert registry["co2_relation"]["n"] == 44


def test_calibration_needs_five_wells():
    with pytest.raises(ValueError, match="five wells"):
        calibrate(synthetic_wells()[:3])


def test_setting_without_wells_falls_back_with_wider_scatter(registry):
    stat, note = class_of(registry, CARBONATE)
    assert stat["sd_prediction_log10"] >= 0.30
    assert "fewer than" in note


def test_prospect_estimate_and_uncertainty_budget(registry):
    prospect = {
        "name": "Prospect X",
        "formation": "Garn Fm.",
        "res_T_C": 130.0,
        "res_P_bara": 500.0,
        "co2_molpct": 2.0,
        "lat": 62.0,
        "lon": 2.4,
    }
    res = estimate_prospect(prospect, registry, synthetic_wells(), buffer=fake_buffer)
    base = fake_buffer(130.0, 500.0, 2.0)["separator_gas_ppm"]
    assert res["p50"] == pytest.approx(
        base * 10 ** registry["classes"][MARINE]["offset_log10"], rel=1e-6
    )
    assert res["p10"] < res["p50"] < res["p90"]
    shares = [b["share_of_variance"] for b in res["uncertainty_budget"]]
    assert sum(shares) == pytest.approx(1.0)
    # 10 C of temperature uncertainty must widen the range beyond the scatter of the wells
    assert res["log10_sd"] > res["statistical"]["sd_wells_log10"]
    assert (
        res["recommended_range"]["low"]
        <= res["p50"]
        <= res["recommended_range"]["high"]
    )
    assert len(res["curve"]) == 8 and res["analogues"]
    # analogues: wells of the same setting first, nearest first
    km = [a["distance_km"] for a in res["analogues"]]
    assert km == sorted(km) and res["analogues"][0]["match_level"] >= 1
    assert {a["match"] for a in res["analogues"]} <= {"same formation", "same setting"}
    # sour service: partial pressure is mole fraction times reservoir pressure
    assert res["sour_service"]["partial_pressure_kpa_p50"] == pytest.approx(
        res["p50"] * 1.02 * 1e-6 * 500.0 * 100.0, rel=1e-6
    )
    assert 0.0 < res["sour_service"]["probability_sour"] < 1.0


def test_measured_conditions_give_a_narrower_range(registry):
    prospect = {
        "name": "D",
        "formation": "Ile Fm.",
        "res_T_C": 130.0,
        "res_P_bara": 500.0,
        "co2_molpct": 2.0,
    }
    wide = estimate_prospect(prospect, registry, buffer=fake_buffer, curve=False)
    narrow = estimate_prospect(
        {**prospect, "measured_conditions": True},
        registry,
        buffer=fake_buffer,
        curve=False,
    )
    assert narrow["log10_sd"] < wide["log10_sd"]


def test_missing_co2_and_pressure_come_from_the_trends_and_are_listed(registry):
    res = estimate_prospect(
        {"name": "P", "formation": "Garn Fm.", "res_T_C": 120.0},
        registry,
        buffer=fake_buffer,
        curve=False,
    )
    gaps = " ".join(res["data_gaps"])
    assert "CO2 content not given" in gaps and "Reservoir pressure not given" in gaps
    assert (
        res["prospect"]["co2_used_molpct"] > 0
        and res["prospect"]["res_P_used_bara"] > 50
    )


def test_red_beds_are_lower_and_wider_than_marine(registry):
    base = {"name": "P", "res_T_C": 130.0, "res_P_bara": 450.0, "co2_molpct": 2.0}
    marine = estimate_prospect(
        {**base, "formation": "Garn Fm."}, registry, buffer=fake_buffer, curve=False
    )
    red = estimate_prospect(
        {**base, "formation": "Skagerrak Fm."},
        registry,
        buffer=fake_buffer,
        curve=False,
    )
    assert red["p50"] < 0.3 * marine["p50"]
    assert red["log10_sd"] > marine["log10_sd"]
    assert any("red beds" in r for r in red["reasoning"])


def test_readings_replace_the_buffer_and_low_readings_keep_the_upper_design_value(
    registry,
):
    prospect = {
        "name": "D",
        "formation": "Garn Fm.",
        "res_T_C": 150.0,
        "res_P_bara": 600.0,
        "co2_molpct": 3.0,
        "measured_conditions": True,
    }
    model = estimate_prospect(prospect, registry, buffer=fake_buffer, curve=False)
    res = estimate_prospect(
        prospect,
        registry,
        buffer=fake_buffer,
        measurements=[9.0, 11.0, 10.0],
        curve=False,
    )
    assert res["best_estimate"] == pytest.approx(10.0)
    assert res["basis"].startswith("H2S measured")
    low = estimate_prospect(
        prospect, registry, buffer=fake_buffer, measurements=[0.5], curve=False
    )
    assert low["best_estimate"] == pytest.approx(0.5)
    # a reading far below the buffer does not lower the upper design value below the buffer estimate
    assert low["recommended_range"]["high"] >= 0.7 * model["p50"]
    assert any("weaker evidence" in r for r in low["reasoning"])


def test_carbonate_and_cold_reservoirs_are_flagged(registry):
    chalk = estimate_prospect(
        {
            "name": "C",
            "formation": "Tor Fm.",
            "res_T_C": 130.0,
            "res_P_bara": 480.0,
            "co2_molpct": 2.0,
        },
        registry,
        buffer=fake_buffer,
        curve=False,
    )
    assert any(
        "outside the calibration" in r or "does not cover" in r
        for r in chalk["reasoning"] + chalk["data_gaps"]
    )
    cold = estimate_prospect(
        {
            "name": "S",
            "formation": "Garn Fm.",
            "res_T_C": 45.0,
            "res_P_bara": 150.0,
            "co2_molpct": 0.5,
        },
        registry,
        buffer=fake_buffer,
        curve=False,
    )
    assert any("70 °C" in r for r in cold["reasoning"])


def test_temperature_is_required(registry):
    with pytest.raises(ValueError, match="temperature"):
        estimate_prospect({"name": "P"}, registry, buffer=fake_buffer)


def test_correlation_buffer_and_rounding():
    assert correlation_buffer(120.0)["separator_gas_ppm"] == pytest.approx(
        haaland_ppm(120.0)
    )
    assert haaland_ppm(160.0) > haaland_ppm(100.0) > 0.5
    assert (
        nice_value(2.3, -1) == 2.0
        and nice_value(2.3, 1) == 2.5
        and nice_value(0.054, 1) == pytest.approx(0.06)
    )
    assert [ordinal(v) for v in (1, 2, 3, 11, 62.8, 112)] == [
        "1st",
        "2nd",
        "3rd",
        "11th",
        "63rd",
        "112th",
    ]
    assert pct(0.001) == "<1 %" and pct(0.999) == ">99 %" and pct(0.382) == "38 %"


def test_report_files_and_registry_round_trip(registry, tmp_path):
    path = tmp_path / "registry.json"
    save_registry(registry, str(path))
    assert load_registry(str(path))["n_wells"] == registry["n_wells"]
    res = estimate_prospect(
        {
            "name": "Prospect X",
            "formation": "Garn Fm.",
            "res_T_C": 130.0,
            "lat": 62.0,
            "lon": 2.4,
        },
        registry,
        synthetic_wells(),
        buffer=fake_buffer,
    )
    headings = [s["heading"] for s in build_sections(res)]
    assert headings[0] == "Summary" and "Sour service and gas specification" in headings
    files = write_report(res, str(tmp_path / "out"), wells=synthetic_wells())
    with open(files["markdown"], encoding="utf-8") as handle:
        text = handle.read()
    assert (
        "Prospect X" in text and "P10 / P50 / P90" in text and "nan" not in text.lower()
    )


def test_nearby_wells_without_h2s_are_reported(registry):
    wells = synthetic_wells()
    for i, w in enumerate(w for w in wells if w.get("detected") is False):
        w.update({"lat": 62.0 + 0.05 * i, "lon": 2.4})
    res = estimate_prospect(
        {
            "name": "P",
            "formation": "Garn Fm.",
            "res_T_C": 75.0,
            "lat": 62.0,
            "lon": 2.4,
        },
        registry,
        wells,
        buffer=fake_buffer,
        curve=False,
    )
    assert [round(s["distance_km"]) for s in res["non_detects_nearby"]] == [0, 6, 11]
    assert any(
        "3 tested wells within 50 km had no detectable H2S" in r
        for r in res["reasoning"]
    )
    far = estimate_prospect(
        {
            "name": "P",
            "formation": "Garn Fm.",
            "res_T_C": 75.0,
            "lat": 70.0,
            "lon": 20.0,
        },
        registry,
        wells,
        buffer=fake_buffer,
        curve=False,
    )
    assert far["non_detects_nearby"] == []
    single = estimate_prospect(
        {
            "name": "P",
            "formation": "Skagerrak Fm.",
            "res_T_C": 120.0,
            "lat": 58.2,
            "lon": 2.5,
        },
        registry,
        [w for w in wells if w.get("formation") == "Skagerrak Fm."][:1],
        buffer=fake_buffer,
        curve=False,
    )
    assert any(
        "there is one measured well of the same setting" in r
        and " to " not in r.split(":")[1]
        for r in single["reasoning"]
    )
