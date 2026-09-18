from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from water_dewpoint_dehydration_screening import WaterDewpointModel


def main() -> None:
    model = WaterDewpointModel()
    result = model.evaluate(
        pressure=70.0,
        temperature=305.15,
    )

    print("Water dewpoint dehydration screening result")
    print(f"saturated_water_content_lb_mmscf={result.saturated_water_content_lb_mmscf}")
    print(f"water_spec_lb_mmscf={result.water_spec_lb_mmscf}")
    print(f"spec_ratio={result.spec_ratio}")
    print(f"dehydration_required={result.dehydration_required}")
    print(f"dehydration_warning={result.dehydration_warning}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()
