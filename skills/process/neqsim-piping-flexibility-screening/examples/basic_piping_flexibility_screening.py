from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from piping_flexibility_screening import PipingFlexibilityModel


def main() -> None:
    model = PipingFlexibilityModel()
    result = model.evaluate(
        outside_diameter_mm=168.3,
        wall_thickness_mm=7.11,
        design_pressure_bar=50.0,
        design_temperature_c=180.0,
        pipe_length_m=40.0,
        install_temperature_c=20.0,
        anchor_to_anchor=True,
        flange_rating_class=300,
        flange_allowable_pressure_bar=49.6,
    )

    print("Piping flexibility screening result")
    print(f"hoop_stress_mpa={result.hoop_stress_mpa}")
    print(f"hoop_stress_ratio={result.hoop_stress_ratio}")
    print(f"delta_temperature_k={result.delta_temperature_k}")
    print(f"free_thermal_expansion_mm={result.free_thermal_expansion_mm}")
    print(f"displacement_stress_mpa={result.displacement_stress_mpa}")
    print(f"allowable_stress_range_mpa={result.allowable_stress_range_mpa}")
    print(f"displacement_stress_ratio={result.displacement_stress_ratio}")
    print(f"flange_pressure_ratio={result.flange_pressure_ratio}")
    print(f"stress_warning={result.stress_warning}")
    print(f"flange_warning={result.flange_warning}")


if __name__ == "__main__":
    main()
