from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from acoustic_induced_vibration_screening import AcousticInducedVibrationModel


def main() -> None:
    model = AcousticInducedVibrationModel()
    result = model.evaluate(
        mass_flow_kg_s=12.0,
        upstream_pressure_bar=90.0,
        downstream_pressure_bar=20.0,
        pipe_outside_diameter_mm=323.9,
        wall_thickness_mm=9.5,
        molecular_weight=19.0,
        temperature_k=313.15,
        downstream_pipe_length_m=12.0,
    )

    print("Acoustic-induced vibration screening result")
    print(f"pressure_drop_ratio={result.pressure_drop_ratio}")
    print(f"sound_power_level_db={result.sound_power_level_db}")
    print(f"diameter_thickness_ratio={result.diameter_thickness_ratio}")
    print(f"allowable_sound_power_level_db={result.allowable_sound_power_level_db}")
    print(f"likelihood_of_failure={result.likelihood_of_failure}")
    print(f"downstream_pipe_length_m={result.downstream_pipe_length_m}")
    print(f"risk_warning={result.risk_warning}")


if __name__ == "__main__":
    main()
