"""Demo: classify points, build a VFPPROD table, re-parse it, and post-process."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vfp_generation import (  # noqa: E402
    classify_named,
    enforce_monotonic,
    format_eclipse_vfp,
    parse_vfp_text,
)


def main() -> None:
    # 1. Classify a few compressor readings against their limits.
    print("motor_power 498.5 vs 500 MW:", classify_named("motor_power", 498.5, 500.0))
    print("surge_margin 8% :", classify_named("surge_margin", 8.0, 0.0))
    print("chart_envelope 1.04 vs 1.0:", classify_named("chart_envelope", 1.04, 1.0))

    # 2. Build a small synthetic VFPPROD table.
    flow = [1.0e6, 5.0e6, 1.0e7]
    pout = [80.0, 100.0, 120.0]
    matrix = [
        [40.0, 50.0, 60.0],
        [55.0, 65.0, 75.0],
        [70.0, 80.0, 90.0],
    ]
    text = format_eclipse_vfp(
        table_id=1,
        datum_depth=335.0,
        flow_rates_sm3day=flow,
        outlet_pressures_bara=pout,
        inlet_pressure_matrix=matrix,
        traceability={"conf_id": "demo", "region": "example", "hard_constraints": ["motor_power"]},
    )
    print("\n--- VFPPROD text ---")
    print(text)

    # 3. Round-trip: parse the text we just wrote.
    tables = parse_vfp_text(text, source_file="demo.VFP")
    tbl = tables[0]
    print("Parsed table id:", tbl.table_id, "datum:", tbl.datum_depth)
    print("Flow axis (MSm3/d):", tbl.flow_rates_MSm3d)
    print("Inlet matrix row 0:", tbl.inlet_pressures[0])

    # 4. Enforce monotonicity on a noisy curve.
    noisy = [[10.0, 9.0, 12.0, 11.0]]
    print("Monotonic:", enforce_monotonic(noisy))


if __name__ == "__main__":
    main()
