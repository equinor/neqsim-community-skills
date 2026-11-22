"""Real NeqSim pipeline, chemistry, dense phase and materials review."""

import pytest

pytest.importorskip("neqsim")

from co2_corrosion_profile import (
    CorrosionFluid,
    DesignBasis,
    NeqSimChemistry,
    PipelineSpec,
    ProfilePoint,
    assess_corrosion_profile,
    neqsim_pipeline_profile,
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


WET_GAS = CorrosionFluid(
    {"methane": 88.0, "ethane": 5.0, "propane": 2.0, "CO2": 3.0, "water": 2.0},
    chloride_mg_l=10000.0,
)


def test_pipeline_profile_cools_and_has_right_length():
    pipe = PipelineSpec(
        length_m=6000.0,
        inner_diameter_m=0.254,
        mass_flow_kg_h=80000.0,
        inlet_pressure_bara=100.0,
        inlet_temperature_c=80.0,
        segments=4,
        ambient_temperature_c=4.0,
        overall_u_w_m2k=15.0,
    )
    points = neqsim_pipeline_profile(WET_GAS, pipe)
    assert len(points) == 5
    assert points[0].distance_m == 0.0
    assert points[-1].distance_m == pytest.approx(6000.0, rel=1e-6)
    assert points[-1].temperature_c < points[0].temperature_c
    assert points[-1].pressure_bara < points[0].pressure_bara
    assert all(p.mixture_velocity_m_s > 0 for p in points)


def test_chemistry_finds_water_and_acid_ph():
    chem = NeqSimChemistry().evaluate(WET_GAS, 100.0, 40.0)
    assert chem.free_water
    assert 3.0 < chem.in_situ_ph < 4.5
    assert chem.gas_co2_mole_fraction == pytest.approx(0.03, abs=0.01)
    fixed = NeqSimChemistry(ph=5.2).evaluate(WET_GAS, 100.0, 40.0)
    assert fixed.in_situ_ph == 5.2 and fixed.ph_source == "user-supplied pH"
    buffered = CorrosionFluid(dict(WET_GAS.components), bicarbonate_mg_l=1000.0)
    assert (
        NeqSimChemistry().evaluate(buffered, 100.0, 40.0).in_situ_ph > chem.in_situ_ph
    )


def test_full_assessment_with_materials_review():
    points = [
        ProfilePoint(0, 100, 60, wall_shear_pa=15),
        ProfilePoint(5000, 98, 30, wall_shear_pa=15),
    ]
    report = assess_corrosion_profile(
        WET_GAS, points, DesignBasis(corrosion_allowance_mm=3.0)
    )
    assert report.worst_station().bare_rate_mm_y > 1.0
    assert report.materials_review["items"]
    assert report.m001_recommendation["recommended_material"]


def test_dense_phase_mode():
    ccs = CorrosionFluid(
        {"CO2": 96.0, "nitrogen": 3.0, "water": 0.05},
        dense_phase_impurities_ppmv={"O2": 20.0},
    )
    points = [
        ProfilePoint(0, 150, 40, wall_shear_pa=5),
        ProfilePoint(50000, 110, 4, wall_shear_pa=5),
    ]
    report = assess_corrosion_profile(
        ccs, points, DesignBasis(), materials_review=False
    )
    assert report.mode == "dense-phase CO2"
    assert all(s.dense_phase for s in report.stations)
    codes = {f.code for f in report.findings}
    assert "dense-phase-summary" in codes and "dense-phase-impurities" in codes
