"""Example: build produced waters and run screening-level scale evaluation.

Run with:

    python examples/scale_screening_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from produced_water_scale_screening import ProducedWaterBuilder, ScaleScreener


def main() -> None:
    builder = ProducedWaterBuilder()

    # Barium-rich formation water (no sulfate) and sulfate-rich seawater.
    formation = builder.build(
        preset="formation_water_high_ba", ph=6.5, name="formation_water"
    )
    seawater = builder.build(preset="seawater", ph=8.1, name="seawater")

    print("=== Produced water summary ===")
    for water in (formation, seawater):
        print(f"\n{water.name}")
        print(f"  TDS (mg/L)              : {water.tds_mg_l:,.0f}")
        print(f"  Ionic strength (mol/kg) : {water.ionic_strength_mol_kg:.3f}")
        print(f"  Charge balance error (%): {water.charge_balance_error_pct:.1f}")
        print(f"  NeqSim available        : {water.neqsim_available}")
        print("  NeqSim mole fractions (electrolyte-CPA builder input):")
        for comp, frac in water.neqsim_components.items():
            print(f"    {comp:<8}: {frac:.6e}")
        for warn in water.warnings:
            print(f"  WARNING: {warn}")

    screener = ScaleScreener()

    print("\n=== Standalone scale screening (seawater) ===")
    screening = screener.screen(seawater)
    for result in screening.results:
        si = "n/a" if result.saturation_index is None else f"{result.saturation_index:+.2f}"
        print(f"  {result.salt:<6}  SI={si:<6}  risk={result.risk}")

    print("\n=== Mixing incompatibility (formation water x seawater) ===")
    incompat = screener.mixing_incompatibility(formation, seawater, steps=11)
    for item in incompat:
        si = (
            "n/a"
            if item.worst_saturation_index is None
            else f"{item.worst_saturation_index:+.2f}"
        )
        print(
            f"  {item.salt:<6}  worst SI={si:<6}  "
            f"at fraction_a={item.worst_fraction_a:.2f}  risk={item.risk}"
        )

    print("\n=== Corrosion screening flags ===")
    for flag in screener.corrosion_flags(seawater, co2_mol_percent=3.0, h2s_mol_percent=0.05):
        print(f"  - {flag}")

    print(
        "\nSCREENING ONLY. Use neqsim.thermo.util.ProducedWaterFluidBuilder and "
        "ThermodynamicOperations.checkScalePotential for validated scale work."
    )


if __name__ == "__main__":
    main()
