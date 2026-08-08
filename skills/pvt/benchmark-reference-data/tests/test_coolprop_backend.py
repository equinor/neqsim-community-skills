from __future__ import annotations

import pytest

from benchmark_reference_data import coolprop_backend as backend

coolprop_required = pytest.mark.skipif(
    not backend.is_available(), reason="CoolProp is an optional backend"
)


def test_availability_check_never_raises():
    assert isinstance(backend.is_available(), bool)


def test_version_is_none_exactly_when_unavailable():
    if backend.is_available():
        assert backend.coolprop_version()
    else:
        assert backend.coolprop_version() is None


def test_fluid_names_map_onto_coolprop_identifiers():
    assert backend.coolprop_fluid_name("co2") == "CarbonDioxide"
    assert backend.coolprop_fluid_name("carbon dioxide") == "CarbonDioxide"
    assert backend.coolprop_fluid_name("water") == "Water"


def test_unmapped_fluid_passes_through_unchanged():
    assert backend.coolprop_fluid_name("Krypton") == "Krypton"


def test_supported_properties_cover_the_common_benchmark_targets():
    supported = set(backend.supported_properties())
    assert {"density", "enthalpy", "viscosity", "speed_of_sound"} <= supported


def test_missing_backend_raises_with_an_install_hint():
    if backend.is_available():
        pytest.skip("CoolProp is installed; the unavailable path cannot be exercised")
    with pytest.raises(backend.CoolPropUnavailableError) as excinfo:
        backend.reference_point("co2", "density", 300.0, 1.0e6)
    assert "pip install CoolProp" in str(excinfo.value)


@coolprop_required
def test_unsupported_property_lists_the_supported_ones():
    with pytest.raises(backend.UnsupportedPropertyError) as excinfo:
        backend.reference_point("co2", "not_a_property", 300.0, 1.0e6)
    assert "density" in str(excinfo.value)


@coolprop_required
def test_reference_point_matches_the_offline_anchor_for_water_density():
    point = backend.reference_point("water", "density", 298.15, 101325.0)
    assert point.value == pytest.approx(997.047, rel=1e-3)
    assert point.source_key == "coolprop_heos"
    assert point.unit == "kg/m3"


@coolprop_required
def test_reference_grid_covers_every_temperature_pressure_combination():
    points = backend.reference_grid("co2", "density", (280.0, 300.0), (5.0e6, 10.0e6))
    assert len(points) == 4
    assert all(p.property_name == "density" for p in points)


@coolprop_required
def test_reference_states_accepts_an_explicit_state_list():
    states = [{"temperature_K": 300.0, "pressure_Pa": 1.0e6}]
    points = backend.reference_states("methane", "density", states)
    assert len(points) == 1
    assert points[0].state["temperature_K"] == pytest.approx(300.0)
