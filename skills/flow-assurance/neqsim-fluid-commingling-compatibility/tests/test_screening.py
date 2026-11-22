"""Screening logic against an analytic stand-in for NeqSim."""

import json
import math

import pytest
from fluid_commingling_compatibility import (
    BlendProperties,
    EvaluationConditions,
    FluidSpec,
    FluidSpecError,
    PseudoComponent,
    ScreeningLimits,
    classify_ri_margin,
    estimate_onset_ri_from_sara,
    refractive_index_from_density,
    screen_commingling,
)

CONDITIONS = EvaluationConditions(
    commingling_pressure_bara=200.0,
    commingling_temperature_c=70.0,
    separator_pressure_bara=40.0,
    separator_temperature_c=50.0,
    hydrate_pressure_bara=100.0,
)


def host(asphaltenic=True):
    return FluidSpec(
        "host",
        {"methane": 20.0},
        [PseudoComponent("C20", 80.0, 0.28, 0.88)],
        asphaltenic=asphaltenic,
    )


def tiein(asphaltenic=False):
    return FluidSpec("tiein", {"methane": 95.0, "H2S": 0.1}, asphaltenic=asphaltenic)


class FakeEvaluator:
    """Analytic blend properties; the knobs shape each check."""

    def __init__(self, hydrate_peak=0.0, gas_from=0.6, end_gas=True):
        self.hydrate_peak = hydrate_peak
        self.gas_from = gas_from
        self.end_gas = end_gas
        self.calls = 0

    def evaluate(self, blend, conditions):
        self.calls += 1
        f = blend.fraction_b
        density = 820.0 - 160.0 * f
        gassy = f >= self.gas_from and (f < 1.0 or self.end_gas)
        return BlendProperties(
            fraction_b=f,
            saturation_pressure_bara=100.0 + 150.0 * f + 120.0 * f * (1 - f),
            phases_at_commingling=["gas", "oil"] if gassy else ["oil"],
            liquid_density_kg_m3=density,
            min_live_oil_ri=refractive_index_from_density(density - 15.0),
            min_live_oil_ri_pressure_bara=100.0 + 150.0 * f,
            de_boer_risk="NO_PROBLEM" if f < 0.5 else "MODERATE_PROBLEM",
            hydrate_temperature_c=15.0 + 3.0 * f + self.hydrate_peak * 4 * f * (1 - f),
            separator_gas_h2s_ppm=1000.0 * f,
            separator_gas_co2_mol_pct=1.0,
        )


def test_refractive_index_matches_buckley_correlation():
    # SG 0.85 -> F_RI = 0.2898*0.85 + 0.07602*0.85^2
    fri = 0.2898 * 0.85 + 0.07602 * 0.85**2
    expected = math.sqrt((1 + 2 * fri) / (1 - fri))
    assert math.isclose(refractive_index_from_density(850.0), expected)
    assert refractive_index_from_density(700.0) < refractive_index_from_density(850.0)
    assert math.isnan(refractive_index_from_density(float("nan")))
    assert math.isnan(refractive_index_from_density(-1.0))


@pytest.mark.parametrize(
    "margin, label",
    [
        (0.05, "VERY_STABLE"),
        (0.025, "STABLE"),
        (0.015, "MARGINAL"),
        (0.005, "UNSTABLE"),
        (-0.01, "HIGHLY_UNSTABLE"),
        (float("nan"), "UNKNOWN"),
    ],
)
def test_ri_classes(margin, label):
    assert classify_ri_margin(margin) == label


def test_sara_onset_is_clamped_and_validated():
    value = estimate_onset_ri_from_sara(0.6, 0.25, 0.1, 0.05)
    assert 1.42 <= value <= 1.55
    with pytest.raises(ValueError):
        estimate_onset_ri_from_sara(0.5, 0.1, 0.1, 0.0)
    with pytest.raises(ValueError):
        estimate_onset_ri_from_sara(-0.1, 0.6, 0.4, 0.1)


def test_onset_crossing_is_high_and_end_members_always_included():
    evaluator = FakeEvaluator()
    report = screen_commingling(
        host(),
        tiein(),
        CONDITIONS,
        evaluator,
        fractions=(0.25, 0.5),
        limits=ScreeningLimits(onset_ri=1.45),
    )
    assert [p.fraction_b for p in report.blends] == [0.0, 0.25, 0.5, 1.0]
    codes = {f.code: f for f in report.findings}
    assert codes["asphaltene-onset-crossed"].severity == "high"
    assert report.highest_severity == "high"
    # With a measured onset the relative indicator is not repeated.
    assert "asphaltene-dilution" not in codes
    worst = report.worst_cases["asphaltene"]
    assert worst["fraction_b"] == 0.5  # x_B = 1 carries no asphaltenes
    assert worst["delta_ri_vs_reference"] < 0


def test_relative_dilution_warning_without_onset():
    report = screen_commingling(host(), tiein(), CONDITIONS, FakeEvaluator())
    codes = {f.code for f in report.findings}
    assert "asphaltene-dilution" in codes
    assert "asphaltene-onset-crossed" not in codes
    assert report.onset_ri_source == "none"


def test_sara_supplies_onset_when_not_measured():
    report = screen_commingling(
        host(), tiein(), CONDITIONS, FakeEvaluator(), sara=(0.6, 0.25, 0.1, 0.05)
    )
    assert report.onset_ri_source == "SARA correlation"
    assert report.limits.onset_ri is not None


def test_asphaltenic_fluid_b_uses_x_one_as_reference():
    report = screen_commingling(
        host(asphaltenic=False),
        tiein(asphaltenic=True),
        CONDITIONS,
        FakeEvaluator(),
    )
    assert report.asphaltenic_side == "b"
    assert report.worst_cases["asphaltene"]["fraction_b"] > 0.0


def test_no_asphaltenic_fluid_is_reported_not_interpreted():
    report = screen_commingling(
        host(asphaltenic=False), tiein(), CONDITIONS, FakeEvaluator()
    )
    codes = {f.code for f in report.findings}
    assert "asphaltene-not-assessed" in codes
    assert "asphaltene" not in report.worst_cases


def test_de_boer_worsening_is_flagged():
    report = screen_commingling(host(), tiein(), CONDITIONS, FakeEvaluator())
    assert any(f.code == "de-boer-worse-than-host" for f in report.findings)


def test_gas_breakout_on_mixing_is_a_warning():
    report = screen_commingling(
        host(), tiein(), CONDITIONS, FakeEvaluator(gas_from=0.5, end_gas=False)
    )
    finding = next(f for f in report.findings if f.code == "free-gas-at-commingling")
    assert finding.severity == "warning"
    assert report.worst_cases["free_gas"]["first_fraction_b"] == 0.5


def test_hydrate_maximum_inside_the_blend_range():
    report = screen_commingling(
        host(),
        tiein(),
        CONDITIONS,
        FakeEvaluator(hydrate_peak=4.0),
        limits=ScreeningLimits(min_operating_temperature_c=18.0),
    )
    codes = {f.code: f for f in report.findings}
    assert "hydrate-blend-maximum" in codes
    assert codes["hydrate-margin"].severity == "high"
    assert 0.0 < report.worst_cases["hydrate"]["fraction_b"] < 1.0


def test_sour_gas_limit():
    report = screen_commingling(
        host(),
        tiein(),
        CONDITIONS,
        FakeEvaluator(),
        limits=ScreeningLimits(h2s_limit_ppm=550.0, co2_limit_mol_pct=5.0),
    )
    codes = {f.code for f in report.findings}
    assert "h2s-limit" in codes
    assert "co2-limit" not in codes


def test_saturation_nonlinearity_needs_liquid_end_members():
    liquid_ends = screen_commingling(
        host(), tiein(), CONDITIONS, FakeEvaluator(gas_from=2.0)
    )
    assert "saturation_nonlinearity" in liquid_ends.worst_cases
    gas_end = screen_commingling(host(), tiein(), CONDITIONS, FakeEvaluator())
    assert "saturation_nonlinearity" not in gas_end.worst_cases


def test_report_serialises_without_nan():
    report = screen_commingling(host(), tiein(), CONDITIONS, FakeEvaluator())
    text = json.dumps(report.to_dict(), allow_nan=False)
    assert '"calculation_basis": "screening"' in text
    markdown = report.to_markdown()
    assert "| x_B |" in markdown
    assert "n/a" in markdown  # x_B = 1 carries no asphaltenes


def test_invalid_inputs():
    with pytest.raises(FluidSpecError):
        screen_commingling(host(), tiein(), CONDITIONS, FakeEvaluator(), fractions=())
    with pytest.raises(FluidSpecError):
        screen_commingling(
            host(), tiein(), CONDITIONS, FakeEvaluator(), fractions=(0.5, 1.5)
        )
    with pytest.raises(ValueError):
        EvaluationConditions(100.0, 50.0, path_end_pressure_bara=150.0)
    with pytest.raises(ValueError):
        EvaluationConditions(100.0, 50.0, separator_pressure_bara=30.0)
    with pytest.raises(ValueError):
        ScreeningLimits(onset_ri=2.0)


def test_path_pressures_span_the_range():
    pressures = EvaluationConditions(200.0, 60.0, 20.0, 4).path_pressures()
    assert pressures[0] == 200.0 and pressures[-1] == 20.0 and len(pressures) == 4
