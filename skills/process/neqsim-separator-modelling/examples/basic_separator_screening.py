from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from separator_modelling import SeparatorModel


def main() -> None:
    model = SeparatorModel()
    result = model.evaluate(
        gas_flow=18_000.0,
        liquid_flow=120.0,
        pressure=55.0,
        temperature=35.0,
        gas_density=18.0,
        liquid_density=720.0,
    )

    print("Separator screening result")
    print(f"gas_load_indicator={result.gas_load_indicator}")
    print(f"residence_time_indicator={result.residence_time_indicator}")
    print(f"capacity_warning={result.capacity_warning}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()