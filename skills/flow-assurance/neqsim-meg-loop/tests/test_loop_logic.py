"""Input validation, Hammerschmidt and findings logic (no Java)."""

import json
import math

import pytest
from meg_loop import (
    HydrateDesign,
    MegInputError,
    MegReport,
    Regeneration,
    WellStream,
    hammerschmidt_wt_fraction,
)
from meg_loop.loop import _findings

DESIGN = HydrateDesign(pressure_bara=150.0, min_temperature_c=4.0, margin_c=3.0)


def make(results, regen=None):
    report = MegReport(DESIGN, regen or Regeneration(), results, [])
    _findings(report)
    return report


def codes(report):
    return {f.code for f in report.findings}


def test_hammerschmidt_round_trip():
    w = hammerschmidt_wt_fraction(8.955)
    assert w == pytest.approx(0.30, abs=0.001)
    dt = 1297.0 * (w * 100) / (62.07 * (100 - w * 100))
    assert dt == pytest.approx(8.955, rel=1e-9)
    assert hammerschmidt_wt_fraction(0.0) == 0.0
    assert hammerschmidt_wt_fraction(-2.0) == 0.0


def test_target_temperature():
    assert DESIGN.target_temperature_c == pytest.approx(1.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"flow_rate": 0.0},
        {"formation_water_m3_d": -1.0},
        {"components": {"methane": 1.0, "MEG": 0.1}},
        {"components": {"methane": -1.0}},
    ],
)
def test_stream_validation(kwargs):
    base = {"components": {"methane": 1.0}, "flow_rate": 1.0}
    with pytest.raises(MegInputError):
        WellStream(**{**base, **kwargs})


@pytest.mark.parametrize(
    "kwargs",
    [
        {"lean_meg_wt": 1.0},
        {"lean_meg_wt": 0.4},
        {"reclaimer_slipstream": 1.5},
        {"salt_limit_wt": 0.0},
        {"lean_alternatives": (0.3,)},
    ],
)
def test_regeneration_validation(kwargs):
    with pytest.raises(MegInputError):
        Regeneration(**kwargs)


def test_design_validation():
    with pytest.raises(MegInputError):
        HydrateDesign(pressure_bara=0.0, min_temperature_c=4.0)
    with pytest.raises(MegInputError):
        HydrateDesign(pressure_bara=100.0, min_temperature_c=4.0, margin_c=-1.0)


def test_no_inhibition_needed():
    report = make({"uninhibited_hydrate_c": -2.0, "lean_meg_kg_h": 0.0})
    assert codes(report) == {"no-inhibition-needed"}
    assert report.highest_severity == "info"


def test_target_not_reached():
    report = make({"uninhibited_hydrate_c": 20.0, "lean_meg_kg_h": math.nan})
    assert codes(report) == {"target-not-reached"}
    assert report.highest_severity == "high"


def base_results(**extra):
    return {
        "uninhibited_hydrate_c": 22.0,
        "lean_meg_kg_h": 3000.0,
        "rich_meg_wt_pct": 49.0,
        "hammerschmidt_wt_pct": 50.0,
        "meg_loss_kg_d": 10.0,
        "salt_in_kg_d": 1200.0,
        **extra,
    }


def test_salt_accumulation_with_insufficient_slipstream():
    report = make(
        base_results(min_slipstream_pct=36.0, days_to_salt_limit=7.0),
        Regeneration(reclaimer_slipstream=0.30),
    )
    assert {"salt-accumulation", "divalent-salts", "meg-losses"} <= codes(report)
    assert report.highest_severity == "high"


def test_salt_ok_with_enough_slipstream():
    report = make(
        base_results(min_slipstream_pct=36.0, days_to_salt_limit=7.0),
        Regeneration(reclaimer_slipstream=0.40),
    )
    assert "salt-accumulation" not in codes(report)
    assert "divalent-salts" in codes(report)


def test_no_reclaimer_slow_build_up_is_warning():
    report = make(
        base_results(min_slipstream_pct=2.0, days_to_salt_limit=900.0),
        Regeneration(reclaimer_slipstream=0.0),
    )
    salt = next(f for f in report.findings if f.code == "salt-accumulation")
    assert salt.severity == "warning"


def test_hammerschmidt_deviation_and_high_rich():
    report = make(base_results(rich_meg_wt_pct=75.0, hammerschmidt_wt_pct=60.0))
    assert {"hammerschmidt-deviation", "high-rich-meg"} <= codes(report)


def test_dict_and_markdown_are_clean():
    report = make(base_results(reboiler_duty_kw=math.nan))
    report.alternatives.append(
        {
            "lean_meg_wt": 0.8,
            "lean_meg_kg_h": 3600.0,
            "rich_meg_wt_pct": 49.0,
            "reboiler_duty_kw": math.nan,
        }
    )
    data = report.to_dict()
    json.dumps(data, allow_nan=False)
    assert data["results"]["reboiler_duty_kw"] is None
    assert data["calculation_basis"] == "screening"
    text = report.to_markdown()
    assert "Lean MEG injection (kg/h) | 3000" in text
    assert "| 80 | 3600 | 49.0 | - |" in text
