from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from subsea_layout_geometry import SubseaLayoutModel


def main() -> None:
    model = SubseaLayoutModel(max_step_out_km=50.0)
    result = model.evaluate(
        nodes=[
            {"name": "Host", "x": 0.0, "y": 0.0, "water_depth_m": 120.0, "kind": "host"},
            {"name": "M1", "x": 7000.0, "y": 1000.0, "water_depth_m": 320.0, "kind": "manifold"},
            {"name": "W1", "x": 8000.0, "y": 1500.0, "water_depth_m": 340.0, "kind": "well"},
            {"name": "W2", "x": 8200.0, "y": 700.0, "water_depth_m": 345.0, "kind": "well"},
        ],
        host_name="Host",
        coordinate_system="cartesian",
    )

    print("Subsea layout geometry result")
    print(f"node_count={result.node_count}")
    print(f"step_out_km={result.step_out_km}")
    print(f"straight_line_km={result.straight_line_km}")
    print(f"max_step_out_km={result.max_step_out_km}")
    print(f"step_out_warning={result.step_out_warning}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()
