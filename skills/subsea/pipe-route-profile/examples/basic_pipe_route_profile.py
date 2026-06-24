from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pipe_route_profile import PipeRouteModel


def main() -> None:
    model = PipeRouteModel(max_slope_deg=15.0)
    result = model.evaluate(
        waypoints=[
            {"name": "Tree", "x": 0.0, "y": 0.0, "depth_m": 340.0},
            {"name": "KP2", "x": 2000.0, "y": 200.0, "depth_m": 300.0},
            {"name": "KP6", "x": 6000.0, "y": 900.0, "depth_m": 210.0},
            {"name": "Riser base", "x": 8000.0, "y": 1500.0, "depth_m": 120.0},
        ],
        coordinate_system="cartesian",
    )

    print("Pipe route profile result")
    print(f"waypoint_count={result.waypoint_count}")
    print(f"total_horizontal_length_km={result.total_horizontal_length_km}")
    print(f"total_route_length_km={result.total_route_length_km}")
    print(f"net_elevation_change_m={result.net_elevation_change_m}")
    print(f"total_rise_m={result.total_rise_m}")
    print(f"max_slope_deg={result.max_slope_deg}")
    print(f"slope_warning={result.slope_warning}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()
