import math
import random

import pytest

from reservoir_souring import (
    fit_well_correlation,
    h2s_ppmv_in_gas_from_mass_rate,
    load_registry,
    mixing_zone_h2s_mg_l,
    save_registry,
    seawater_fraction_from_tracer,
    seawater_fraction_multi_tracer,
    sulfate_balance_h2s_mg_l,
    update_correlation,
    water_h2s_to_well_stream_rate,
)


def test_tracer_mixing_and_clipping():
    assert seawater_fraction_from_tracer(10000.0, 30000.0, 19000.0) == 1.0
    assert seawater_fraction_from_tracer(24500.0, 30000.0, 19000.0) == pytest.approx(0.5)
    assert seawater_fraction_from_tracer(35000.0, 30000.0, 19000.0) == 0.0
    with pytest.raises(ValueError):
        seawater_fraction_from_tracer(1.0, 5.0, 5.0)


def test_multi_tracer_consistent_and_inconsistent():
    fw = {"Cl": 30000.0, "Mg": 200.0}
    sw = {"Cl": 19000.0, "Mg": 1300.0}
    good = {"Cl": 24500.0, "Mg": 750.0}
    f, rms = seawater_fraction_multi_tracer(good, fw, sw)
    assert f == pytest.approx(0.5) and rms == pytest.approx(0.0, abs=1e-9)
    bad = {"Cl": 24500.0, "Mg": 1000.0}
    _, rms_bad = seawater_fraction_multi_tracer(bad, fw, sw)
    assert rms_bad > 0.05


def _synthetic(model_fn, n=40, noise=0.02, seed=3):
    rng = random.Random(seed)
    f = [i / (n - 1) * 0.6 for i in range(n)]
    y = [max(0.0, model_fn(v) * (1.0 + rng.gauss(0, noise))) for v in f]
    return f, y


def test_fit_recovers_linear():
    f, y = _synthetic(lambda v: 120.0 * v)
    c = fit_well_correlation("A-1", f, y)
    assert c.r2 > 0.98
    assert c.predict(0.3) == pytest.approx(36.0, rel=0.1)


def test_fit_recovers_threshold_delay():
    f, y = _synthetic(lambda v: 200.0 * max(v - 0.15, 0.0))
    c = fit_well_correlation("A-2", f, y)
    assert c.model == "threshold"
    assert c.params["f0"] == pytest.approx(0.15, abs=0.05)


def test_fit_recovers_saturation():
    f, y = _synthetic(lambda v: 300.0 * v / (1 + 4.0 * v), noise=0.01)
    c = fit_well_correlation("A-3", f, y, models=["linear", "saturating"])
    assert c.model == "saturating"


def test_few_points_rejected():
    with pytest.raises(ValueError):
        fit_well_correlation("X", [0.1, 0.2], [1.0, 2.0])


def test_update_flags_shift_and_registry_round_trip(tmp_path):
    f, y = _synthetic(lambda v: 100.0 * v)
    old = fit_well_correlation("A-4", f, y)
    f2, y2 = _synthetic(lambda v: 180.0 * v, seed=5)
    new = update_correlation(old, "A-4", f2, y2)
    assert any("moved" in w for w in new.warnings)
    path = tmp_path / "reg.json"
    save_registry([new], str(path))
    back = load_registry(str(path))["A-4"]
    assert back.predict(0.4) == pytest.approx(new.predict(0.4))


def test_forgetting_tracks_recent_data():
    f = [i / 59 * 0.6 for i in range(60)]
    y = [100.0 * v if i < 30 else 200.0 * v for i, v in enumerate(f)]
    static = fit_well_correlation("A-5", f, y, models=["linear"])
    recent = update_correlation(None, "A-5", f, y, half_life_points=8, models=["linear"])
    assert recent.predict(0.6) > static.predict(0.6)


def test_mixing_zone_substrate_limits_and_temperature():
    assert mixing_zone_h2s_mg_l(0.0, 2700.0, 200.0) == 0.0
    assert mixing_zone_h2s_mg_l(1.0, 2700.0, 200.0) == 0.0
    mid = mixing_zone_h2s_mg_l(0.5, 2700.0, 200.0)
    assert mid == pytest.approx(min(0.355 * 1350.0, 0.577 * 100.0), rel=0.01)
    hot = mixing_zone_h2s_mg_l(0.5, 2700.0, 200.0, temperature_c=110.0)
    assert hot < 0.01 * mid
    assert mixing_zone_h2s_mg_l(0.5, 2700.0, 200.0, mitigation_factor=0.1) == pytest.approx(0.1 * mid)
    with pytest.raises(ValueError):
        mixing_zone_h2s_mg_l(1.2, 2700.0, 200.0)


def test_mass_balance_helpers():
    assert sulfate_balance_h2s_mg_l(2700.0, 1700.0) == pytest.approx(1000.0 * 34.081 / 96.06)
    assert sulfate_balance_h2s_mg_l(100.0, 200.0) == 0.0
    assert water_h2s_to_well_stream_rate(10.0, 5000.0) == pytest.approx(50.0)
    ppm = h2s_ppmv_in_gas_from_mass_rate(34.081, 23.64)
    assert math.isclose(ppm, 1.0e6, rel_tol=1e-6)
