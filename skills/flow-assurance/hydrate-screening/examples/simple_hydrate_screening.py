from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hydrate_screening import HydrateScreener


def main() -> None:
    result = HydrateScreener().screen(
        pressure=80.0,
        temperature=4.0,
        water_present=True,
    )

    print("Hydrate screening result")
    print(f"risk_level={result.risk_level}")
    print(f"margin_indicator={result.margin_indicator}")
    print(f"estimated_boundary={result.estimated_boundary}")
    print(f"neqsim_available={result.neqsim_available}")
    print(f"assumptions={list(result.assumptions)}")


if __name__ == "__main__":
    main()