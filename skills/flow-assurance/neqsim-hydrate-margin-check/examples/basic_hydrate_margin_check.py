from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hydrate_margin_check import HydrateMarginModel


def main() -> None:
    model = HydrateMarginModel()
    result = model.evaluate(
        operating_temperature=10.0,
        hydrate_equilibrium_temperature=8.0,
    )

    print("Hydrate margin check result")
    print(f"hydrate_margin_c={result.hydrate_margin_c}")
    print(f"subcooling_c={result.subcooling_c}")
    print(f"margin_warning={result.margin_warning}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()
