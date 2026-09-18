"""Tests for the adsorbent capillary condensation screening model."""

import math

import pytest

from adsorbent_capillary_condensation_screening import (
    CapillaryCondensationScreeningModel,
    micropore_filling_fraction,
)

# Methanol at 20 C
T = 293.15
SIGMA = 0.0225
VM = 40.7e-6
Y_SAT = 3.553e-3  # from CPA for rich gas at 20 C / 70 bara


@pytest.fixture(name="model")
def fixture_model():
    return CapillaryCondensationScreeningModel()


def test_kelvin_length_matches_analytical(model):
    result = model.evaluate(T, SIGMA, VM, 5.0, Y_SAT)
    expected = 2.0 * SIGMA * VM / (8.314462618 * T) * 1e9
    assert result.kelvin_length_nm == pytest.approx(expected, rel=1e-9)
    assert result.kelvin_length_nm == pytest.approx(0.7514, abs=5e-4)


def test_onset_matches_kelvin_equation(model):
    for radius, expected in ((1.0, 0.4717), (2.0, 0.6868), (5.0, 0.8605), (10.0, 0.9276)):
        result = model.evaluate(T, SIGMA, VM, radius, Y_SAT)
        assert result.onset_relative_saturation == pytest.approx(expected, abs=5e-4)


def test_narrow_pores_give_tighter_limit(model):
    narrow = model.evaluate(T, SIGMA, VM, 1.5, Y_SAT)
    wide = model.evaluate(T, SIGMA, VM, 20.0, Y_SAT)
    assert narrow.max_ppmv < wide.max_ppmv
    assert narrow.max_ppmv < Y_SAT * 1e6


def test_limit_is_a_fraction_of_bulk_saturation(model):
    result = model.evaluate(T, SIGMA, VM, 6.0, Y_SAT)
    assert result.max_mole_fraction == pytest.approx(result.onset_relative_saturation * Y_SAT)
    assert result.max_mole_fraction < Y_SAT


def test_micropore_flagged_as_invalid(model):
    assert model.evaluate(T, SIGMA, VM, 1.0, Y_SAT).kelvin_valid is False
    assert model.evaluate(T, SIGMA, VM, 6.0, Y_SAT).kelvin_valid is True


def test_slit_pores_condense_later_than_cylindrical(model):
    cylindrical = model.evaluate(T, SIGMA, VM, 5.0, Y_SAT, geometry_factor=2.0)
    slit = model.evaluate(T, SIGMA, VM, 5.0, Y_SAT, geometry_factor=1.0)
    assert slit.onset_relative_saturation > cylindrical.onset_relative_saturation


def test_partial_wetting_relaxes_the_limit(model):
    wetting = model.evaluate(T, SIGMA, VM, 5.0, Y_SAT, contact_angle_deg=0.0)
    partial = model.evaluate(T, SIGMA, VM, 5.0, Y_SAT, contact_angle_deg=60.0)
    assert partial.max_ppmv > wetting.max_ppmv


def test_warning_levels(model):
    limit = model.evaluate(T, SIGMA, VM, 6.0, Y_SAT).max_mole_fraction
    assert model.evaluate(T, SIGMA, VM, 6.0, Y_SAT, 0.05 * limit).warning == "ok"
    assert model.evaluate(T, SIGMA, VM, 6.0, Y_SAT, 0.7 * limit).warning == "watch"
    assert model.evaluate(T, SIGMA, VM, 6.0, Y_SAT, 1.4 * limit).warning == "condensation-expected"


def test_margin_and_relative_saturation_reported(model):
    result = model.evaluate(T, SIGMA, VM, 6.0, Y_SAT, 500e-6)
    assert result.relative_saturation == pytest.approx(500e-6 / Y_SAT)
    assert result.margin_ratio == pytest.approx(500e-6 / result.max_mole_fraction)


def test_micropore_filling_is_monotonic_and_bounded():
    assert micropore_filling_fraction(0.0, T) == 0.0
    assert micropore_filling_fraction(1.0, T) == 1.0
    low = micropore_filling_fraction(0.01, T)
    high = micropore_filling_fraction(0.3, T)
    assert 0.0 < low < high < 1.0


def test_micropores_fill_far_below_the_kelvin_onset(model):
    """The point of the micropore caveat: filling starts long before Kelvin says so."""
    onset = model.evaluate(T, SIGMA, VM, 1.0, Y_SAT).onset_relative_saturation
    assert micropore_filling_fraction(onset, T) > 0.5


@pytest.mark.parametrize(
    "kwargs",
    [
        {"temperature": 0.0},
        {"surface_tension": 0.0},
        {"molar_volume": -1.0},
        {"pore_radius_nm": 0.0},
        {"saturation_mole_fraction": 0.0},
    ],
)
def test_invalid_inputs_raise(model, kwargs):
    args = {
        "temperature": T,
        "surface_tension": SIGMA,
        "molar_volume": VM,
        "pore_radius_nm": 5.0,
        "saturation_mole_fraction": Y_SAT,
    }
    args.update(kwargs)
    with pytest.raises(ValueError):
        model.evaluate(**args)
