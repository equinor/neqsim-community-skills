"""Synthetic tie-in: a gas condensate commingled into an asphaltenic host oil.

Public, invented compositions. Run with the neqsim package installed:

    python examples/heavy_oil_condensate_tie_in.py
"""

from __future__ import annotations

import json
import sys

from fluid_commingling_compatibility import (
    EvaluationConditions,
    FluidSpec,
    NeqSimBlendEvaluator,
    NeqSimUnavailableError,
    PseudoComponent,
    ScreeningLimits,
    mole_fraction_from_mass_rates,
    screen_commingling,
)

HOST_OIL = FluidSpec(
    label="host",
    asphaltenic=True,
    components={
        "nitrogen": 0.3,
        "CO2": 1.0,
        "H2S": 0.02,
        "methane": 18.0,
        "ethane": 6.0,
        "propane": 5.0,
        "i-butane": 1.0,
        "n-butane": 3.0,
        "i-pentane": 1.2,
        "n-pentane": 1.8,
        "n-hexane": 2.5,
    },
    pseudo_components=[
        PseudoComponent("C7", 7.0, 0.100, 0.75),
        PseudoComponent("C10", 12.0, 0.140, 0.80),
        PseudoComponent("C15", 14.0, 0.210, 0.85),
        PseudoComponent("C30", 20.0, 0.450, 0.93),
    ],
)

NEW_CONDENSATE = FluidSpec(
    label="tiein",
    components={
        "nitrogen": 0.6,
        "CO2": 2.5,
        "H2S": 0.05,
        "methane": 72.0,
        "ethane": 8.0,
        "propane": 5.0,
        "i-butane": 1.0,
        "n-butane": 1.8,
        "i-pentane": 0.7,
        "n-pentane": 0.8,
        "n-hexane": 1.0,
    },
    pseudo_components=[
        PseudoComponent("C7", 4.0, 0.098, 0.74),
        PseudoComponent("C10", 2.0, 0.135, 0.78),
        PseudoComponent("C15", 0.6, 0.200, 0.81),
    ],
)

CONDITIONS = EvaluationConditions(
    commingling_pressure_bara=200.0,
    commingling_temperature_c=80.0,
    path_end_pressure_bara=20.0,
    path_points=12,
    separator_pressure_bara=40.0,
    separator_temperature_c=60.0,
    hydrate_pressure_bara=120.0,
)

# Synthetic "measured" onset refractive index from an n-heptane titration.
LIMITS = ScreeningLimits(
    onset_ri=1.445,
    min_operating_temperature_c=25.0,
    h2s_limit_ppm=400.0,
    co2_limit_mol_pct=3.0,
)


def main() -> int:
    try:
        evaluator = NeqSimBlendEvaluator()
    except NeqSimUnavailableError as exc:
        print(f"SKIPPED: {exc}")
        return 0
    # Where does the planned operating point sit on the blend axis?
    host_kg_h, tiein_kg_h = 150_000.0, 25_000.0
    x_operating = mole_fraction_from_mass_rates(
        host_kg_h,
        evaluator.molar_mass_kg_mol(HOST_OIL),
        tiein_kg_h,
        evaluator.molar_mass_kg_mol(NEW_CONDENSATE),
    )
    print(
        f"{tiein_kg_h / 1000:.0f} t/h condensate into {host_kg_h / 1000:.0f} t/h "
        f"oil is x_B = {x_operating:.2f} (mole fraction)\n"
    )
    report = screen_commingling(
        HOST_OIL,
        NEW_CONDENSATE,
        CONDITIONS,
        evaluator,
        fractions=(0.0, 0.1, 0.2, 0.3, 0.4, round(x_operating, 2), 0.7, 1.0),
        limits=LIMITS,
    )
    print(report.to_markdown())
    if "--json" in sys.argv:
        print(json.dumps(report.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
