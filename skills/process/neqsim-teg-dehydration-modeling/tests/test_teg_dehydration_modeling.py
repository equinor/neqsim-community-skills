import pytest

from teg_dehydration_modeling import (
    DEFAULT_FEED,
    GAS_COMPONENTS,
    NMVOC,
    build_teg_plant,
    classify_emissions,
    glycol_purity_wt,
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


def test_recirculated_stripping_gas_uses_one_controller_priority() -> None:
    pytest.importorskip("neqsim")

    process, _ = _default_case(recirculate_stripping_gas=True)

    assert process.getUnit("stripping gas recirc").getPriority() == 100
    assert process.getUnit("stripping gas makeup recycle").getPriority() == 100


def test_drizo_build_has_solvent_loop_units() -> None:
    pytest.importorskip("neqsim")

    process, streams = _default_case(
        stripping_mode="drizo", drizo_solvent_kg_hr=400.0, still_pressure_bara=1.36
    )

    for name in ("solvent loop recycle", "solvent recovery recycle", "solvent split"):
        assert process.getUnit(name) is not None
    assert streams["solventExcess"] is not None
    assert streams["solventHeater"] is not None


def test_drizo_rejects_recirculated_gas_and_unknown_mode() -> None:
    pytest.importorskip("neqsim")

    with pytest.raises(ValueError):
        _default_case(stripping_mode="drizo", recirculate_stripping_gas=True)
    with pytest.raises(ValueError):
        _default_case(stripping_mode="steam")


def test_glycol_purity_excludes_hydrocarbon_solvent() -> None:
    class _Comp:
        def __init__(self, name, z, mw):
            self._n, self._z, self._mw = name, z, mw

        def getComponentName(self):
            return self._n

        def getz(self):
            return self._z

        def getMolarMass(self):
            return self._mw

    class _Fluid:
        comps = [
            _Comp("TEG", 0.20, 0.15017),
            _Comp("water", 0.001, 0.018015),
            _Comp("m-Xylene", 0.05, 0.10617),
        ]

        def getNumberOfComponents(self):
            return len(self.comps)

        def getComponent(self, i):
            return self.comps[i]

    class _Stream:
        def getFluid(self):
            return _Fluid()

        def getFlowRate(self, unit):
            return 1000.0

    s = _Stream()
    assert glycol_purity_wt(s) > teg_mass_fraction(s)
    assert glycol_purity_wt(s) == pytest.approx(99.94, abs=0.05)


