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
