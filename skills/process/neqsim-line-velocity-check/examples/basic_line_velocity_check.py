from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from line_velocity_check import LineVelocityModel


def main() -> None:
    model = LineVelocityModel()
    result = model.evaluate(
        fluid_velocity=12.0,
        mixture_density=50.0,
        c_factor=122.0,
        max_velocity_guideline=20.0,
    )

    print("Line velocity check result")
    print(f"erosional_velocity_m_per_s={result.erosional_velocity_m_per_s}")
    print(f"velocity_ratio={result.velocity_ratio}")
    print(f"guideline_ratio={result.guideline_ratio}")
    print(f"operating_indicator={result.operating_indicator}")
    print(f"velocity_warning={result.velocity_warning}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()
