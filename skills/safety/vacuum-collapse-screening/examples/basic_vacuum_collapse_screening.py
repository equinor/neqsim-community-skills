from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vacuum_collapse_screening import VacuumCollapseModel


def main() -> None:
    model = VacuumCollapseModel()
    result = model.evaluate(
        initial_pressure=1.8,
        initial_temperature=120.0,
        cold_end_temperature=20.0,
        condensable_fraction=0.85,
        external_pressure_rating=0.5,
    )

    print("Vacuum collapse screening result")
    print(f"estimated_final_pressure_bara={result.estimated_final_pressure_bara}")
    print(f"vacuum_depth_bar={result.vacuum_depth_bar}")
    print(f"margin_to_rating_bar={result.margin_to_rating_bar}")
    print(f"vacuum_present={result.vacuum_present}")
    print(f"exceeds_rating={result.exceeds_rating}")
    print(f"verdict={result.verdict}")
    print(f"collapse_warning={result.collapse_warning}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()
