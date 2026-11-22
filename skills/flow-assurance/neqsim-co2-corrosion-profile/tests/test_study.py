"""Profile assessment logic with an analytic chemistry stand-in (no Java)."""

import json
import math

import pytest
from co2_corrosion_profile import (
    CorrosionFluid,
    CorrosionInputError,
    DesignBasis,
    PipelineSpec,
    PointChemistry,
    ProfilePoint,
    PseudoCut,
    assess_corrosion_profile,
    wall_shear_stress_pa,
)

FLUID = CorrosionFluid({"methane": 90.0, "CO2": 3.0, "water": 2.0, "H2S": 0.0})


class FakeChemistry:
    """Water drops out below 70 C; pH falls as the line cools."""

    def __init__(self, h2s=0.0, glycol=0.0):
        self.h2s = h2s
        self.glycol = glycol

    def evaluate(self, fluid, pressure_bara, temperature_c):
        wet = temperature_c < 70.0
        return PointChemistry(
            free_water=wet,
            in_situ_ph=4.0 + 0.01 * temperature_c if wet else math.nan,
            ph_source="fake",
            gas_co2_mole_fraction=0.03,
            gas_h2s_mole_fraction=self.h2s,
            glycol_weight_fraction=self.glycol if wet else 0.0,
            # water vapour carried per kg of stream falls as the line cools
            water_vapour_mass_fraction=2e-5 * temperature_c,
        )


def profile(n=6, flow=True):
    return [
        ProfilePoint(
            distance_m=1000.0 * i,
            pressure_bara=100.0 - i,
            temperature_c=80.0 - 10.0 * i,
            mixture_velocity_m_s=5.0 if flow else None,
            mixture_density_kg_m3=90.0 if flow else None,
            mixture_viscosity_pa_s=1.5e-5 if flow else None,
        )
        for i in range(n)
    ]


def run(basis=None, points=None, chemistry=None, **kwargs):
    return assess_corrosion_profile(
        FLUID,
        profile() if points is None else points,
        basis or DesignBasis(corrosion_allowance_mm=3.0),
        chemistry=chemistry or FakeChemistry(),
        materials_review=False,
        **kwargs,
    )


def test_dry_upstream_wet_downstream():
    report = run()
    assert [s.free_water for s in report.stations] == [
        False,
        False,
        True,
        True,
        True,
        True,
    ]
    assert report.stations[0].bare_rate_mm_y == 0.0
    assert all(s.bare_rate_mm_y > 0 for s in report.stations[2:])
    codes = {f.code for f in report.findings}
    assert "water-dropout" in codes and "allowance-exceeded" in codes
    assert report.summary["wet_length_fraction"] == pytest.approx(4 / 6)
    worst = report.worst_station()
    assert report.summary["max_rate_distance_m"] == worst.distance_m
    assert report.summary["required_allowance_mm"] == pytest.approx(worst.wall_loss_mm)


def test_inhibitor_availability_reduces_design_rate():
    bare = run(DesignBasis(corrosion_allowance_mm=3.0))
    inhibited = run(
        DesignBasis(
            corrosion_allowance_mm=3.0,
            inhibitor_availability=0.95,
            inhibited_rate_mm_y=0.1,
        )
    )
    b, i = bare.worst_station(), inhibited.worst_station()
    assert i.bare_rate_mm_y == pytest.approx(b.bare_rate_mm_y)
    assert i.design_rate_mm_y == pytest.approx(0.95 * 0.1 + 0.05 * b.bare_rate_mm_y)
    assert i.wall_loss_mm == pytest.approx(i.design_rate_mm_y * 25.0)


def test_design_rate_formula():
    basis = DesignBasis(inhibitor_availability=0.9, inhibited_rate_mm_y=0.1)
    assert basis.design_rate(5.0) == pytest.approx(0.9 * 0.1 + 0.1 * 5.0)
    assert basis.design_rate(0.05) == pytest.approx(0.05)  # never above bare


def test_dry_line_is_info_only():
    hot = [
        ProfilePoint(0, 100, 90, wall_shear_pa=10),
        ProfilePoint(1000, 99, 85, wall_shear_pa=10),
    ]
    report = run(points=hot)
    assert report.highest_severity == "info"
    assert {f.code for f in report.findings} == {"dry-line"}
    assert report.worst_station() is None


def test_shear_from_flow_and_fallbacks():
    tau = wall_shear_stress_pa(5.0, 90.0, 1.5e-5, 0.254)
    reynolds = 90.0 * 5.0 * 0.254 / 1.5e-5
    f_d = (-1.8 * math.log10(6.9 / reynolds + (5e-5 / 0.254 / 3.7) ** 1.11)) ** -2
    assert tau == pytest.approx(f_d / 8 * 90.0 * 5.0**2)
    laminar = wall_shear_stress_pa(0.01, 800.0, 0.1, 0.1)  # Re = 8
    assert laminar == pytest.approx(64 / 8.0 / 8 * 800.0 * 0.01**2)
    assert math.isnan(wall_shear_stress_pa(0.0, 90.0, 1e-5, 0.254))
    with pytest.raises(CorrosionInputError, match="default_wall_shear_pa"):
        run(points=profile(flow=False))
    report = run(DesignBasis(default_wall_shear_pa=20.0), points=profile(flow=False))
    wet = [s for s in report.stations if s.free_water]
    assert all(s.wall_shear_pa == 20.0 for s in wet)
    assert all("shear from default_wall_shear_pa" in s.flags for s in wet)


def test_out_of_range_inputs_are_flagged():
    cold = [ProfilePoint(0, 100, 2.0, wall_shear_pa=10)]
    report = run(points=cold)
    assert any(f.code == "outside-correlation" for f in report.findings)
    assert report.stations[0].flags


def test_report_serialises_and_renders():
    report = run()
    text = json.dumps(report.to_dict(), allow_nan=False)
    assert '"calculation_basis": "screening"' in text
    markdown = report.to_markdown()
    assert "| km |" in markdown and "allowance-exceeded" in markdown


def test_input_validation():
    with pytest.raises(CorrosionInputError, match="water"):
        CorrosionFluid({"methane": 1.0, "CO2": 0.1})
    with pytest.raises(CorrosionInputError):
        CorrosionFluid({"methane": 1.0, "water": 0.1}, chloride_mg_l=-1)
    with pytest.raises(CorrosionInputError):
        PseudoCut("C10", 1.0, 140.0, 0.8)
    with pytest.raises(CorrosionInputError):
        DesignBasis(inhibitor_availability=1.5)
    with pytest.raises(CorrosionInputError):
        PipelineSpec(1000, 0.2, 1000, 50, 40, ambient_temperature_c=4.0)
    with pytest.raises(CorrosionInputError):
        ProfilePoint(0, -1, 20)
    with pytest.raises(CorrosionInputError):
        run(points=[])


def test_co2_rich_streams_switch_mode():
    rich = CorrosionFluid({"CO2": 95.0, "nitrogen": 5.0, "water": 0.01})
    assert rich.is_co2_rich()
    assert not FLUID.is_co2_rich()
    assert rich.dry_co2_fraction() == pytest.approx(0.95)


def test_top_of_line_screen_needs_mass_flow():
    assert any(f.code == "tlc-not-assessed" for f in run().findings)
    report = run(DesignBasis(mass_flow_kg_h=4.0e6, inner_diameter_m=0.254))
    rates = [s.condensation_g_m2_s for s in report.stations]
    # 4e6 kg/h * 2e-4 kg/kg per 10 C drop over 1 km of 0.254 m pipe = 0.28 g/m2/s
    assert rates[1] == pytest.approx(
        4.0e6 / 3600 * 2e-4 * 1000 / (math.pi * 0.254 * 1000)
    )
    assert report.stations[1].tlc_risk == "high"  # unknown regime treated as stratified
    assert any(
        f.code == "top-of-line-corrosion" and f.severity == "high"
        for f in report.findings
    )


def test_glycol_reduces_design_rate():
    plain = run().worst_station()
    with_meg = run(chemistry=FakeChemistry(glycol=0.4)).worst_station()
    assert with_meg.glycol_factor == pytest.approx(0.6)
    assert with_meg.design_rate_mm_y == pytest.approx(plain.design_rate_mm_y * 0.6)
    off = run(
        DesignBasis(apply_glycol_correction=False), chemistry=FakeChemistry(glycol=0.4)
    )
    assert off.worst_station().glycol_factor == 1.0


def test_h2s_regime_and_iso_threshold():
    # 0.0002 mol fraction at ~95 bara = 0.019 bar H2S; pCO2 2.9 bar -> ratio ~150
    report = run(chemistry=FakeChemistry(h2s=0.0002))
    codes = {f.code: f for f in report.findings}
    assert codes["h2s-regime"].severity == "warning"
    assert "sour-service" in codes
    sour = run(chemistry=FakeChemistry(h2s=0.01))
    assert {f.code: f for f in sour.findings}["h2s-regime"].severity == "high"
    trace = run(chemistry=FakeChemistry(h2s=0.00002))  # 1.9 mbar: below 0.3 kPa
    assert not any(f.code in ("sour-service", "h2s-regime") for f in trace.findings)
