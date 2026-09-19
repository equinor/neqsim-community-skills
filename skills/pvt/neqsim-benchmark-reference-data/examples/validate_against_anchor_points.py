"""Benchmark a set of model values against the offline anchor table.

Runs with no optional dependency: no CoolProp, no NeqSim, no network. The model
values here stand in for whatever a task actually computed.
"""

from __future__ import annotations

import json

from benchmark_reference_data import BenchmarkReport, compare, find_anchor

# Stand-ins for values a task would read from a NeqSim fluid.
MODEL_VALUES = {
    "co2_critical_temperature": 304.2,
    "co2_critical_pressure": 7.38e6,
    "methane_critical_temperature": 190.6,
    "water_normal_boiling_point": 373.0,
    "water_density_ambient": 998.0,
}


def main() -> None:
    report = BenchmarkReport(
        title="SRK pure-component anchors vs reference formulations",
        description=(
            "Pure-component critical constants and one ambient liquid density "
            "compared against IAPWS-95 and the Span-Wagner / Setzmann-Wagner "
            "reference equations of state."
        ),
    )

    report.add(
        compare(
            "CO2 critical temperature",
            MODEL_VALUES["co2_critical_temperature"],
            find_anchor("co2", "critical_temperature"),
        )
    )
    report.add(
        compare(
            "CO2 critical pressure",
            MODEL_VALUES["co2_critical_pressure"],
            find_anchor("co2", "critical_pressure"),
        )
    )
    report.add(
        compare(
            "Methane critical temperature",
            MODEL_VALUES["methane_critical_temperature"],
            find_anchor("methane", "critical_temperature"),
        )
    )
    report.add(
        compare(
            "Water normal boiling point",
            MODEL_VALUES["water_normal_boiling_point"],
            find_anchor("water", "normal_boiling_point", pressure_Pa=101325.0),
        )
    )
    report.add(
        compare(
            "Water density at 25 C, 1 atm",
            MODEL_VALUES["water_density_ambient"],
            find_anchor(
                "water", "density", temperature_K=298.15, pressure_Pa=101325.0
            ),
        )
    )

    print(report.to_markdown())
    print()
    print("results.json benchmark_validation block:")
    print(json.dumps(report.to_results_json(), indent=2))


if __name__ == "__main__":
    main()
