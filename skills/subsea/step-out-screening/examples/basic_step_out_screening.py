from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from step_out_screening import StepOutScreeningModel


def main() -> None:
    model = StepOutScreeningModel(max_step_out_km=50.0)
    result = model.evaluate(
        step_out_km=42.0,
        arrival_pressure_bara=95.0,
        min_arrival_pressure_bara=90.0,
        hydrate_margin_c=3.0,
    )

    print("Step-out screening result")
    print(f"step_out_km={result.step_out_km}")
    print(f"step_out_warning={result.step_out_warning}")
    print(f"arrival_pressure_margin_bar={result.arrival_pressure_margin_bar}")
    print(f"pressure_warning={result.pressure_warning}")
    print(f"hydrate_warning={result.hydrate_warning}")
    print(f"overall_warning={result.overall_warning}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()
