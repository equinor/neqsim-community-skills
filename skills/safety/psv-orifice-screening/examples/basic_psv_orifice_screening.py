from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from psv_orifice_screening import PsvOrificeModel


def main() -> None:
    model = PsvOrificeModel()
    result = model.evaluate(
        relief_rate=50000.0,
        relieving_pressure=20.0,
        temperature=323.15,
        molecular_weight=19.0,
    )

    print("PSV orifice screening result")
    print(f"coefficient_c={result.coefficient_c}")
    print(f"required_area_mm2={result.required_area_mm2}")
    print(f"selected_orifice={result.selected_orifice}")
    print(f"selected_orifice_area_mm2={result.selected_orifice_area_mm2}")
    print(f"area_margin_ratio={result.area_margin_ratio}")
    print(f"psv_warning={result.psv_warning}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()
