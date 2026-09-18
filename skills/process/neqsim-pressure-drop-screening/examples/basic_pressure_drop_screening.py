from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pressure_drop_screening import PressureDropModel


def main() -> None:
    model = PressureDropModel()
    result = model.evaluate(
        fluid_velocity=12.0,
        mixture_density=50.0,
        viscosity=1.2e-5,
        pipe_inner_diameter=0.2,
        length=100.0,
    )

    print("Pressure drop screening result")
    print(f"reynolds_number={result.reynolds_number}")
    print(f"friction_factor={result.friction_factor}")
    print(f"dp_per_100m_bar={result.dp_per_100m_bar}")
    print(f"dp_total_bar={result.dp_total_bar}")
    print(f"guideline_ratio={result.guideline_ratio}")
    print(f"pressure_drop_warning={result.pressure_drop_warning}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()
