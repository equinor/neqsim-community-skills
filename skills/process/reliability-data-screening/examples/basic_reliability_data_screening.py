from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reliability_data_screening import ReliabilityDataModel


def main() -> None:
    model = ReliabilityDataModel()
    result = model.evaluate(
        failure_rate_per_year=0.5,
        mean_time_to_repair_h=48.0,
        redundancy=2,
        mission_time_years=1.0,
        planned_downtime_h_per_year=24.0,
    )

    print("MTBF (years):", result.mtbf_years)
    print("MTBF (h):", result.mtbf_h)
    print("Unit availability:", result.unit_availability)
    print("System availability:", result.system_availability)
    print("System unavailability:", result.system_unavailability)
    print("Reliability over mission:", result.reliability_over_mission)
    print("Expected failures:", result.expected_failures)
    print("Availability warning:", result.availability_warning)
    print("NeqSim available:", result.neqsim_available)
    print("Assumptions:")
    for line in result.assumptions:
        print("  -", line)


if __name__ == "__main__":
    main()
