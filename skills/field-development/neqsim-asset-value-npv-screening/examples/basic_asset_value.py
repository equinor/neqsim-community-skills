"""Minimal asset-value (NPV) screening example.

Run from inside the skill folder:

    python examples/basic_asset_value.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from asset_value_npv_screening import AssetValueModel


def main() -> None:
    model = AssetValueModel()
    result = model.evaluate(
        annual_revenue_musd=[0.0, 300.0, 320.0, 280.0, 230.0, 180.0],
        annual_opex_musd=40.0,
        capex_schedule_musd=[600.0, 200.0, 0.0, 0.0, 0.0, 0.0],
        discount_rate_fraction=0.08,
        tax_rate_fraction=0.78,
    )

    print(f"NPV (MUSD):            {result.npv_musd}")
    print(f"IRR (fraction):        {result.irr_fraction}")
    print(f"Payback year:          {result.payback_year}")
    print(f"Discounted payback yr: {result.discounted_payback_year}")
    print(f"Value warning:         {result.value_warning}")
    print("Assumptions:")
    for line in result.assumptions:
        print(f"  - {line}")


if __name__ == "__main__":
    main()
