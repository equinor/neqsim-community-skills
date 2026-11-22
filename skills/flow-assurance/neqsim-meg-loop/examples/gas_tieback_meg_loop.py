"""Synthetic gas-condensate tie-back: size the MEG loop.

8 MSm3/d lean gas saturated with water, 20 m3/d formation water at 60 g/L
TDS; shut-in 150 bara at 4 C seabed with a 3 C hydrate margin; 90 wt % lean
MEG, 30 % reclaimer slipstream. Public, invented data. Run with neqsim
installed:

    python examples/gas_tieback_meg_loop.py [--json]
"""

from __future__ import annotations

import json
import sys
import time

from meg_loop import HydrateDesign, Regeneration, WellStream, assess_meg_loop

STREAM = WellStream(
    components={
        "nitrogen": 1.0,
        "CO2": 2.0,
        "methane": 85.0,
        "ethane": 6.0,
        "propane": 3.0,
        "i-butane": 0.5,
        "n-butane": 0.8,
        "n-pentane": 0.3,
        "n-hexane": 0.2,
        "water": 0.6,
    },
    flow_rate=8.0,
    flow_unit="MSm3/day",
    formation_water_m3_d=20.0,
    formation_water_tds_mg_l=60000.0,
)
DESIGN = HydrateDesign(
    pressure_bara=150.0,
    min_temperature_c=4.0,
    margin_c=3.0,
    arrival_pressure_bara=60.0,
    arrival_temperature_c=15.0,
)
REGEN = Regeneration(
    lean_meg_wt=0.90,
    regenerator_pressure_bara=1.2,
    reclaimer_slipstream=0.30,
    salt_limit_wt=0.05,
    loop_inventory_m3=150.0,
    lean_alternatives=(0.80, 0.85),
)


def main() -> int:
    try:
        import neqsim  # noqa: F401
    except ImportError:
        print("SKIPPED: python -m pip install neqsim")
        return 0
    t0 = time.perf_counter()
    report = assess_meg_loop(STREAM, DESIGN, REGEN)
    print(report.to_markdown())
    print(f"({time.perf_counter() - t0:.0f} s)")
    if "--json" in sys.argv:
        print(json.dumps(report.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
