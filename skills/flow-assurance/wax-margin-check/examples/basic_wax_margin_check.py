from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wax_margin_check import WaxMarginModel


def main() -> None:
    model = WaxMarginModel()
    result = model.evaluate(
        operating_temperature=33.0,
        wax_appearance_temperature=30.0,
    )

    print("Wax margin check result")
    print(f"wax_margin_c={result.wax_margin_c}")
    print(f"below_wax_appearance={result.below_wax_appearance}")
    print(f"margin_warning={result.margin_warning}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()
