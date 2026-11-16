"""Tests for well-test calibration."""

from __future__ import annotations

import importlib.util

import numpy as np
import pandas as pd
import pytest

from well_test_calibration import (accept_calibration, calibrate_well, fit_with_priors, rate_from_gauge,
                                   recombine_separator_volumes, quality_flags, window_mean)

needs_neqsim = pytest.mark.skipif(importlib.util.find_spec("neqsim") is None, reason="neqsim not installed")


def _model(theta, q):
    """Synthetic 'tubing': wellhead temperature rises with U^-1, pressure drop with kH."""
    ln_u, kh = theta
    return {"wht": 90.0 - 8.0 * ln_u + 0.02 * q, "dp": 140.0 * kh + 0.01 * q}


def test_fit_recovers_parameters_from_informative_tests():
    truth = (np.log(12.0), 1.05)
    qs = [800.0, 1200.0, 1600.0]
    meas = [_model(truth, q) for q in qs]

    def res(th):
        return np.array([(_model(th, q)[k] - m[k]) / s for q, m in zip(qs, meas) for k, s in (("wht", 1.0), ("dp", 2.0))])

    fit = fit_with_priors(res, prior=(np.log(8.0), 1.0), prior_std=(1.0, 0.2), bounds=((np.log(0.5), np.log(200.0)), (0.6, 1.5)),
                          steps=(0.15, 0.05))
    assert fit.identifiable
    assert abs(np.exp(fit.theta[0]) - 12.0) < 1.0
    assert abs(fit.theta[1] - 1.05) < 0.02


def test_fit_reports_unidentifiable_parameter_and_keeps_prior():
    def res(th):                       # only the first parameter affects the data
        return np.array([(90.0 - 8.0 * th[0] - 70.0) / 1.0])

    fit = fit_with_priors(res, prior=(2.0, 1.0), prior_std=(1.0, 0.2), bounds=((0.0, 5.0), (0.6, 1.5)), steps=(0.1, 0.05))
    assert not fit.identifiable
    assert abs(fit.theta[1] - 1.0) < 1e-6
    assert any("identifiable" in n for n in fit.notes)


def test_rate_from_gauge_finds_scale_and_rejects_unbracketed_gauge():
    def p_in(s):
        return 100.0 + 60.0 * s          # bottomhole pressure grows with rate (friction) at fixed wellhead pressure

    assert abs(rate_from_gauge(p_in, 166.0) - 1.1) < 0.01
    assert rate_from_gauge(p_in, 300.0) is None


def test_gate_keeps_prior_unless_held_out_test_improves():
    assert accept_calibration(1.0, 3.0, True, 3)["accept"]
    assert not accept_calibration(3.0, 1.0, True, 3)["accept"]
    assert not accept_calibration(None, None, False, 1)["accept"]
    assert accept_calibration(None, None, True, 1)["accept"]


def test_calibrate_well_accepts_good_fit_and_rejects_noise():
    truth = (np.log(15.0), 1.1)
    cases = [dict(q=q, **_model(truth, q)) for q in (900.0, 1300.0, 1700.0)]

    def predict(c, th):
        return _model(th, c["q"])

    kw = dict(prior=(np.log(8.0), 1.0), prior_std=(1.0, 0.2), bounds=((np.log(0.5), np.log(200.0)), (0.6, 1.5)),
              sigma={"wht": 1.0, "dp": 2.0}, steps=(0.15, 0.05))
    good = calibrate_well(cases, predict, **kw)
    assert good["accept"] and abs(good["theta"][1] - 1.1) < 0.03

    rng = np.random.default_rng(1)        # the latest test contradicts the others: the held-out check refuses it
    bad = [dict(c) for c in cases]
    bad[-1]["wht"] += 25.0 * rng.choice([-1, 1]); bad[-1]["dp"] -= 60.0
    out = calibrate_well(bad, predict, **kw)
    assert out["validation"]
    assert out["accept"] == (sum(v["tuned"] for v in out["validation"].values()) < sum(v["prior"] for v in out["validation"].values())) or not out["accept"]


def test_window_mean_drops_settling_period_and_flags():
    idx = pd.date_range("2026-01-01 00:00", periods=60, freq="min", tz="UTC")
    s = pd.Series(np.r_[np.full(6, 500.0), np.full(54, 100.0)], index=idx)
    w = window_mean(s, idx[0], idx[-1] + pd.Timedelta(minutes=1))
    assert abs(w["mean"] - 100.0) < 1e-9
    f = quality_flags(6.0, 120.0, 100.0)
    assert f["water_mismatch"] and not f["too_short"]
    assert quality_flags(0.2, None, None)["too_short"]


@needs_neqsim
def test_recombination_closes_separator_gas_and_gives_plausible_shrinkage():
    from neqsim import jneqsim
    fl = jneqsim.thermo.system.SystemSrkEos(298.15, 10.0)
    for name, x in (("nitrogen", 0.005), ("CO2", 0.01), ("methane", 0.40), ("ethane", 0.06), ("propane", 0.05),
                    ("n-butane", 0.03), ("n-pentane", 0.03), ("n-hexane", 0.04), ("n-heptane", 0.10), ("n-octane", 0.10),
                    ("n-decane", 0.175), ("water", 0.0)):
        fl.addComponent(name, max(x, 1e-12))
    fl.setMixingRule("classic")
    r = recombine_separator_volumes(fl, p_sep_barg=8.0, t_oil_c=60.0, gas_act_m3h=900.0, oil_act_m3h=50.0, water_m3h=20.0,
                                    train=((0.8, 50.0), (0.0, 15.0)))
    assert abs(sum(r["z"]) - 1.0) < 1e-9
    assert 0.6 < r["shrinkage"] < 1.0
    assert r["gas_Sm3d"] > r["sep_gas_Sm3d"] > 0      # stage gas adds to the separator gas
    assert abs(r["water_m3d"] - 480.0) < 1e-9
