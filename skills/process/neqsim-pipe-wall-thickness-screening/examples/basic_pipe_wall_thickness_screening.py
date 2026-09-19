from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pipe_wall_thickness_screening import PipeWallThicknessModel


def main() -> None:
    model = PipeWallThicknessModel()
    result = model.evaluate(
        design_pressure=100.0,
        outer_diameter=323.9,
        allowable_stress=138.0,
        nominal_thickness=12.7,
    )

    print("Pipe wall thickness screening result")
    print(f"pressure_design_thickness_mm={result.pressure_design_thickness_mm}")
    print(f"required_thickness_mm={result.required_thickness_mm}")
    print(f"nominal_thickness_mm={result.nominal_thickness_mm}")
    print(f"thickness_margin_ratio={result.thickness_margin_ratio}")
    print(f"wall_thickness_warning={result.wall_thickness_warning}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()
