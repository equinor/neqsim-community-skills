"""Minimal Norwegian Continental Shelf public-data usage example.

Run from inside the skill folder:

    python examples/basic_ncs_data.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from norwegian_continental_shelf_data import (
    load_dataset,
    production_share,
    resource_remaining,
    fields_started_by_decade,
    rank_fields_by_remaining,
    sodir_download_plan,
)


def main() -> None:
    ds = load_dataset()

    print("Attribution:", ds.attribution)
    print("Snapshot date:", ds.snapshot_date)

    prod = ds.national_kpi("annual_production_oe")
    print(
        f"\n{prod['as_of_year']} production: {prod['value']} {prod['unit']}"
        f"  (source: {prod['source_url']})"
    )

    ra = ds.resource_accounting()
    remaining = resource_remaining(
        total_billion_sm3_oe=ra["total_petroleum_resources"]["value"],
        produced_fraction=ra["produced_sold_delivered_fraction"]["value"],
        latest_annual_oe_mill_sm3=prod["value"],
    )
    print(
        f"Remaining resources: {remaining.remaining_billion_sm3_oe} "
        f"billion Sm3 o.e. ({remaining.remaining_fraction:.0%})"
    )
    print(f"Static R/P horizon: {remaining.reserve_to_production_years} years")

    print("\nField counts:", ds.field_counts())
    print("Fields by start decade:", fields_started_by_decade(ds.fields()))

    print("\nBarents Sea fields:")
    for f in ds.list_fields(sea_area="barents_sea"):
        print(f"  {f.name} ({f.operator}, {f.main_product}, from {f.production_start_year})")

    latest = ds.production_for_year(prod["as_of_year"])
    if latest is not None:
        share = production_share(latest)
        print(f"\n{share.year} o.e.: {share.oe_mill_sm3} mill Sm3 o.e.")

    # Per-field reserves are populated by ingesting the official Sodir export.
    # Here we demonstrate the overlay + ranking with illustrative values.
    ds.ingest_field_reserves(
        [
            {"name": "Troll", "remaining_oe_mill_sm3": 900.0},
            {"name": "Johan Sverdrup", "remaining_oe_mill_sm3": 300.0},
        ]
    )
    print("\nTop fields by (illustrative) remaining reserves:")
    for f in rank_fields_by_remaining(ds.fields(), top=2):
        print(f"  {f.name}: {f.remaining_oe_mill_sm3} mill Sm3 o.e.")

    print("\nRefresh plan (official public sources, offline URL builder):")
    for target in sodir_download_plan():
        print(f"  {target.dataset}: {target.factpages_page_url}")

    print("\nValidated path: ingest full Sodir FactPages tables, then use")
    print("NeqSim SimpleReservoir / runReservoir for production forecasting.")


if __name__ == "__main__":
    main()
