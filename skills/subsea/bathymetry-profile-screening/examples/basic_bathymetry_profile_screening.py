from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from bathymetry_profile_screening import BathymetryProfileModel


def main() -> None:
    model = BathymetryProfileModel(max_slope_deg=10.0)
    result = model.evaluate(
        soundings=[
            {"distance_m": 0.0, "depth_m": 340.0},
            {"distance_m": 2000.0, "depth_m": 300.0},
            {"distance_m": 4000.0, "depth_m": 305.0},
            {"distance_m": 8000.0, "depth_m": 120.0},
        ],
        query_distances=[1000.0, 3000.0, 5000.0],
    )

    print("Bathymetry profile screening result")
    print(f"sounding_count={result.sounding_count}")
    print(f"interpolated={result.interpolated}")
    print(f"max_slope_deg={result.max_slope_deg}")
    print(f"min_depth_m={result.min_depth_m}")
    print(f"max_depth_m={result.max_depth_m}")
    print(f"steep_sections={result.steep_sections}")
    print(f"slope_warning={result.slope_warning}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()
