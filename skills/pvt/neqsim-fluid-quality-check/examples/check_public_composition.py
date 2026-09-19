from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fluid_quality_check import FluidQualityChecker


def main() -> None:
    composition = {
        "methane": 0.82,
        "ethane": 0.08,
        "propane": 0.04,
        "CO2": 0.03,
        "water": 0.03,
    }

    checker = FluidQualityChecker(required_components=("methane", "ethane", "propane"))
    result = checker.check(composition)

    print("Fluid quality result")
    print(f"total_fraction={result.total_fraction}")
    print(f"is_usable={result.is_usable}")
    print(f"flagged_components={result.flagged_components}")
    print(f"warnings={list(result.warnings)}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()