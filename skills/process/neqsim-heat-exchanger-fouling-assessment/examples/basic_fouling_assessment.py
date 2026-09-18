from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from heat_exchanger_fouling_assessment import HeatExchangerFoulingModel


def main() -> None:
    model = HeatExchangerFoulingModel()
    result = model.evaluate(
        area=420.0,
        design_overall_coefficient=1250.0,
        hot_mass_flow=180.0,
        hot_specific_heat=3.6,
        hot_inlet_temperature=338.15,
        hot_outlet_temperature=318.15,
        cold_mass_flow=260.0,
        cold_specific_heat=4.0,
        cold_inlet_temperature=288.15,
        cold_outlet_temperature=300.65,
        design_hot_mass_flow=220.0,
        design_cold_mass_flow=300.0,
        design_fouling_allowance=2.0e-4,
        installed_units=3,
    )

    print("Heat exchanger fouling assessment")
    print(f"duty_kw={result.duty_kw} ({result.duty_source})")
    print(f"lmtd_k={result.lmtd_k} reliable={result.lmtd_reliable}")
    print(f"effectiveness={result.effectiveness} ntu={result.ntu}")
    print(f"u_measured_w_m2k={result.u_measured_w_m2k} basis={result.u_measured_basis}")
    print(f"u_normalised_to_design_flow_w_m2k={result.u_normalised_to_design_flow_w_m2k}")
    print(f"u_naive_one_sided_w_m2k={result.u_naive_one_sided_w_m2k}")
    print(f"naive_optimism_percentage_points={result.naive_optimism_percentage_points}")
    print(f"performance_ratio={result.performance_ratio}")
    print(f"fouling_resistance_m2k_w={result.fouling_resistance_m2k_w}")
    print(f"excess_fouling_resistance_m2k_w={result.excess_fouling_resistance_m2k_w}")
    print(f"condition={result.condition}")
    for row in result.maldistribution_scan:
        print(
            f"  credited units={row.units_credited} "
            f"u_apparent={row.u_apparent_w_m2k} ratio={row.performance_ratio}"
        )
    for warning in result.warnings:
        print(f"  warning: {warning}")

    limit = model.capacity_limit(
        effectiveness=result.effectiveness,
        hot_capacity_rate=180.0 * 3.6,
        cold_capacity_rate=260.0 * 4.0,
        set_point_temperature=318.15,
        cold_inlet_temperature=298.15,  # warm-season cooling medium
        required_duty=result.duty_kw,
    )
    print(f"maximum_duty_kw={limit.maximum_duty_kw} limited={limit.limited}")
    print(f"limit_cause={limit.limit_cause}")

    cycle = model.cleaning_interval(
        fouling_resistance_start=2.0e-5,
        fouling_resistance_end=result.fouling_resistance_m2k_w,
        elapsed_days=180.0,
        fouling_resistance_limit=6.0e-4,
        cleaning_residual_fraction=0.4,
    )
    print(f"fouling_rate_m2k_w_per_day={cycle.fouling_rate_m2k_w_per_day}")
    print(f"days_to_limit={cycle.days_to_limit}")
    print(f"achievable_cycle_days={cycle.achievable_cycle_days}")
    print(f"cleaning_effective={cycle.cleaning_effective}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()
