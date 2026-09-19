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
        distance=3.0,
    )

    print(f"vena_contracta_velocity_m_s   : {result.vena_contracta_velocity_m_s}")
    print(f"mach_number                   : {result.mach_number}")
    print(f"internal_sound_power_level_db : {result.internal_sound_power_level_db}")
    print(f"estimated_spl_1m_dba          : {result.estimated_spl_1m_dba}")
    print(f"estimated_spl_at_distance_dba : {result.estimated_spl_at_distance_dba}")
    print(f"assessment_basis              : {result.assessment_basis}")
    print(f"noise_warning                 : {result.noise_warning}")
    print(f"neqsim_available              : {result.neqsim_available}")
    for line in result.assumptions:
        print(f"  - {line}")

    measured_result = model.evaluate(
        mass_flow=12.0,
        pressure_drop=40.0,
        inlet_density=35.0,
        sound_speed=410.0,
        distance=3.0,
        measured_spl_at_distance=92.0,
        measured_uncertainty_db=2.0,
    )
    print(f"measured_receiver_level_dba   : {measured_result.estimated_spl_at_distance_dba}")
    print(f"measured_assessment_basis     : {measured_result.assessment_basis}")


if __name__ == "__main__":
    main()
