from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sand_erosion_screening import SandErosionModel


def main() -> None:
    model = SandErosionModel()
    result = model.evaluate(
        fluid_velocity=12.0,
        mixture_density=120.0,
        pipe_diameter=0.1524,
        wall_thickness=12.7,
        sand_rate=50.0,
        corrosion_allowance=3.0,
        material_factor=1.0,
        design_life_years=25.0,
    )

    print("Sand erosion screening result")
    print(f"erosional_velocity_m_per_s={result.erosional_velocity_m_per_s}")
    print(f"velocity_ratio={result.velocity_ratio}")
    print(f"erosion_rate_mm_per_yr={result.erosion_rate_mm_per_yr}")
    print(f"cumulative_erosion_mm={result.cumulative_erosion_mm}")
    print(f"remaining_wall_mm={result.remaining_wall_mm}")
    print(f"remaining_life_years={result.remaining_life_years}")
    print(f"erosion_warning={result.erosion_warning}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()
