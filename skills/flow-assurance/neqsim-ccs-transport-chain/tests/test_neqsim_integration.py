"""Real NeqSim chain pieces; skipped without neqsim."""

import pytest

pytest.importorskip("neqsim")

from ccs_transport_chain import (
    ChainLimits,
    Co2Pipeline,
    Co2Stream,
    InjectionWell,
    assess_transport_chain,
    two_phase_boundary_bara,
    water_solubility_ppm_mol,
)


@pytest.fixture(scope="module", autouse=True)
def _keep_jvm_alive_at_exit():
    """Skip JPype's exit-time JVM teardown (avoids a spurious exit 139)."""
    import jpype.config

    jpype.config.destroy_jvm = False
    yield


IMPURE = {
    "CO2": 0.955,
    "nitrogen": 0.02,
    "argon": 0.005,
    "hydrogen": 0.005,
    "methane": 0.015,
}


def test_two_phase_boundary_matches_bubble_point():
    from neqsim import jneqsim as j

    system = j.thermo.system.SystemPrEos(273.15 + 4.0, 80.0)
    for name, x in IMPURE.items():
        system.addComponent(name, x)
    system.setMixingRule("classic")
    j.thermodynamicoperations.ThermodynamicOperations(system).bubblePointPressureFlash(
        False
    )
    bubble = float(system.getPressure())
    assert two_phase_boundary_bara(IMPURE, 4.0, 200.0) == pytest.approx(bubble, abs=0.5)


def test_water_solubility_in_dense_co2_is_plausible():
    pure = water_solubility_ppm_mol({"CO2": 1.0}, 5.0, 100.0)
    assert 1000.0 < pure < 5000.0  # a few thousand ppm(mol) in liquid CO2
    assert water_solubility_ppm_mol({"CO2": 1.0}, 30.0, 100.0) > pure


def test_short_chain_end_to_end():
    stream = Co2Stream({**IMPURE, "water": 0.00005})
    pipe = Co2Pipeline(20000.0, 0.3, 150000.0, 140.0, 30.0, segments=2)
    well = InjectionWell(1000.0, 0.157, 100.0, fracture_pressure_bara=300.0)
    report = assess_transport_chain(stream, pipe, well, ChainLimits())
    assert len(report.stations) == 3
    assert all(s.phases == 1 for s in report.stations)
    assert report.well["bhp_bara"] > report.stations[-1].pressure_bara
    assert any(f.code == "dry-ice" for f in report.findings)
