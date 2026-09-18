from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from control_authority_screening import ControlAuthorityModel, PeriodObservation


def main() -> None:
    model = ControlAuthorityModel()

    result = model.evaluate(
        controller_output=[62.0, 78.0, 95.0, 100.0, 100.0, 100.0, 88.0, 71.0],
        controlled_variable=[18.2, 18.9, 20.4, 22.1, 23.6, 24.9, 21.0, 19.1],
        output_max=100.0,
        saturation_band=1.0,
        sample_interval_h=0.5,
        set_point=19.0,
        set_point_tolerance=0.5,
        disturbance=[11.0, 11.4, 12.2, 12.9, 13.5, 14.1, 12.6, 11.5],
        limit_value=26.0,
    )

    print("Authority status:", result.authority_status)
    print("Saturation fraction:", result.saturation_fraction)
    print("  upper stop:", result.upper_saturation_fraction)
    print("  lower stop:", result.lower_saturation_fraction)
    print("Variance ratio (saturated / modulating):", result.variance_ratio)
    print("Off set point fraction:", result.off_set_point_fraction)
    print("Max rate (per hour):", result.max_rate_per_hour)
    print("Time to limit (h):", result.time_to_limit_h)
    print("Warnings:")
    for line in result.warnings:
        print("  -", line)

    trend = model.compare_periods(
        [
            PeriodObservation("year 1", 0.25, 1.03),
            PeriodObservation("year 2", 0.45, 0.70),
            PeriodObservation("year 3", 0.53, 0.98),
            PeriodObservation("year 4", 0.78, 1.11),
        ]
    )

    print()
    print("Trend verdict:", trend.verdict)
    print("Saturation change:", trend.saturation_change)
    print("Disturbance relative change:", trend.disturbance_relative_change)
    print(trend.narrative)


if __name__ == "__main__":
    main()
