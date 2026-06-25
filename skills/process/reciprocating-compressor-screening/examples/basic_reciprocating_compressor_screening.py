from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reciprocating_compressor_screening import ReciprocatingCompressorModel


def main() -> None:
    model = ReciprocatingCompressorModel()
    result = model.evaluate(
        suction_pressure=2.0,
        discharge_pressure=120.0,
        suction_temperature=313.15,
        swept_volume_rate_m3_h=800.0,
        clearance_fraction=0.12,
        rated_rod_load_kn=120.0,
        piston_area_m2=0.04,
    )

    print("Reciprocating compressor screening result")
    print(f"pressure_ratio={result.pressure_ratio}")
    print(f"stages={result.stages}")
    print(f"stage_pressure_ratio={result.stage_pressure_ratio}")
    print(f"volumetric_efficiency={result.volumetric_efficiency}")
    print(f"actual_inlet_capacity_m3_h={result.actual_inlet_capacity_m3_h}")
    print(f"discharge_temperature_k={result.discharge_temperature_k}")
    print(f"rod_load_ratio={result.rod_load_ratio}")
    print(f"capacity_warning={result.capacity_warning}")
    print(f"rod_load_warning={result.rod_load_warning}")


if __name__ == "__main__":
    main()
