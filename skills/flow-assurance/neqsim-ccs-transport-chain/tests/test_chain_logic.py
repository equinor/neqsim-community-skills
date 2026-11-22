"""Chain input validation and findings logic (no Java)."""

import json
import math

import pytest
from ccs_transport_chain import (
    CcsInputError,
    ChainLimits,
    ChainReport,
    Co2Pipeline,
    Co2Stream,
    InjectionWell,
    Station,
)
from ccs_transport_chain.chain import _findings

STREAM = Co2Stream({"CO2": 0.96, "nitrogen": 0.03, "water": 0.0001})


def report(stations, depress=-50.0, impurities=None, well=None):
    rep = ChainReport(
        stations=stations,
        depressurisation=[
            {
                "from": "highest pressure",
                "pressure_bara": 150.0,
                "temperature_c": 20.0,
                "isenthalpic_final_c": depress,
                "isentropic_final_c": depress - 1,
            }
        ],
        impurities=impurities or {},
        well=well,
    )
    _findings(
        rep, STREAM, ChainLimits(min_single_phase_margin_bar=10.0, maop_bara=160.0)
    )
    return rep


def station(d, p, t, phases=1, boundary=60.0, solubility=2000.0):
    s = Station(d, p, t, phases=phases, two_phase_boundary_bara=boundary)
    s.single_phase_margin_bar = p - boundary
    s.water_solubility_ppm_mol = solubility
    s.water_margin_factor = solubility / STREAM.water_ppm_mol()
    return s


def test_stream_validation_and_helpers():
    assert STREAM.water_ppm_mol() == pytest.approx(1e6 * 0.0001 / 0.9901)
    assert "water" not in STREAM.dry()
    assert math.isclose(sum(STREAM.dry().values()), 1.0)
    with pytest.raises(CcsInputError):
        Co2Stream({"methane": 1.0})
    with pytest.raises(CcsInputError):
        Co2Stream({"CO2": 0.5, "methane": 0.5})
    with pytest.raises(CcsInputError):
        Co2Pipeline(0, 0.3, 1e5, 100, 30)
    with pytest.raises(CcsInputError):
        InjectionWell(0, 0.15, 100)
    with pytest.raises(CcsInputError):
        ChainLimits(water_margin_factor=0.5)


def test_clean_chain_has_only_low_temperature_findings_when_cold_blowdown():
    rep = report([station(0, 150, 30), station(1000, 149, 10)], depress=-40.0)
    assert rep.highest_severity == "none"
    assert rep.summary["min_single_phase_margin_bar"] == pytest.approx(89.0)


def test_margin_two_phase_water_and_maop():
    tight = report([station(0, 150, 30), station(1000, 65, 10)])
    assert {f.code for f in tight.findings} >= {"single-phase-margin"}
    two = report([station(0, 150, 30), station(1000, 55, 10, phases=2)])
    assert any(
        f.code == "two-phase-flow" and f.severity == "high" for f in two.findings
    )
    wet = report([station(0, 150, 30, solubility=50.0)])
    assert any(f.code == "free-water" for f in wet.findings)
    damp = report([station(0, 150, 30, solubility=150.0)])
    assert any(f.code == "water-margin" for f in damp.findings)
    high = report([station(0, 170, 30)])
    assert any(f.code == "above-maop" for f in high.findings)


def test_dry_ice_and_design_temperature():
    rep = report([station(0, 150, 30)], depress=-80.0)
    codes = {f.code for f in rep.findings}
    assert {"dry-ice", "below-design-temperature"} <= codes


def test_well_findings_and_serialisation():
    well = {
        "bhp_bara": 230.0,
        "bht_c": 40.0,
        "safe_to_operate": False,
        "injectivity_margin_bar": -5.0,
        "fracture_margin_bar": -20.0,
    }
    rep = report(
        [station(0, 150, 30)],
        impurities={"impurityIssues": ["O2 above limit"]},
        well=well,
    )
    codes = {f.code for f in rep.findings}
    assert {
        "no-injectivity",
        "above-fracture-pressure",
        "well-analyzer",
        "impurity-specification",
    } <= codes
    json.dumps(rep.to_dict(), allow_nan=False)
    assert "Fracture margin" in rep.to_markdown()
