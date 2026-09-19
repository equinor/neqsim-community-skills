"""Minimal CAPEX/OPEX screening example.

Run from inside the skill folder:

    python examples/basic_capex_opex.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from capex_opex_screening import CapexOpexModel


def main() -> None:
    model = CapexOpexModel()
    result = model.evaluate(
        bare_equipment_cost_musd=120.0,
        installation_factor=3.5,
        contingency_fraction=0.25,
        opex_fraction_of_capex_per_year=0.04,
        annual_energy_use_mwh=180000.0,
        energy_price_usd_per_mwh=60.0,
        project_life_years=20,
    )

    print(f"Total CAPEX (MUSD):            {result.total_capex_musd}")
    print(f"Annual OPEX (MUSD/yr):         {result.total_annual_opex_musd}")
    print(f"Lifecycle OPEX (MUSD):         {result.lifecycle_opex_musd}")
    print(f"Total cost of ownership (MUSD):{result.total_cost_of_ownership_musd}")
    print(f"CAPEX warning:                 {result.capex_warning}")
    print("Assumptions:")
    for line in result.assumptions:
        print(f"  - {line}")


if __name__ == "__main__":
    main()
