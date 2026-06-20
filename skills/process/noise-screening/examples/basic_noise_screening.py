import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from noise_screening import ValveNoiseModel


def main() -> None:
    model = ValveNoiseModel()
    result = model.evaluate(
        mass_flow=12.0,
        pressure_drop=40.0,
        inlet_density=35.0,
        specific_heat_ratio=1.3,
        temperature=310.0,
        molar_mass=19.0,
    )

    print(f"vena_contracta_velocity_m_s   : {result.vena_contracta_velocity_m_s}")
    print(f"mach_number                   : {result.mach_number}")
    print(f"internal_sound_power_level_db : {result.internal_sound_power_level_db}")
    print(f"estimated_spl_1m_dba          : {result.estimated_spl_1m_dba}")
    print(f"noise_warning                 : {result.noise_warning}")
    print(f"neqsim_available              : {result.neqsim_available}")
    for line in result.assumptions:
        print(f"  - {line}")


if __name__ == "__main__":
    main()
