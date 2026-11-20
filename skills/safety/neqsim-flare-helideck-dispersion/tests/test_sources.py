import math

import pytest
from flare_helideck_dispersion import (
    api520_rated_mass_flow_kg_s,
    composition_to_release_properties,
    neqsim_available,
    release_case_from_composition,
    size_psv_api520_gas,
    sources,
)
from flare_helideck_dispersion.sources import (
    NeqSimUnavailableError,
    relieving_pressure_pa,
)


def test_composition_lfl_and_molar_mass():
    methane = composition_to_release_properties({"methane": 1.0})
    assert methane["lfl_vol_frac"] == pytest.approx(0.05)
    assert methane["fuel_mole_frac"] == pytest.approx(1.0)
    assert methane["mw_kg_mol"] == pytest.approx(0.016043)
    mix = composition_to_release_properties({"methane": 0.5, "ethane": 0.5})
    assert mix["lfl_vol_frac"] == pytest.approx(1.0 / (0.5 / 0.05 + 0.5 / 0.03))
    diluted = composition_to_release_properties({"methane": 0.9, "CO2": 0.1})
    assert diluted["fuel_mole_frac"] == pytest.approx(0.9)
    assert diluted["lfl_vol_frac"] == pytest.approx(0.05)
    with pytest.raises(ValueError):
        composition_to_release_properties({"unobtainium": 1.0})
    with pytest.raises(ValueError):
        composition_to_release_properties({"nitrogen": 1.0})


def test_release_case_from_composition():
    case = release_case_from_composition(
        "c", 10.0, {"methane": 0.8, "ethane": 0.2}, 1.25, 300.0
    )
    assert case.mass_flow_kg_s == 10.0
    assert 0.03 < case.lfl_vol_frac < 0.05


def test_rated_flow_scales_with_area_and_pressure():
    a = 1.84e-3
    w = api520_rated_mass_flow_kg_s(a, 50.0, 0.1, 323.15, 0.0212, 0.9, 1.2)
    assert w == pytest.approx(19.3, rel=0.01)
    assert api520_rated_mass_flow_kg_s(
        2 * a, 50.0, 0.1, 323.15, 0.0212, 0.9, 1.2
    ) == pytest.approx(2 * w)
    assert api520_rated_mass_flow_kg_s(a, 100.0, 0.1, 323.15, 0.0212, 0.9, 1.2) > w
    assert relieving_pressure_pa(50.0, 0.1) == pytest.approx(50e5 + 101325.0 + 5e5)
    with pytest.raises(ValueError):
        api520_rated_mass_flow_kg_s(-1.0, 50.0, 0.1, 323.15, 0.0212, 0.9, 1.2)


def test_psv_sizing_skips_gracefully_without_neqsim(monkeypatch):
    monkeypatch.setattr(sources, "neqsim_available", lambda: False)
    assert size_psv_api520_gas(18.0, 50.0, 323.15, 0.0212, 0.9, 1.2) is None
    with pytest.raises(NeqSimUnavailableError):
        size_psv_api520_gas(18.0, 50.0, 323.15, 0.0212, 0.9, 1.2, required=True)


@pytest.mark.skipif(not neqsim_available(), reason="NeqSim is not importable")
def test_psv_sizing_with_neqsim_selects_an_api526_orifice():
    res = size_psv_api520_gas(18.0, 50.0, 323.15, 0.0212, 0.9, 1.2)
    assert res["api526_orifice_letter"] in sources.STANDARD_ORIFICES_IN2
    area_m2 = res["selected_area_in2"] * sources.IN2_TO_M2
    expected = api520_rated_mass_flow_kg_s(area_m2, 50.0, 0.1, 323.15, 0.0212, 0.9, 1.2)
    assert res["rated_mass_flow_kg_s"] == pytest.approx(expected)
    assert res["rated_mass_flow_kg_s"] >= 18.0
    assert math.isfinite(res["required_area_in2"])
    assert res["required_area_in2"] * sources.IN2_TO_M2 <= area_m2
