"""Monte Carlo NPV study with a technical/economic split.

Runs with no optional dependency. The ``technical`` stage stands in for the
expensive part (a NeqSim production/process solve); the ``economic`` stage is
cheap, so price and cost parameters never trigger a re-solve.
"""

from __future__ import annotations

import json

from uncertainty_quantification import (
    Triangular,
    UncertaintyReport,
    UncertaintyStudy,
)

PARAMETERS = [
    Triangular(name="GIP", unit="GSm3", low=105.0, base_value=135.0, high=169.0),
    Triangular(name="Recovery factor", unit="-", low=0.45, base_value=0.57, high=0.66),
    Triangular(
        name="Gas price", unit="NOK/Sm3", low=0.8, base_value=1.5, high=2.5, kind="economic"
    ),
    Triangular(
        name="CAPEX multiplier", unit="-", low=0.85, base_value=1.0, high=1.4, kind="economic"
    ),
]


def technical_stage(values):
    """Stand-in for the expensive NeqSim solve: recoverable volume in GSm3."""
    return {"recoverable_GSm3": values["GIP"] * values["Recovery factor"]}


def economic_stage(intermediate, values):
    """Cheap stage: discounted revenue minus CAPEX, in MNOK."""
    volume_Sm3 = intermediate["recoverable_GSm3"] * 1.0e9
    revenue_MNOK = volume_Sm3 * values["Gas price"] / 1.0e6
    capex_MNOK = 14700.0 * values["CAPEX multiplier"]
    return 0.45 * revenue_MNOK - capex_MNOK


def main() -> None:
    study = UncertaintyStudy(
        parameters=PARAMETERS,
        output_name="NPV after tax",
        output_unit="MNOK",
        sampling_method="lhs",
        seed=42,
        technical=technical_stage,
        economic=economic_stage,
        simulation_engine="staged model (technical stage cached)",
    )

    result = study.run(500)
    report = UncertaintyReport(
        parameters=PARAMETERS,
        result=result,
        output_name="NPV after tax",
        output_unit="MNOK",
        tornado=study.tornado(),
        simulation_engine=study.simulation_engine,
    )

    print(report.to_markdown())
    print()
    print("results.json uncertainty block:")
    print(json.dumps(report.to_results_json(), indent=2))


if __name__ == "__main__":
    main()
