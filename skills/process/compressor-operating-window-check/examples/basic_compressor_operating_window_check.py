from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from compressor_operating_window import CompressorOperatingWindowModel


def main() -> None:
    model = CompressorOperatingWindowModel()
    result = model.evaluate(
        operating_flow=1300.0,
        surge_flow=1000.0,
        stonewall_flow=2000.0,
    )

    print("Compressor operating window check result")
    print(f"surge_margin_fraction={result.surge_margin_fraction}")
    print(f"stonewall_margin_fraction={result.stonewall_margin_fraction}")
    print(f"limiting_margin_fraction={result.limiting_margin_fraction}")
    print(f"operating_window_warning={result.operating_window_warning}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()
