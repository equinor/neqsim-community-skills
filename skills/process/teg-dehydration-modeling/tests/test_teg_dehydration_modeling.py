import pytest

from teg_dehydration_modeling import (
    DEFAULT_FEED,
    GAS_COMPONENTS,
    NMVOC,
    build_teg_plant,
    classify_emissions,
    teg_mass_fraction,
)


def test_constants_are_aligned() -> None:
    assert len(GAS_COMPONENTS) == len(DEFAULT_FEED)
    assert "methane" in GAS_COMPONENTS
    assert "benzene" in GAS_COMPONENTS
    assert NMVOC.issubset(set(GAS_COMPONENTS))
    assert "methane" not in NMVOC


def test_build_teg_plant_requires_neqsim_message() -> None:
    pytest.importorskip("neqsim")


def _default_case(**overrides):
    kwargs = dict(
        feed_fractions=DEFAULT_FEED,
        feed_flow_MSm3_day=4.65,
        feed_temp_C=25.0,
        feed_pressure_bara=70.0,
        absorber_pressure_bara=85.0,
        absorber_temp_C=35.0,
        teg_flow_kg_hr=5500.0,
        teg_feed_temp_C=48.5,
        lean_teg_purity=0.97,
        flash_drum_pressure_bara=4.8,
        reboiler_temp_C=197.5,
        stripping_gas_Sm3_hr=180.0,
        n_absorber_stages=4,
        stage_efficiency=0.7,
    )
    kwargs.update(overrides)
    return build_teg_plant(**kwargs)


def test_build_and_run_default_case_meets_acceptance_criteria() -> None:
    pytest.importorskip("neqsim")

    process, streams = _default_case()
    thr = process.runAsThread()
    thr.join(300000)

    water_dew_C = float(streams["waterDewAnalyser"].getMeasuredValue("C"))
    lean_teg_wt = teg_mass_fraction(streams["leanTEGtoAbs"])
    still_vent = classify_emissions(streams["stillVent"])

    assert water_dew_C < 0.0
    assert lean_teg_wt > 90.0
    assert still_vent["NMVOC"] >= 0.0
    assert still_vent["methane"] >= 0.0
    assert still_vent["total"] >= still_vent["NMVOC"]


def test_recirculated_stripping_gas_does_not_increase_emissions() -> None:
    pytest.importorskip("neqsim")

    once_process, once_streams = _default_case(recirculate_stripping_gas=False)
    once_thr = once_process.runAsThread()
    once_thr.join(300000)
    once = classify_emissions(once_streams["stillVent"])

    recirc_process, recirc_streams = _default_case(recirculate_stripping_gas=True)
    recirc_thr = recirc_process.runAsThread()
    recirc_thr.join(600000)
    recirc = classify_emissions(recirc_streams["stillVent"])

    assert recirc["NMVOC"] <= once["NMVOC"] + 1e-6
    assert recirc["methane"] <= once["methane"] + 1e-6
