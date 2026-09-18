from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from compressor_power_screening import CompressorPowerModel


def main() -> None:
    model = CompressorPowerModel()
    result = model.evaluate(
        suction_pressure=30.0,
        discharge_pressure=90.0,
        suction_temperature=313.15,
        mass_flow=25.0,
        molecular_weight=19.0,
        rated_power=8000.0,
    )

    print("Compressor power screening result")
    print(f"pressure_ratio={result.pressure_ratio}")
    print(f"polytropic_head_kj_kg={result.polytropic_head_kj_kg}")
    print(f"discharge_temperature_k={result.discharge_temperature_k}")
    print(f"gas_power_kw={result.gas_power_kw}")
    print(f"power_margin_ratio={result.power_margin_ratio}")
    print(f"compressor_warning={result.compressor_warning}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()
