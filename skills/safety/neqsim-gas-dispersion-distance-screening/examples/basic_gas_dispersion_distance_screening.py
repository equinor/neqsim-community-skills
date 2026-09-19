import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gas_dispersion_distance_screening import GaussianDispersionModel


def main() -> None:
    model = GaussianDispersionModel(assessment_distance=500.0)

    # Convert the methane lower flammable limit (~4.4 vol%) to kg/m3.
    lfl = GaussianDispersionModel.concentration_from_volume_fraction(
        volume_fraction=0.044,
        molar_mass=16.04,
    )
    result = model.evaluate(
        release_rate=2.0,
        wind_speed=5.0,
        stability_class="F",
        target_concentration=lfl,
        release_height=1.0,
    )

    print(f"target_concentration_kg_m3 : {result.target_concentration_kg_m3}")
    print(f"hazard_distance_m          : {result.hazard_distance_m}")
    print(f"peak_concentration_kg_m3   : {result.peak_concentration_kg_m3}")
    print(f"dispersion_warning         : {result.dispersion_warning}")
    print(f"neqsim_available           : {result.neqsim_available}")
    for line in result.assumptions:
        print(f"  - {line}")


if __name__ == "__main__":
    main()
