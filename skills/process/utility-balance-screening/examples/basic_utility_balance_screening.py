from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from utility_balance_screening import UtilityBalanceModel


def main() -> None:
    model = UtilityBalanceModel()
    result = model.evaluate(
        instrument_air_consumers=120,
        air_per_consumer_nm3_h=0.3,
        cooling_duty_kw=2500.0,
        cooling_water_delta_t_c=10.0,
        fuel_gas_lhv_mj_sm3=39.0,
        fuel_gas_relative_density=0.62,
        instrument_air_capacity_nm3_h=60.0,
        cooling_water_capacity_m3_h=250.0,
    )

    print("Instrument air demand (Nm3/h):", result.instrument_air_demand_nm3_h)
    print("Cooling water flow (m3/h):", result.cooling_water_flow_m3_h)
    print("Wobbe index (MJ/Sm3):", result.wobbe_index_mj_sm3)
    print("Wobbe in band:", result.wobbe_in_band)
    print("Air utilisation:", result.air_utilisation)
    print("Cooling utilisation:", result.cooling_utilisation)
    print("Utility warning:", result.utility_warning)
    print("Wobbe warning:", result.wobbe_warning)
    print("NeqSim available:", result.neqsim_available)
    print("Assumptions:")
    for line in result.assumptions:
        print("  -", line)


if __name__ == "__main__":
    main()
