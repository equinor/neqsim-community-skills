from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flare_radiation_screening import FlareRadiationModel


def main() -> None:
    model = FlareRadiationModel()
    result = model.evaluate(
        mass_flow=50.0,
        heat_of_combustion=46.0,
        distance=60.0,
    )

    print("Flare radiation screening result")
    print(f"total_heat_release_kw={result.total_heat_release_kw}")
    print(f"radiant_heat_flux_kw_m2={result.radiant_heat_flux_kw_m2}")
    print(f"allowable_flux_kw_m2={result.allowable_flux_kw_m2}")
    print(f"flux_ratio={result.flux_ratio}")
    print(f"radiation_warning={result.radiation_warning}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()
