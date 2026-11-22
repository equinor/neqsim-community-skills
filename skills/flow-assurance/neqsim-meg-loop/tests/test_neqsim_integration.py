"""Real NeqSim MEG loop; skipped without neqsim."""

import math

import pytest

pytest.importorskip("neqsim")

from meg_loop import (
    HydrateDesign,
    Regeneration,
    WellStream,
    assess_meg_loop,
    hammerschmidt_wt_fraction,
)
from meg_loop.loop import _Model, _regeneration


@pytest.fixture(scope="module", autouse=True)
def _keep_jvm_alive_at_exit():
    """Skip JPype's exit-time JVM teardown (avoids a spurious exit 139)."""
    import jpype.config

    jpype.config.destroy_jvm = False
    yield


GAS = {
    "nitrogen": 1.0,
    "CO2": 2.0,
    "methane": 85.0,
    "ethane": 6.0,
    "propane": 3.0,
    "n-butane": 1.0,
    "water": 0.6,
}
STREAM = WellStream(
    GAS, flow_rate=8.0, formation_water_m3_d=20.0, formation_water_tds_mg_l=60000.0
)
DESIGN = HydrateDesign(
    pressure_bara=150.0,
    min_temperature_c=4.0,
    margin_c=3.0,
    arrival_pressure_bara=60.0,
    arrival_temperature_c=15.0,
)


@pytest.fixture(scope="module")
def report():
    regen = Regeneration(reclaimer_slipstream=0.30, lean_alternatives=(0.80,))
    return assess_meg_loop(STREAM, DESIGN, regen)


def test_rate_meets_hydrate_target(report):
    r = report.results
    assert r["uninhibited_hydrate_c"] > 15.0
    assert r["lean_meg_kg_h"] > 0
    assert r["inhibited_hydrate_c"] == pytest.approx(
        DESIGN.target_temperature_c, abs=0.1
    )


def test_rich_meg_agrees_with_hammerschmidt(report):
    r = report.results
    assert r["rich_meg_wt_pct"] == pytest.approx(r["hammerschmidt_wt_pct"], abs=5.0)


def test_mass_balance_and_regeneration(report):
    r = report.results
    lean_kg_h = r["lean_meg_kg_h"]
    produced_water = r["free_water_kg_h"]
    # Water boiled off equals the produced free water (lean water is recycled).
    assert r["water_evaporated_kg_h"] == pytest.approx(produced_water, rel=0.05)
    rich = lean_kg_h * 0.9 / (lean_kg_h + produced_water) * 100.0
    assert r["rich_meg_wt_pct"] == pytest.approx(rich, abs=2.0)
    assert 130.0 < r["reboiler_temperature_c"] < 155.0
    kj_per_kg = r["reboiler_duty_kw"] / (r["water_evaporated_kg_h"] / 3600.0)
    assert 2300.0 < kj_per_kg < 3200.0


def test_salt_balance(report):
    r = report.results
    assert r["salt_in_kg_d"] == pytest.approx(20.0 * 60.0, rel=1e-9)
    lean_kg_d = r["lean_meg_kg_h"] * 24.0
    assert r["steady_salt_wt_pct"] == pytest.approx(
        1200.0 / (0.3 * lean_kg_d) * 100, rel=1e-6
    )
    assert r["min_slipstream_pct"] == pytest.approx(
        1200.0 / (0.05 * lean_kg_d) * 100, rel=1e-6
    )


def test_lower_lean_needs_more_injection(report):
    alt = report.alternatives[0]
    assert alt["lean_meg_wt"] == 0.80
    assert alt["lean_meg_kg_h"] > report.results["lean_meg_kg_h"]
    assert alt["rich_meg_wt_pct"] == pytest.approx(
        report.results["rich_meg_wt_pct"], abs=1.0
    )


def test_pure_methane_depression_tracks_hammerschmidt():
    model = _Model(WellStream({"methane": 99.0, "water": 1.0}, flow_rate=1.0))
    base = model.hydrate_c(0.0, 0.9, 100.0)
    water_kg_s = model.arrival(0.0, 0.9, HydrateDesign(100.0, 4.0))["free_water_kg_s"]
    lean = water_kg_s * 0.3 / (0.9 - 0.3)  # gives about 30 wt % in the water
    depression = base - model.hydrate_c(lean, 0.9, 100.0)
    assert hammerschmidt_wt_fraction(depression) == pytest.approx(0.30, abs=0.04)


def test_regeneration_bubble_point_rises_with_lean():
    regen = Regeneration(regenerator_pressure_bara=1.01325)
    _, t90, _ = _regeneration(0.9, 0.9, regen, 0.90)
    _, t80, _ = _regeneration(0.9, 0.9, regen, 0.80)
    assert t90 > t80
    assert math.isfinite(t90)


def test_dry_gas_needs_no_meg():
    dry = WellStream({"methane": 1.0, "water": 1e-6}, flow_rate=1.0)
    rep = assess_meg_loop(
        dry, HydrateDesign(100.0, 4.0), Regeneration(lean_alternatives=())
    )
    assert rep.results["lean_meg_kg_h"] == 0.0
    assert {f.code for f in rep.findings} == {"no-inhibition-needed"}
