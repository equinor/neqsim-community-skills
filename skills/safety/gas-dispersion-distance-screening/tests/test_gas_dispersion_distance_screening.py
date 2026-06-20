import pytest

from gas_dispersion_distance_screening import GaussianDispersionModel


def test_hazard_distance_found():
    model = GaussianDispersionModel()
    result = model.evaluate(
        release_rate=1.0,
        wind_speed=5.0,
        stability_class="D",
        target_concentration=1.0e-3,
    )
    assert result.hazard_distance_m is not None
    assert result.hazard_distance_m > 0.0
    assert result.dispersion_warning == "hazard-zone"


def test_stable_class_gives_longer_distance():
    model = GaussianDispersionModel()
    unstable = model.evaluate(
        release_rate=1.0,
        wind_speed=5.0,
        stability_class="B",
        target_concentration=1.0e-3,
    )
    stable = model.evaluate(
        release_rate=1.0,
        wind_speed=5.0,
        stability_class="F",
        target_concentration=1.0e-3,
    )
    assert stable.hazard_distance_m >= unstable.hazard_distance_m


def test_no_hazard_distance_for_high_target():
    model = GaussianDispersionModel()
    result = model.evaluate(
        release_rate=0.001,
        wind_speed=8.0,
        stability_class="A",
        target_concentration=1.0e6,
    )
    assert result.hazard_distance_m is None
    assert result.dispersion_warning == "no-hazard-distance"


def test_volume_fraction_helper():
    conc = GaussianDispersionModel.concentration_from_volume_fraction(
        volume_fraction=0.044,  # ~LFL of methane
        molar_mass=16.04,
    )
    assert conc == pytest.approx(0.0299, abs=2.0e-3)


def test_invalid_stability_rejected():
    model = GaussianDispersionModel()
    with pytest.raises(ValueError, match="stability_class"):
        model.evaluate(
            release_rate=1.0,
            wind_speed=5.0,
            stability_class="Z",
            target_concentration=1.0e-3,
        )


def test_invalid_release_rate_rejected():
    model = GaussianDispersionModel()
    with pytest.raises(ValueError, match="release_rate"):
        model.evaluate(
            release_rate=0.0,
            wind_speed=5.0,
            stability_class="D",
            target_concentration=1.0e-3,
        )
