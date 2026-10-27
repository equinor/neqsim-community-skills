"""Near-field discovery inventory and map for one target (Norway or Brazil).

Examples:
    python near_field_study.py --country NO --name Wisting --lat 73.3 --lon 24.0 --radius 120 --out task/step2_analysis
    python near_field_study.py --country BR --name "Santos target" --lat -25.0 --lon -42.0 --radius 150 --out task/step2_analysis

Network reads are cached under ``<out>/references/anp``; pass ``--offline`` to reuse them.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from near_field_discoveries import (
    brazil_records,
    fetch_anp_layers,
    fetch_ncs_near_field,
    hosts_from_production_units,
    near_field,
    plot_near_field,
)

logger = logging.getLogger("near_field_study")


def main() -> None:
    """Build the inventory, write CSV/JSON/GeoJSON/Markdown and the map."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--country", choices=["NO", "BR"], required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--lon", type=float, required=True)
    ap.add_argument("--radius", type=float, default=100.0, help="km")
    ap.add_argument("--out", required=True)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--bathymetry", action="store_true", help="add ETOPO contours (needs anp_open_data)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    out = Path(args.out)
    point = (args.lon, args.lat)

    layers = {}
    if args.country == "NO":
        data = fetch_ncs_near_field(point, args.radius)
        records, hosts, pipes, log = data["records"], data["hosts"], data["pipelines"], data["log"]
    else:
        raw, log = fetch_anp_layers(point, args.radius, out / "references" / "anp", offline=args.offline)
        records = brazil_records(raw)
        hosts, pipes = hosts_from_production_units(raw["production_units"]), []
        layers = {"blocks": raw["blocks"], "relinquished_blocks": raw["relinquished_blocks"]}
        for entry in log:
            if entry.get("truncated"):
                logger.warning("TRUNCATED read: %s - narrow the radius", entry["layer"])

    inv = near_field(point, args.radius, records, name=args.name, hosts=hosts, pipelines=pipes, layers=layers, log=log)
    paths = inv.write(out)
    grid = None
    if args.bathymetry:
        from anp_open_data import bathymetry as bt
        from near_field_discoveries import bbox_around

        b = bbox_around(point[0], point[1], args.radius * 1.1)
        grid = bt.fetch_etopo_grid((b[0], b[2], b[1], b[3]), out / "references" / "bathymetry", offline=args.offline)
    paths["map"] = str(plot_near_field(inv, out / "near_field_map.png", bathymetry=grid))
    for key, value in paths.items():
        logger.info("%s: %s", key, value)


if __name__ == "__main__":
    main()
