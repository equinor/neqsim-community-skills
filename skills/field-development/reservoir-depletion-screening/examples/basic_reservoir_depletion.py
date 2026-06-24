"""Minimal reservoir-depletion-vs-time screening example.

Run from inside the skill folder:

    python examples/basic_reservoir_depletion.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from reservoir_depletion_screening import ReservoirDepletionModel


def main() -> None:
    model = ReservoirDepletionModel()
    result = model.evaluate(
        fluid_type="gas",
        initial_pressure_bara=300.0,
        abandonment_pressure_bara=80.0,
        recoverable_volume_sm3=20.0e9,
        offtake_rate_sm3_per_day=8.0e6,
        years=15,
        initial_water_cut_fraction=0.05,
        water_cut_rise_per_year=0.03,
    )

    print(f"fluid: {result.fluid_type}")
    print(f"final pressure: {result.final_pressure_bara} bara")
    print(f"final recovery factor: {result.final_recovery_factor:.3f}")
    print(f"plateau years: {result.plateau_years}")
    print(f"years to abandonment: {result.years_to_abandonment}")
    print(f"verdict: {result.depletion_warning}")
    print("year  pressure  RF     water_cut  hc_rate")
    for step in result.steps:
        print(
            f"{step.year:>4.0f}  {step.pressure_bara:>8.1f}  "
            f"{step.recovery_factor:>5.3f}  {step.water_cut_fraction:>8.3f}  "
            f"{step.hydrocarbon_rate_sm3_per_day:>10.0f}"
        )

    print("\nNeqSim available:", result.neqsim_available)
    print("Validated path: NeqSim SimpleReservoir (runTransient) / MCP runReservoir")


if __name__ == "__main__":
    main()
