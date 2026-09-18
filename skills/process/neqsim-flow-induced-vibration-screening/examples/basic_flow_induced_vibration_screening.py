from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flow_induced_vibration_screening import FlowInducedVibrationModel


def main() -> None:
    model = FlowInducedVibrationModel()
    result = model.evaluate(
        fluid_velocity=20.0,
        mixture_density=60.0,
        kinetic_energy_threshold=10000.0,
        small_bore_present=False,
    )

    print("Flow-induced vibration screening result")
    print(f"kinetic_energy_pa={result.kinetic_energy_pa}")
    print(f"threshold_ratio={result.threshold_ratio}")
    print(f"likelihood_of_failure_band={result.likelihood_of_failure_band}")
    print(f"fiv_warning={result.fiv_warning}")
    print(f"small_bore_flag={result.small_bore_flag}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()
