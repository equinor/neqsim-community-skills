"""Calibrated asphaltene onset: findings logic (no Java) and NeqSim integration."""

import math

import pytest
from fluid_commingling_compatibility import (
    BlendProperties,
    EvaluationConditions,
    FluidSpec,
    FluidSpecError,
    MeasuredOnset,
    OnsetResult,
    PseudoComponent,
    blend,
    screen_commingling,
    size_asymmetry_kij,
)

CONDITIONS = EvaluationConditions(
    commingling_pressure_bara=200.0,
    commingling_temperature_c=70.0,
)


def host():
    return FluidSpec(
        "host",
        {"methane": 20.0},
        [PseudoComponent("C20", 80.0, 0.28, 0.88)],
        asphaltenic=True,
    )


def tiein():
    return FluidSpec("tiein", {"methane": 95.0})


class FakeEvaluator:
    """Minimal analytic blend properties."""

    def evaluate(self, blend, conditions):
        f = blend.fraction_b
        return BlendProperties(
            fraction_b=f,
            saturation_pressure_bara=100.0 + 150.0 * f,
            phases_at_commingling=["oil"],
            liquid_density_kg_m3=820.0 - 160.0 * f,
            min_live_oil_ri=1.48 - 0.05 * f,
            min_live_oil_ri_pressure_bara=100.0 + 150.0 * f,
        )


def asph_host(with_critical=True):
    crit = (1015.0, 15.7, 1.5) if with_critical else ()
    return FluidSpec(
        "host",
        {
            "methane": 30.0,
            "ethane": 7.0,
            "propane": 5.0,
            "n-butane": 3.0,
            "n-hexane": 3.0,
        },
        [
            PseudoComponent("C10", 15.0, 0.14, 0.79),
            PseudoComponent("C20", 15.0, 0.28, 0.86),
            PseudoComponent("C40", 12.0, 0.56, 0.93),
            PseudoComponent("Asphaltene", 0.3, 1.0, 1.15, *crit),
        ],
        asphaltenic=True,
    )


def condensate():
    return FluidSpec(
        "cond",
        {
            "methane": 72.0,
            "ethane": 9.0,
            "propane": 6.0,
            "n-butane": 3.0,
            "n-hexane": 2.0,
        },
        [PseudoComponent("C10", 2.0, 0.14, 0.79)],
    )


class FakeModel:
    """Onset rises linearly with the fraction of fluid B."""

    backend = "fake"

    def __init__(self, base=150.0, slope=80.0, measured_t=70.0, unstable_from=None):
        self.measured = MeasuredOnset(measured_t, base)
        self.base, self.slope, self.unstable_from = base, slope, unstable_from

    def onset(self, blend, temperature_c, max_p, min_p, step):
        f = blend.fraction_b
        if self.unstable_from is not None and f >= self.unstable_from:
            return OnsetResult(math.nan, math.nan, True)
        return OnsetResult(self.base + self.slope * f, math.nan, False)


def run(model, fractions=(0.25, 0.5, 0.75)):
    return screen_commingling(
        host(), tiein(), CONDITIONS, FakeEvaluator(), fractions, asphaltene_model=model
    )


def codes(report):
    return {f.code for f in report.findings}


def test_pseudo_component_critical_properties_validation():
    PseudoComponent("A", 1.0, 1.0, 1.15, 1015.0, 15.7, 1.5)
    with pytest.raises(FluidSpecError):
        PseudoComponent("A", 1.0, 1.0, 1.15, 1015.0, None, 1.5)
    with pytest.raises(FluidSpecError):
        PseudoComponent("A", 1.0, 1.0, 1.15, 5000.0, 15.7, 1.5)


def test_blend_carries_critical_properties():
    b = blend(asph_host(), condensate(), 0.3)
    asph = next(p for p in b.pseudo_components if "Asphaltene" in p.name)
    assert asph.critical_temperature_k == 1015.0
    assert asph.mole_fraction > 0
    dry = next(p for p in b.without_water().pseudo_components if "Asphaltene" in p.name)
    assert dry.acentric_factor == 1.5


def test_size_asymmetry_kij():
    assert size_asymmetry_kij(10.0, 10.0, 1.0) == pytest.approx(0.0)
    big = 1015.0 / 15.7
    assert size_asymmetry_kij(big, 190.6 / 46.0, 1.0) > size_asymmetry_kij(
        big, 507.6 / 30.25, 1.0
    )


def test_onset_reaching_commingling_pressure_is_high():
    report = run(FakeModel(base=150.0, slope=80.0))
    assert "asphaltene-eos-onset-at-commingling" in codes(report)
    assert report.highest_severity == "high"
    worst = report.worst_cases["asphaltene_eos"]
    assert worst["reference_onset_bara"] == pytest.approx(150.0)
    assert "| 150.0 |" in report.to_markdown()


def test_raised_onset_below_commingling_is_warning():
    report = run(FakeModel(base=120.0, slope=40.0))
    assert "asphaltene-eos-onset-raised" in codes(report)
    assert "asphaltene-eos-onset-at-commingling" not in codes(report)


def test_unstable_blend_reported_as_above_range():
    report = run(FakeModel(base=120.0, slope=10.0, unstable_from=0.75))
    assert "asphaltene-eos-onset-at-commingling" in codes(report)
    assert ">max" in report.to_markdown()
    assert report.to_dict()["blends"][3]["asphaltene_onset_bara"] is None


def test_reference_unstable_and_temperature_note():
    report = run(FakeModel(base=250.0, slope=0.0, measured_t=20.0))
    assert {"asphaltene-eos-reference-unstable", "asphaltene-eos-temperature"} <= codes(
        report
    )


def test_non_asphaltenic_fluid_end_member_has_no_onset():
    report = run(FakeModel())
    end = next(p for p in report.blends if p.fraction_b == 1.0)
    assert math.isnan(end.asphaltene_onset_bara)


# -- NeqSim -----------------------------------------------------------------
@pytest.fixture(scope="module")
def jvm():
    pytest.importorskip("neqsim")
    import jpype.config

    jpype.config.destroy_jvm = False
    from fluid_commingling_compatibility import CalibratedAsphalteneModel

    return CalibratedAsphalteneModel


def test_calibration_reproduces_onset_and_condensate_raises_it(jvm):
    model = jvm(asph_host(), MeasuredOnset(90.0, 250.0), backend="python")
    host_onset = model.onset(blend(asph_host(), condensate(), 0.0))
    assert host_onset.upper_bara == pytest.approx(250.0, abs=0.2)
    b10 = model.onset(blend(asph_host(), condensate(), 0.1)).upper_bara
    b30 = model.onset(blend(asph_host(), condensate(), 0.3)).upper_bara
    assert 250.0 + 2.0 < b10 < b30


def test_lower_onset_fits_solid_volume(jvm):
    model = jvm(asph_host(), MeasuredOnset(90.0, 250.0, 80.0), backend="python")
    result = model.onset(
        blend(asph_host(), condensate(), 0.0), step_bar=5.0, min_pressure_bara=20.0
    )
    assert result.upper_bara == pytest.approx(250.0, abs=0.2)
    assert result.lower_bara == pytest.approx(80.0, abs=0.2)
    assert 0 < model.solid_molar_volume < 1.0 / 1150.0


def test_java_backend_matches_python_when_available(jvm):
    from neqsim import jneqsim

    try:
        jneqsim.pvtsimulation.flowassurance.AsphalteneSolidModel  # noqa: B018
    except AttributeError:
        pytest.skip("installed NeqSim has no AsphalteneSolidModel")
    java = jvm(asph_host(), MeasuredOnset(90.0, 250.0), backend="java")
    python = jvm(asph_host(), MeasuredOnset(90.0, 250.0), backend="python")
    b = blend(asph_host(), condensate(), 0.3)
    assert java.onset(b).upper_bara == pytest.approx(
        python.onset(b).upper_bara, abs=0.1
    )


def test_model_needs_asphaltene_with_critical_properties(jvm):
    with pytest.raises(FluidSpecError):
        jvm(asph_host(with_critical=False), MeasuredOnset(90.0, 250.0))
    with pytest.raises(FluidSpecError):
        jvm(condensate(), MeasuredOnset(90.0, 250.0))
