from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from compressor_antisurge_recycle import AntiSurgeRecycleModel


def main() -> None:
    model = AntiSurgeRecycleModel()

    # Operating point close to surge with a vendor chart available.
    result = model.plan(
        inlet_flow=4200.0,
        surge_flow=5000.0,
        chart_provided=True,
        current_recycle=0.0,
    )

    print("Compressor anti-surge recycle plan")
    print(f"needs_chart_generation={result.needs_chart_generation}")
    print(f"in_surge={result.in_surge}")
    print(f"surge_margin_fraction={result.surge_margin_fraction}")
    print(f"recommended_recycle_flow={result.recommended_recycle_flow}")
    print(f"total_suction_flow={result.total_suction_flow}")
    print(f"recycle_warning={result.recycle_warning}")
    print(f"neqsim_available={result.neqsim_available}")

    # Same point, but no vendor chart: a chart (with surge and stonewall
    # curves) must be generated in NeqSim first.
    no_chart = model.plan(
        inlet_flow=4200.0,
        surge_flow=5000.0,
        chart_provided=False,
    )
    print()
    print(f"needs_chart_generation (no vendor chart)={no_chart.needs_chart_generation}")


if __name__ == "__main__":
    main()
