from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from relief_load_screening import ReliefLoadModel


def main() -> None:
    model = ReliefLoadModel()
    result = model.evaluate(
        wetted_area=50.0,
        latent_heat=300.0,
        relief_pressure=20.0,
        environment_factor=1.0,
    )

    print("Relief load screening result")
    print(f"fire_heat_input_kW={result.fire_heat_input_kW}")
    print(f"relief_mass_rate_kg_per_h={result.relief_mass_rate_kg_per_h}")
    print(f"relief_load_indicator={result.relief_load_indicator}")
    print(f"relief_warning={result.relief_warning}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()
