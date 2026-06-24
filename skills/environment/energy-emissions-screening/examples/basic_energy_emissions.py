"""Minimal field-life energy and emissions screening example.

Run from inside the skill folder:

    python examples/basic_energy_emissions.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from energy_emissions_screening import EnergyEmissionsModel


def main() -> None:
    model = EnergyEmissionsModel()
    result = model.evaluate(
        annual_energy_use_mwh=[120000.0, 180000.0, 175000.0, 150000.0, 120000.0],
        emission_factor_kg_co2e_per_mwh=450.0,
        annual_production_boe=[3.0e6, 7.0e6, 6.5e6, 5.0e6, 3.5e6],
        co2_tax_usd_per_tonne=85.0,
    )

    print(f"Total CO2e (tonnes):        {result.total_co2e_tonnes}")
    print(f"Carbon intensity (kg/boe):  {result.carbon_intensity_kg_per_boe}")
    print(f"Total emission cost (MUSD): {result.total_emission_cost_musd}")
    print(f"Intensity warning:          {result.intensity_warning}")
    print("Assumptions:")
    for line in result.assumptions:
        print(f"  - {line}")


if __name__ == "__main__":
    main()
