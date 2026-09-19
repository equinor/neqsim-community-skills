import pytest

from flare_radiation_screening import FlareRadiationModel


def test_flare_radiation_model_ok_at_distance() -> None:
    result = FlareRadiationModel().evaluate(
        mass_flow=20.0,
        heat_of_combustion=46.0,
        distance=80.0,
    )

    assert result.radiation_warning == "ok"
    assert result.radiant_heat_flux_kw_m2 < result.allowable_flux_kw_m2
    assert result.assumptions


def test_flare_radiation_model_high_when_close() -> None:
    result = FlareRadiationModel().evaluate(
        mass_flow=100.0,
        heat_of_combustion=46.0,
        distance=20.0,
    )

    assert result.radiation_warning == "high"
    assert result.flux_ratio >= 1.0


def test_flare_radiation_model_matches_point_source_formula() -> None:
    from math import pi

    result = FlareRadiationModel().evaluate(
        mass_flow=50.0,
        heat_of_combustion=46.0,
        distance=60.0,
        fraction_radiated=0.2,
        transmissivity=1.0,
    )

    q_total = 50.0 * 46.0 * 1000.0
    expected = 1.0 * 0.2 * q_total / (4.0 * pi * 60.0 * 60.0)
    assert result.radiant_heat_flux_kw_m2 == pytest.approx(expected, rel=1e-4)


def test_flare_radiation_model_rejects_invalid_fraction() -> None:
    with pytest.raises(ValueError, match="fraction_radiated"):
        FlareRadiationModel().evaluate(
            mass_flow=50.0,
            heat_of_combustion=46.0,
            distance=60.0,
            fraction_radiated=1.5,
        )
