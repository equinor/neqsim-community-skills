import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dry_gas_seal_screening import DryGasSealModel


def main() -> None:
    model = DryGasSealModel()
    result = model.evaluate(
        seal_leakage_rate_nl_per_min=280.0,
        seal_cavity_temperature_c=44.0,
        hydrocarbon_dew_point_c=40.0,
        seal_count=2,
        supply_margin=1.25,
        separation_gas_rate_nl_per_min=120.0,
    )

    print("total_seal_gas_supply_nl_per_min:", result.total_seal_gas_supply_nl_per_min)
    print(
        "separation_gas_supply_nl_per_min:",
        result.separation_gas_supply_nl_per_min,
    )
    print("condensation_margin_c:", result.condensation_margin_c)
    print("condensation_warning:", result.condensation_warning)
    print("neqsim_available:", result.neqsim_available)
    for assumption in result.assumptions:
        print("-", assumption)


if __name__ == "__main__":
    main()
