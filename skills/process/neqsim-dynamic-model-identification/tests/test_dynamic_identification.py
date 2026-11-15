"""Tests for dynamic model identification."""

from __future__ import annotations

import json
import math

import numpy as np
import pandas as pd
import pytest

from dynamic_identification import align, find_assemblies, frozen_mask, run_identification, saturation
from dynamic_identification.__main__ import main

needs_tsa = pytest.mark.skipif(find_assemblies() is None, reason="TimeSeriesAnalysis assemblies not installed")


def _series(values, start="2026-01-01", step_s=1.0):
    index = pd.date_range(start, periods=len(values), freq=pd.to_timedelta(step_s, unit="s"), tz="UTC")
    return pd.Series(np.asarray(values, dtype=float), index=index)


def _closed_loop(n=1500, dt=1.0, gain=1.5, tau=20.0, delay=4, kp=0.4, ti=25.0, seed=3):
    rng = np.random.default_rng(seed)
    sp = np.full(n, 50.0)
    sp[400:], sp[1000:] = 55.0, 52.0
    dist = np.zeros(n)
    dist[700:] = 3.0
    y, u = np.zeros(n), np.zeros(n)
    x = integral = 0.0
    a = math.exp(-dt / tau)
    history = [30.0] * (delay + 1)
    y0 = 5 + gain * 30
    for i in range(n):
        error = sp[i] - (y[i - 1] if i else y0)
        integral += error * dt / ti
        u[i] = min(100.0, max(0.0, 30.0 + kp * (error + integral)))
        history.append(u[i])
        x = a * x + (1 - a) * gain * (history[-1 - delay] - 30.0)
        y[i] = y0 + x + dist[i] + rng.normal(0, 0.03)
    return y, sp, u


def test_align_holds_on_change_tags_and_masks_frozen_values():
    fast = _series(np.sin(np.arange(100) / 5.0))
    frozen = np.arange(100, dtype=float)
    frozen[40:60] = 7.0
    sparse = pd.Series([1.0, 2.0], index=pd.DatetimeIndex(["2026-01-01T00:00:00", "2026-01-01T00:00:50"], tz="UTC"))
    data = align({"y": fast, "f": _series(frozen), "sp": sparse}, frozen_samples=10, hold=["sp"])
    assert data["timebase_s"] == 1.0
    assert data["bad_fraction"]["sp"] == 0.0
    assert data["values"]["sp"][49] == 1.0 and data["values"]["sp"][50] == 2.0
    assert np.isnan(data["values"]["f"][45]) and not np.isnan(data["values"]["f"][30])
    assert frozen_mask(np.array([1, 1, 1, 2.0]), 3).tolist() == [True, True, True, False]
    stats = saturation(np.array([0.0, 0.1, 50, 100, 99.8, np.nan]), 0, 100)
    assert stats["at_min_fraction"] == pytest.approx(0.4) and stats["at_max_fraction"] == pytest.approx(0.4)


@needs_tsa
def test_open_loop_unit_model_recovers_gain_time_constant_and_delay():
    from dynamic_identification import identify_unit

    n, dt = 600, 1.0
    u = np.where(np.arange(n) < 100, 0.0, 1.0) + np.where(np.arange(n) >= 350, 0.5, 0.0)
    y, state, a = np.zeros(n), 0.0, math.exp(-1.0 / 30.0)
    for i in range(n):
        state = a * state + (1 - a) * 2.0 * u[max(i - 5, 0)]
        y[i] = 10.0 + state
    y += np.random.default_rng(1).normal(0, 0.02, n)
    y[300:305] = np.nan
    result = identify_unit(y, {"u": u}, dt)
    assert result["gains"]["u"] == pytest.approx(2.0, rel=0.05)
    assert result["time_constant_s"] == pytest.approx(30.0, rel=0.2)
    assert result["time_delay_s"] == pytest.approx(5.0, abs=2.0)


@needs_tsa
def test_pid_and_closed_loop_identification(tmp_path, capsys):
    y, sp, u = _closed_loop()
    folder = tmp_path / "data"
    folder.mkdir()
    for name, values in (("pv", y), ("sp", sp), ("out", u)):
        frame = pd.DataFrame({"time": _series(values).index.strftime("%Y-%m-%dT%H:%M:%SZ"), "value": values})
        frame.to_csv(folder / f"{name}.csv", index=False)
    config = {"series": {k: {"path": str(folder / f"{k}.csv")} for k in ("pv", "sp", "out")},
              "analyses": {"loop": {"pv": "pv", "sp": "sp", "out": "out", "out_range": [0, 100]}},
              "out_dir": str(tmp_path / "out")}
    config["series"]["sp"]["hold"] = True
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    assert main(["run", str(path)]) == 0
    assert "status=ok" in capsys.readouterr().out
    evidence = json.loads((tmp_path / "out" / "identification_evidence.json").read_text(encoding="utf-8"))
    pid = evidence["results"]["loop"]["pid"]
    assert pid["usable"] and pid["kp"] == pytest.approx(0.4, rel=0.1) and pid["ti_s"] == pytest.approx(25, rel=0.2)
    process = evidence["results"]["loop"]["process_closed_loop"]
    assert process["gains"]["controller_output"] == pytest.approx(1.5, rel=0.2)
    assert process["time_constant_s"] == pytest.approx(20.0, rel=0.3)
    assert (tmp_path / "out" / "identification.png").exists()


@needs_tsa
def test_flat_data_is_reported_unusable(tmp_path):
    rng = np.random.default_rng(0)
    pv = 49.0 + rng.normal(0, 0.01, 400)
    files = {}
    for name, values in (("pv", pv), ("sp", np.full(400, 49.0)), ("out", 80.0 + rng.normal(0, 0.01, 400))):
        files[name] = tmp_path / f"{name}.csv"
        pd.DataFrame({"time": _series(values, step_s=3600).index, "avg": values}).to_csv(files[name], index=False)
    evidence = run_identification({"series": {k: {"path": str(p)} for k, p in files.items()},
                                   "analyses": {"loop": {"pv": "pv", "sp": "sp", "out": "out"}}})
    assert any("setpoint never changes" in w for w in evidence["warnings"])
    loop = evidence["results"]["loop"]
    assert not (loop["pid"]["usable"] and loop["process_closed_loop"]["usable"])


def test_missing_file_blocks(tmp_path):
    evidence = run_identification({"series": {"pv": {"path": str(tmp_path / "nope.csv")}}})
    assert evidence["status"] == "blocked" and "pv" in evidence["missing"][0]


@needs_tsa
def test_neqsim_physics_checks_identified_dynamics_and_separates_faults():
    pytest.importorskip("neqsim")
    from neqsim import jneqsim

    from dynamic_identification import identify_unit
    from dynamic_identification.neqsim_bridge import (automation_evaluator, compare_gains, physics_residuals,
                                                      simulate_unit, steady_gains, two_residual_diagnosis)

    gas = jneqsim.thermo.system.SystemSrkEos(298.15, 30.0)
    for name, x in (("methane", 0.9), ("ethane", 0.07), ("propane", 0.03)):
        gas.addComponent(name, x)
    gas.setMixingRule("classic")
    feed = jneqsim.process.equipment.stream.Stream("feed", gas)
    feed.setFlowRate(20.0, "kg/sec")
    comp = jneqsim.process.equipment.compressor.Compressor("comp", feed)
    comp.setOutletPressure(90.0, "bara")
    comp.setPolytropicEfficiency(0.78)
    comp.setUsePolytropicCalc(True)
    process = jneqsim.process.processmodel.ProcessSystem()
    process.add(feed)
    process.add(comp)
    process.run()
    evaluate = automation_evaluator(process, {"flow": "feed.flowRate|kg/sec", "ps": "feed.pressure|bara",
                                              "eta": "comp.polytropicEfficiency|"},
                                    {"power": "comp.power|kW", "tout": "comp.outletStream.temperature|C"})
    physics = steady_gains(evaluate, {"flow": 20.0, "ps": 30.0}, {"flow": 0.5, "ps": 0.5}, ["power"])
    assert physics["relative_step_error"] < 0.03
    gains = physics["gains"]["power"]
    assert gains["flow"] > 0 > gains["ps"]

    # Historian from the NeqSim steady map through a 60 s lag; identification must agree with NeqSim.
    n, dt, tau = 600, 10.0, 60.0
    rng = np.random.default_rng(5)
    flow = 20 + np.repeat(rng.uniform(-2, 2, n // 60 + 1), 60)[:n]
    press = 30 + np.repeat(rng.uniform(-2, 2, n // 90 + 1), 90)[:n]
    static = 4400.0 + gains["flow"] * (flow - 20) + gains["ps"] * (press - 30)
    y, a = np.empty(n), math.exp(-dt / tau)
    y[0] = static[0]
    for k in range(1, n):
        y[k] = a * y[k - 1] + (1 - a) * static[k]
    y += rng.normal(0, 5, n)
    model = identify_unit(y[:400], {"flow": flow[:400], "ps": press[:400]}, dt, estimate_delay=False)
    assert model["method"] == "linear" and model["time_constant_s"] == pytest.approx(55.0, rel=0.2)
    assert compare_gains(model["gains"], gains, tolerance=0.1)["all_consistent"]
    replay = simulate_unit(model, {"flow": flow, "ps": press}, dt)
    assert np.sqrt(np.mean((replay[400:] - y[400:]) ** 2)) < 30.0

    # An efficiency drop moves power and temperature; a meter bias moves power alone.
    w = 90
    f2, p2 = 20 + 2 * np.sin(np.arange(w) / 7), 30 + 2 * np.cos(np.arange(w) / 11)
    expected = np.array([[evaluate({"flow": f, "ps": p, "eta": 0.78})[k] for k in ("power", "tout")]
                         for f, p in zip(f2, p2)])
    observed = expected.copy()
    for i in range(55, 70):
        point = evaluate({"flow": f2[i], "ps": p2[i], "eta": 0.73})
        observed[i] = [point["power"], point["tout"]]
    observed += rng.normal(size=(w, 2)) * [20, 0.1]
    observed[78:, 0] += 400
    res = physics_residuals({"power": observed[:, 0], "tout": observed[:, 1]},
                            {"power": expected[:, 0], "tout": expected[:, 1]}, slice(0, 40))
    labels = two_residual_diagnosis(res["power"]["flag"], res["tout"]["flag"])
    assert labels[65].startswith("physical") and labels[85].startswith("measurement")
    assert labels[30] == "within baseline"


def test_step_forecast_recovers_timing_and_beats_persistence():
    from dynamic_identification.step_prediction import (detect_steps, fit_step_dynamics, fopdt_step,
                                                        hybrid_step_forecast, pooled_dynamics, score_forecast)

    rng = np.random.default_rng(7)
    t = np.arange(-7200.0, 21600.0 + 1.0, 300.0)
    fits = []
    for dy in (1.5, -2.0, 0.8):
        y = 60.0 + fopdt_step(t, dy, 1800.0, 600.0) + rng.normal(0.0, 0.1, t.size)
        fits.append(fit_step_dynamics(t, y))
    for f, dy in zip(fits, (1.5, -2.0, 0.8)):
        assert f["dy"] == pytest.approx(dy, abs=0.15) and f["snr"] > 3.0
    dyn = pooled_dynamics(fits)
    assert dyn["tau_s"] == pytest.approx(1800.0, rel=0.35) and dyn["delay_s"] == pytest.approx(600.0, abs=300.0)

    y = 60.0 + fopdt_step(t, -1.2, 1800.0, 600.0) + rng.normal(0.0, 0.1, t.size)
    fc = hybrid_step_forecast(60.0, -1.1, dyn["tau_s"], dyn["delay_s"], horizon_s=21600.0, timebase_s=300.0)
    assert fc["y_final"] == pytest.approx(58.9) and fc["t95_s"] > fc["t63_s"]
    s = score_forecast(y[t >= 0], fc["y"], 60.0)
    assert s["skill"] > 0.5 and s["sign_agrees"]
    with pytest.raises(ValueError):
        pooled_dynamics([{"snr": 1.0, "tau_s": 1.0, "delay_s": 0.0}])

    idx = pd.date_range("2026-01-01", periods=200, freq="5min")
    moves = pd.DataFrame({"w1": np.r_[np.full(100, 30.0), np.full(100, 22.0)], "w2": np.full(200, 40.0)}, index=idx)
    steps = detect_steps(moves, min_step=3.0, step_samples=6, quiet_before=24, quiet_after=72)
    assert len(steps) == 1 and steps[0]["variable"] == "w1" and steps[0]["du"] == pytest.approx(-8.0)
    moves.loc[idx[110], "w2"] = 45.0
    assert detect_steps(moves, min_step=3.0, step_samples=6, quiet_before=24, quiet_after=72) == []
