import pytest

from gas_scrubber_sizing_screening import GasScrubberSizingModel


def test_sizes_vessel_without_diameter() -> None:
    result = GasScrubberSizingModel().evaluate(
        gas_mass_flow_kg_s=8.0,
        gas_density_kg_m3=45.0,
        liquid_density_kg_m3=700.0,
    )

    assert result.souders_brown_velocity_m_s > 0.0
    assert result.required_diameter_m > 0.0
    assert result.actual_velocity_m_s is None
    assert result.velocity_utilisation is None
    assert result.sizing_warning == "ok"
    assert result.assumptions


def test_undersized_vessel_flags_undersized() -> None:
    result = GasScrubberSizingModel().evaluate(
        gas_mass_flow_kg_s=20.0,
        gas_density_kg_m3=45.0,
        liquid_density_kg_m3=700.0,
        vessel_inside_diameter_m=0.6,
    )

    assert result.velocity_utilisation is not None
    assert result.velocity_utilisation > 1.0
    assert result.sizing_warning == "undersized"


def test_large_vessel_flags_oversized() -> None:
    result = GasScrubberSizingModel().evaluate(
        gas_mass_flow_kg_s=2.0,
        gas_density_kg_m3=45.0,
        liquid_density_kg_m3=700.0,
        vessel_inside_diameter_m=3.0,
    )

    assert result.sizing_warning == "oversized"


def test_demister_overload_flag() -> None:
    result = GasScrubberSizingModel().evaluate(
        gas_mass_flow_kg_s=20.0,
        gas_density_kg_m3=45.0,
        liquid_density_kg_m3=700.0,
        vessel_inside_diameter_m=0.6,
        mist_eliminator_k_factor=0.05,
    )

    assert result.demister_utilisation is not None
    assert result.demister_utilisation > 1.0
    assert result.demister_warning == "mist-eliminator-overloaded"


def test_no_demister_flag() -> None:
    result = GasScrubberSizingModel().evaluate(
        gas_mass_flow_kg_s=8.0,
        gas_density_kg_m3=45.0,
        liquid_density_kg_m3=700.0,
        vessel_inside_diameter_m=1.2,
        demister_present=False,
    )

    assert result.demister_warning == "no-demister"


def test_rejects_liquid_lighter_than_gas() -> None:
    with pytest.raises(ValueError, match="liquid_density_kg_m3"):
        GasScrubberSizingModel().evaluate(
            gas_mass_flow_kg_s=8.0,
            gas_density_kg_m3=700.0,
            liquid_density_kg_m3=45.0,
        )
