import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from co2_emissions_screening import CombustionCO2Model


def main() -> None:
    model = CombustionCO2Model()
    result = model.evaluate(
        composition={
            "methane": 0.85,
            "ethane": 0.07,
            "propane": 0.03,
            "nitrogen": 0.03,
            "co2": 0.02,
        },
        mass_flow=2.0,
        co2_limit_t_per_day=400.0,
    )

    print(f"mixture_molecular_weight_g_mol : {result.mixture_molecular_weight_g_mol}")
    print(f"carbon_per_mole_fuel           : {result.carbon_per_mole_fuel}")
    print(f"co2_mass_rate_kg_s             : {result.co2_mass_rate_kg_s}")
    print(f"co2_mass_rate_t_per_day        : {result.co2_mass_rate_t_per_day}")
    print(f"specific_co2_kg_per_kg_fuel    : {result.specific_co2_kg_per_kg_fuel}")
    print(f"emission_warning               : {result.emission_warning}")
    print(f"neqsim_available               : {result.neqsim_available}")
    for line in result.assumptions:
        print(f"  - {line}")


if __name__ == "__main__":
    main()
