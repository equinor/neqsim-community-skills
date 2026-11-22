"""Synthetic wet-gas flowline: CO2 corrosion profile and materials review.

A 12 km, 10-inch subsea flowline carries wet gas with 3 mol % CO2 and some
produced water from 110 bara and 85 C, cooling towards 4 C seawater. Public,
invented data. Run with neqsim installed:

    python examples/wet_gas_flowline.py [--json]
"""

from __future__ import annotations

import json
import sys
import time

from co2_corrosion_profile import (
    CorrosionFluid,
    DesignBasis,
    NeqSimUnavailableError,
    PipelineSpec,
    PseudoCut,
    assess_corrosion_profile,
    neqsim_pipeline_profile,
)

FLUID = CorrosionFluid(
    components={
        "nitrogen": 0.8,
        "CO2": 3.0,
        "H2S": 0.0005,
        "methane": 82.0,
        "ethane": 6.0,
        "propane": 3.0,
        "n-butane": 1.5,
        "n-pentane": 0.6,
        "water": 2.0,
    },
    pseudo_components=[PseudoCut("C7", 0.8, 0.100, 0.75)],
    chloride_mg_l=20000.0,
)

PIPE = PipelineSpec(
    length_m=12000.0,
    inner_diameter_m=0.254,
    mass_flow_kg_h=90000.0,
    inlet_pressure_bara=110.0,
    inlet_temperature_c=85.0,
    segments=12,
    elevation_change_m=-50.0,
    ambient_temperature_c=4.0,
    overall_u_w_m2k=15.0,
)

BASIS = DesignBasis(
    design_life_years=25.0,
    corrosion_allowance_mm=6.0,
    inhibitor_availability=0.9,
    inhibited_rate_mm_y=0.1,
    inner_diameter_m=PIPE.inner_diameter_m,
)


def main() -> int:
    try:
        t0 = time.perf_counter()
        profile = neqsim_pipeline_profile(FLUID, PIPE)
    except NeqSimUnavailableError as exc:
        print(f"SKIPPED: {exc}")
        return 0
    report = assess_corrosion_profile(FLUID, profile, BASIS)
    print(report.to_markdown())
    print(f"({len(profile)} stations in {time.perf_counter() - t0:.0f} s)")
    if "--json" in sys.argv:
        print(json.dumps(report.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
