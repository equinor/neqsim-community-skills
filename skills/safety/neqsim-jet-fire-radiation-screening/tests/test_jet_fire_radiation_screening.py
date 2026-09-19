import pytest

from jet_fire_radiation_screening import JetFireRadiationModel


def test_total_radiative_power():
    model = JetFireRadiationModel()
    result = model.evaluate(release_rate=1.0)
    # 1.0 * 50e6 * 0.2 / 1000 = 10000 kW
    assert result.total_radiative_power_kw == pytest.approx(10000.0, abs=1.0)


def test_flux_at_distance():
    model = JetFireRadiationModel()
    result = model.evaluate(release_rate=1.0, distance=50.0)
    # q = 1e7 W / (4 pi 2500) ~ 318.3 W/m2 ~ 0.318 kW/m2
    assert result.radiation_flux_kw_m2 == pytest.approx(0.318, abs=5.0e-3)
    assert result.radiation_warning == "ok"


def test_distance_to_target():
    model = JetFireRadiationModel()
    result = model.evaluate(release_rate=10.0, target_flux=12.5)
    assert result.distance_to_target_m is not None
    assert result.distance_to_target_m > 0.0


def test_severe_warning_close_in():
    model = JetFireRadiationModel()
    result = model.evaluate(release_rate=30.0, distance=10.0)
    assert result.radiation_warning == "severe"


def test_invalid_radiant_fraction_rejected():
    model = JetFireRadiationModel()
    with pytest.raises(ValueError, match="radiant_fraction"):
        model.evaluate(release_rate=1.0, radiant_fraction=1.5)


def test_invalid_release_rate_rejected():
    model = JetFireRadiationModel()
    with pytest.raises(ValueError, match="release_rate"):
        model.evaluate(release_rate=0.0)
