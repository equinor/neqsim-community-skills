from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from depressurization_screening import DepressurizationModel


def main() -> None:
    model = DepressurizationModel()
    result = model.evaluate(
        initial_pressure=100.0,
        target_pressure=7.0,
        inventory=2000.0,
        vent_mass_rate=12000.0,
        relieving_temperature=30.0,
        mdmt=-46.0,
    )

    print("Depressurization screening result")
    print(f"estimated_blowdown_time_min={result.estimated_blowdown_time_min}")
    print(f"blowdown_time_indicator={result.blowdown_time_indicator}")
    print(f"estimated_min_temperature_C={result.estimated_min_temperature_C}")
    print(f"low_temperature_flag={result.low_temperature_flag}")
    print(f"depressurization_warning={result.depressurization_warning}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()
