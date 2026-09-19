"""Tests for the pure-Python E300 format layer of neqsim-e300-fluid-io.

These tests do not require NeqSim. They validate parsing, round-tripping, water
addition with the public PVTsim parameters, and the file-level add-water helper.
"""

from __future__ import annotations

import os

import pytest

from e300_fluid_io import (
    WATER_E300_PARAMETERS,
    add_water,
    add_water_to_e300_file,
    parse_e300,
    read_e300_file,
    serialize_e300,
    write_e300_file,
)

EXAMPLES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "examples"
)
SAMPLE = os.path.join(EXAMPLES_DIR, "sample_gas.e300")


def _load_sample():
    return read_e300_file(SAMPLE)


def test_parse_reads_components_and_scalars():
    fluid = _load_sample()
    assert fluid.names == ["N2", "CO2", "C1", "C2"]
    assert fluid.ncomps == 4
    assert fluid.eos == "PR"
    assert fluid.eos_correction == "PRCORR"
    assert fluid.reservoir_temp_c == pytest.approx(90.0)
    assert fluid.pedersen is True


def test_vector_lengths_match_components():
    fluid = _load_sample()
    assert len(fluid.tcrit) == 4
    assert len(fluid.zi) == 4
    assert fluid.tcrit[2] == pytest.approx(190.578)
    assert sum(fluid.zi) == pytest.approx(1.0)
    assert fluid.validate() == []


def test_bic_matrix_is_symmetric():
    fluid = _load_sample()
    assert len(fluid.bic) == 4
    for r in range(4):
        for c in range(4):
            assert fluid.bic[r][c] == pytest.approx(fluid.bic[c][r])
    assert fluid.bic[1][0] == pytest.approx(0.0)
    assert fluid.bic[2][0] == pytest.approx(0.0250)
    assert fluid.bic[2][1] == pytest.approx(0.1050)


def test_round_trip_preserves_values():
    fluid = _load_sample()
    text = serialize_e300(fluid)
    reparsed = parse_e300(text)
    assert reparsed.names == fluid.names
    for a, b in zip(reparsed.tcrit, fluid.tcrit):
        assert a == pytest.approx(b)
    for a, b in zip(reparsed.zi, fluid.zi):
        assert a == pytest.approx(b)
    assert reparsed.validate() == []


def test_add_water_appends_water_with_pvtsim_parameters():
    fluid = _load_sample()
    assert fluid.has_water() is False
    add_water(fluid)
    assert fluid.has_water() is True
    assert fluid.names[-1] == "H2O"
    assert fluid.ncomps == 5
    assert fluid.tcrit[-1] == pytest.approx(WATER_E300_PARAMETERS["TCRIT"])
    assert fluid.sshift[-1] == pytest.approx(0.084004)
    assert fluid.parachor[-1] == pytest.approx(10.0)
    assert fluid.zi[-1] == pytest.approx(0.0)
    # Water binary interaction parameter is 0.5 against all other components.
    for c in range(4):
        assert fluid.bic[4][c] == pytest.approx(0.5)
        assert fluid.bic[c][4] == pytest.approx(0.5)
    assert fluid.validate() == []


def test_add_water_is_idempotent():
    fluid = _load_sample()
    add_water(fluid)
    add_water(fluid)
    assert fluid.names.count("H2O") == 1


def test_add_water_to_e300_file(tmp_path):
    out = tmp_path / "sample_gas_water.e300"
    fluid = add_water_to_e300_file(SAMPLE, str(out))
    assert out.exists()
    assert fluid.has_water()
    reloaded = read_e300_file(str(out))
    assert reloaded.names[-1] == "H2O"
    assert reloaded.ncomps == 5
    assert reloaded.validate() == []


def test_custom_water_kij(tmp_path):
    fluid = _load_sample()
    add_water(fluid, water_kij=0.48)
    assert fluid.bic[4][0] == pytest.approx(0.48)
    write_e300_file(fluid, str(tmp_path / "x.e300"))
