"""Benchmark model densities against CoolProp reference densities.

CoolProp is optional. Without it the example explains how to install it and
exits cleanly, so the skill remains runnable in a minimal environment.

The stand-in ``model_density`` is a deliberately crude fixed-Z model, so most of
these dense-phase points are *expected* to come out FAIL. That is the point of
the example: the gate catches a model that is not fit for the state it is being
used at, instead of reporting a comfortable average.

In a real task the ``model_density`` function is replaced by a NeqSim flash::

    fluid = SystemSrkEos(temperature_K, pressure_Pa / 1.0e5)
    fluid.addComponent("CO2", 1.0)
    fluid.setMixingRule("classic")
    ThermodynamicOperations(fluid).TPflash()
    fluid.initProperties()
    value = fluid.getDensity("kg/m3")
"""

from __future__ import annotations

import json

from benchmark_reference_data import BenchmarkReport, compare
from benchmark_reference_data.coolprop_backend import (
    INSTALL_HINT,
    coolprop_version,
    is_available,
    reference_grid,
)

TEMPERATURES_K = (280.0, 300.0, 320.0)
PRESSURES_PA = (5.0e6, 10.0e6)


def model_density(temperature_K: float, pressure_Pa: float) -> float:
    """Deliberately crude fixed-Z stand-in for the value a NeqSim flash returns."""
    molar_mass = 0.0440098  # kg/mol, CO2
    gas_constant = 8.31446
    compressibility = 0.75
    return pressure_Pa * molar_mass / (compressibility * gas_constant * temperature_K)


def main() -> None:
    if not is_available():
        print("CoolProp is not installed — {}".format(INSTALL_HINT))
        print("Falling back: run validate_against_anchor_points.py instead.")
        return

    print("CoolProp version: {}".format(coolprop_version()))
    print(
        "NOTE: the stand-in model is a crude fixed-Z correlation, so FAIL rows "
        "below are the expected demonstration outcome.\n"
    )
    references = reference_grid("co2", "density", TEMPERATURES_K, PRESSURES_PA)

    report = BenchmarkReport(
        title="CO2 density vs CoolProp HEOS",
        description="Dense-phase CO2 density on a 3x2 (T, P) grid.",
    )
    for reference in references:
        state = reference.state
        report.add(
            compare(
                "CO2 density at {:g} K, {:g} bar".format(
                    state["temperature_K"], state["pressure_Pa"] / 1.0e5
                ),
                model_density(state["temperature_K"], state["pressure_Pa"]),
                reference,
            )
        )

    print(report.to_markdown())
    print()
    print(json.dumps(report.to_results_json(), indent=2))


if __name__ == "__main__":
    main()
