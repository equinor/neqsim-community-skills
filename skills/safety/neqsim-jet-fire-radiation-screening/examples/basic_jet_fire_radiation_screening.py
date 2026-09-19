import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from jet_fire_radiation_screening import JetFireRadiationModel


def main() -> None:
    model = JetFireRadiationModel()

    at_distance = model.evaluate(
        release_rate=10.0,
        heat_of_combustion=50.0e6,
        radiant_fraction=0.2,
        distance=40.0,
    )
    print("Flux at 40 m")
    print(f"  total_radiative_power_kw : {at_distance.total_radiative_power_kw}")
    print(f"  radiation_flux_kw_m2     : {at_distance.radiation_flux_kw_m2}")
    print(f"  radiation_warning        : {at_distance.radiation_warning}")

    to_target = model.evaluate(
        release_rate=10.0,
        target_flux=12.5,
    )
    print("Distance to 12.5 kW/m2")
    print(f"  distance_to_target_m     : {to_target.distance_to_target_m}")
    for line in to_target.assumptions:
        print(f"  - {line}")


if __name__ == "__main__":
    main()
