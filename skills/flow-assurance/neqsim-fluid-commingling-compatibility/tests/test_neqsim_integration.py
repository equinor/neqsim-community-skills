"""Runs the real NeqSim backend; skipped when neqsim is not installed."""

import math

import pytest

pytest.importorskip("neqsim")

from fluid_commingling_compatibility import (
    EvaluationConditions,
    FluidSpec,
    NeqSimBlendEvaluator,
    PseudoComponent,
    ScreeningLimits,
    blend,
    screen_commingling,
)


@pytest.fixture(scope="module", autouse=True)
def _keep_jvm_alive_at_exit():
    """Skip JVM teardown at interpreter exit.

    JPype can segfault in its exit-time JVM shutdown after NeqSim has run in
    the same pytest session as other test directories. The tests have finished
    by then; this only avoids a spurious non-zero exit code.
    """
    import jpype.config

    jpype.config.destroy_jvm = False
    yield


HOST = FluidSpec(
    "host",
    {"methane": 18.0, "ethane": 6.0, "propane": 5.0, "n-butane": 3.0, "CO2": 1.0},
    [
        PseudoComponent("C10", 20.0, 0.14, 0.80),
        PseudoComponent("C15", 14.0, 0.21, 0.85),
        PseudoComponent("C30", 20.0, 0.45, 0.93),
    ],
    asphaltenic=True,
)
CONDENSATE = FluidSpec(
    "tiein",
    {"methane": 80.0, "ethane": 8.0, "propane": 5.0, "CO2": 2.5, "H2S": 0.05},
    [PseudoComponent("C7", 4.0, 0.098, 0.74)],
)
CONDITIONS = EvaluationConditions(
    commingling_pressure_bara=200.0,
    commingling_temperature_c=80.0,
    path_end_pressure_bara=20.0,
    path_points=6,
)


@pytest.fixture(scope="module")
def evaluator():
    return NeqSimBlendEvaluator()


def test_condensate_raises_bubble_point_and_lowers_ri(evaluator):
    base = evaluator.evaluate(blend(HOST, CONDENSATE, 0.0), CONDITIONS)
    mixed = evaluator.evaluate(blend(HOST, CONDENSATE, 0.3), CONDITIONS)
    assert math.isfinite(base.saturation_pressure_bara)
    assert mixed.saturation_pressure_bara > base.saturation_pressure_bara
    assert mixed.liquid_density_kg_m3 < base.liquid_density_kg_m3
    assert mixed.min_live_oil_ri < base.min_live_oil_ri
    # The minimum sits at (just above) the bubble point.
    assert base.min_live_oil_ri_pressure_bara == pytest.approx(
        base.saturation_pressure_bara, abs=1.0
    )
    assert base.de_boer_risk in (
        "NO_PROBLEM",
        "SLIGHT_PROBLEM",
        "MODERATE_PROBLEM",
        "SEVERE_PROBLEM",
    )


def test_hydrate_and_separator_checks(evaluator):
    conditions = EvaluationConditions(
        200.0,
        80.0,
        20.0,
        4,
        separator_pressure_bara=40.0,
        separator_temperature_c=50.0,
        hydrate_pressure_bara=100.0,
    )
    props = evaluator.evaluate(blend(HOST, CONDENSATE, 0.5), conditions)
    assert props.free_water_assumed
    assert 5.0 < props.hydrate_temperature_c < 30.0
    assert props.separator_gas_h2s_ppm > 0
    assert props.separator_gas_co2_mol_pct > 0


def test_full_sweep_flags_onset(evaluator):
    report = screen_commingling(
        HOST,
        CONDENSATE,
        CONDITIONS,
        evaluator,
        fractions=(0.0, 0.3, 0.6, 1.0),
        limits=ScreeningLimits(onset_ri=1.445),
    )
    assert report.blends[0].min_live_oil_ri > 1.445
    assert any(f.code == "asphaltene-onset-crossed" for f in report.findings)


def test_molar_mass_from_neqsim(evaluator):
    heavy = evaluator.molar_mass_kg_mol(HOST)
    light = evaluator.molar_mass_kg_mol(CONDENSATE)
    assert 0.08 < heavy < 0.4
    assert 0.016 < light < heavy
