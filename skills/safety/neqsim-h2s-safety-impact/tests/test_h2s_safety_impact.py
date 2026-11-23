import math

import pytest
from h2s_safety_impact import (
    detector_equivalence,
    evidence_gate,
    export_blend_ppm,
    h2s_safety_impact,
    mg_nm3_to_ppm,
    partial_pressure_kpa,
    ppm_for_partial_pressure,
    ppm_to_kg_m3,
    ppm_to_mg_nm3,
    probit_h2s,
    removal_and_scavenger,
    so2_emission_kg_h,
    sour_service_screen,
    toxic_reach,
    vapour_ppm_over_water,
)


def test_partial_pressure_and_threshold_ppm():
    assert partial_pressure_kpa(5.0, 258.4) == pytest.approx(0.1292, rel=1e-3)
    assert ppm_for_partial_pressure(0.3, 258.4) == pytest.approx(11.61, rel=1e-3)
    assert partial_pressure_kpa(
        ppm_for_partial_pressure(0.3, 50.0), 50.0
    ) == pytest.approx(0.3)
    with pytest.raises(ValueError):
        partial_pressure_kpa(-1.0, 10.0)


def test_sour_service_flags_and_source_echo():
    below = sour_service_screen(1.0, 100.0)
    border = sour_service_screen(5.0, 258.4)
    sour = sour_service_screen(20.0, 258.4)
    assert (below["flag"], border["flag"], sour["flag"]) == (
        "below",
        "borderline",
        "sour",
    )
    assert border["threshold_source"] == "convention, standard text not read"
    assert sour_service_screen(5.0, 258.4, 0.01, source="TR3051")["flag"] == "sour"


def test_mg_nm3_round_trip():
    assert mg_nm3_to_ppm(5.0) == pytest.approx(3.288, rel=1e-3)
    assert ppm_to_mg_nm3(mg_nm3_to_ppm(5.0)) == pytest.approx(5.0)


def test_detector_equivalence_matches_clause_numbers():
    # 1500 ppm in process gas, LFL 5 vol-%, 20 % LEL alarm -> 15 ppm in air (the relation quoted in NORSOK S-001)
    d = detector_equivalence(1500.0, 0.05)
    assert d["h2s_ppm_in_air_at_gas_alarm"] == pytest.approx(15.0)
    assert d["dedicated_h2s_detection_required"] is True
    low = detector_equivalence(20.0, 0.04)
    assert low["h2s_ppm_in_air_at_gas_alarm"] == pytest.approx(0.16)
    assert low["h2s_alarm_reached_before_gas_alarm"] is False
    assert low["dedicated_h2s_detection_required"] is False


def test_so2_and_scavenger_hand_calculation():
    # 250 t/h of gas (MW 21.4) with 20 ppm H2S: 250000 * 20e-6 * 34.081/21.4 = 7.96 kg/h H2S -> 14.9 kg/h SO2
    assert so2_emission_kg_h(250000.0, 20.0, 21.4) == pytest.approx(14.95, rel=1e-2)
    r = removal_and_scavenger(6.0, 3.29, 4.0e6, 8.0)
    kg_d = (6.0 - 3.29) * 1e-6 * 4.0e6 / 23.64 * 34.081
    assert r["removal_kg_d"] == pytest.approx(kg_d)
    assert r["scavenger_t_d"] == pytest.approx(kg_d * 8 / 1000)
    assert removal_and_scavenger(2.0, 3.29, 4.0e6)["removal_kg_d"] == 0.0


def test_blend_is_rate_weighted():
    assert export_blend_ppm([(1.0e6, 6.0), (3.0e6, 1.0)]) == pytest.approx(2.25)
    with pytest.raises(ValueError):
        export_blend_ppm([(0.0, 5.0)])


def test_vapour_over_water_hand_calculation():
    # 1 mg/L at 40 C, 1 atm: x = 5.29e-7, K = 55.5/kH(40 C) = 762 -> about 403 ppm in the vapour
    assert vapour_ppm_over_water(1.0, 40.0) == pytest.approx(403.0, rel=0.03)


def test_probit_reference_point():
    y, p = probit_h2s(1000.0, 10.0)
    assert y == pytest.approx(5.21, abs=0.02)
    assert 0.55 < p < 0.62
    assert probit_h2s(30.0, 10.0)[1] < 1e-3
    assert probit_h2s(0.0, 10.0)[1] == 0.0


def test_toxic_reach_passes_the_diluted_threshold_to_the_plume_model():
    seen = []

    def plume(rate, thr):
        seen.append(thr)
        return rate / thr * 1.0e-6

    w = 1.0e-5
    d = toxic_reach(10.0, w, {"alarm": 5.0, "IDLH": 100.0}, plume)
    assert seen[0] == pytest.approx(ppm_to_kg_m3(5.0) / w)
    assert d["alarm"] > d["IDLH"] > 0.0
    assert toxic_reach(10.0, 0.0, {"alarm": 5.0}, plume) == {"alarm": 0.0}
    assert ppm_to_kg_m3(100.0) == pytest.approx(1.42e-4, rel=0.02)


def test_evidence_gate_never_passes_without_measurement():
    g = evidence_gate(
        "estimate",
        {
            "y_h2s_ppm": 3.5,
            "basis": "test separator gas",
            "temperature_c": 119.0,
            "pressure_bara": 338.0,
        },
    )
    assert g["status"] == "UNVERIFIED_SCREENING"
    assert any(x["gap"] == "measured H2S" for x in g["data_gaps"])
    m = evidence_gate(
        "measured",
        {
            "y_h2s_ppm": 3.5,
            "basis": "test separator gas",
            "temperature_c": 119.0,
            "pressure_bara": 338.0,
        },
    )
    assert m["status"] == "VERIFIED_INPUT" and m["data_gaps"] == []
    missing = evidence_gate("measured", {"y_h2s_ppm": 3.5})
    assert (
        missing["status"] == "UNVERIFIED_SCREENING" and len(missing["data_gaps"]) == 3
    )
    with pytest.raises(ValueError):
        evidence_gate("guess", {})


def test_worked_example_generic_oil_rim_field():
    case = {
        "y_h2s_ppm": 4.7,
        "basis": "gas at the host inlet separator",
        "temperature_c": 119.0,
        "pressure_bara": 13.0,
        "evidence": "estimate",
        "locations": {"shut-in tubing head": (4.5, 258.4), "host inlet": (4.7, 13.0)},
        "lfl_vol_frac": 0.0376,
        "tie_in_gas_sm3_d": 1.0e6,
        "host_gas": (2.5e6, 1.0),
        "export_limit_mg_nm3": 5.0,
    }
    r = h2s_safety_impact(case)
    assert r["gate"]["status"] == "UNVERIFIED_SCREENING"
    assert r["sour_service"]["shut-in tubing head"]["flag"] == "borderline"
    assert r["sour_service"]["host inlet"]["flag"] == "below"
    assert r["detector"]["dedicated_h2s_detection_required"] is False
    assert r["export"]["blend_ppm"] == pytest.approx((4.7 * 1.0 + 1.0 * 2.5) / 3.5)
    assert r["export"]["exceeds"] is False
    assert math.isclose(r["export"]["limit_ppm"], 3.288, rel_tol=1e-3)
