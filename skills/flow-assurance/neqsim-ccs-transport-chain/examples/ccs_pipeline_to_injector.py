"""Synthetic CCS chain: captured CO2 from shore to an offshore injector.

95.5 mol % CO2 with N2, Ar, H2, CH4 and 50 ppm(mol) water; 80 km, 16-inch
pipeline from 150 bara and 35 C to 4 C seabed; 1300 m injector into a 120 bara
aquifer. Public, invented data. Run with neqsim installed:

    python examples/ccs_pipeline_to_injector.py [--json]
"""

from __future__ import annotations

import json
import sys
import time

from ccs_transport_chain import (
    ChainLimits,
    Co2Pipeline,
    Co2Stream,
    InjectionWell,
    assess_transport_chain,
)

STREAM = Co2Stream(
    components={
        "CO2": 0.955,
        "nitrogen": 0.02,
        "argon": 0.005,
        "hydrogen": 0.005,
        "oxygen": 0.00002,
        "methane": 0.01488,
        "water": 0.00005,
    },
    so2_ppmv=10.0,
    nox_ppmv=5.0,
)
PIPE = Co2Pipeline(
    length_m=80000.0,
    inner_diameter_m=0.38,
    mass_flow_kg_h=200000.0,
    inlet_pressure_bara=150.0,
    inlet_temperature_c=35.0,
    ambient_temperature_c=4.0,
    overall_u_w_m2k=5.0,
    segments=10,
)
WELL = InjectionWell(
    depth_m=1300.0,
    tubing_inner_diameter_m=0.157,
    reservoir_pressure_bara=120.0,
    top_formation_temperature_c=4.0,
    bottom_formation_temperature_c=45.0,
    fracture_pressure_bara=210.0,
)
LIMITS = ChainLimits(min_single_phase_margin_bar=10.0, maop_bara=180.0)


def main() -> int:
    try:
        import neqsim  # noqa: F401
    except ImportError:
        print("SKIPPED: python -m pip install neqsim")
        return 0
    t0 = time.perf_counter()
    report = assess_transport_chain(STREAM, PIPE, WELL, LIMITS)
    print(report.to_markdown())
    print(f"({time.perf_counter() - t0:.0f} s)")
    if "--json" in sys.argv:
        print(json.dumps(report.to_dict(), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
