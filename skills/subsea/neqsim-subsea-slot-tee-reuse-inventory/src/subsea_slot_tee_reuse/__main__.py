"""Command line: ``python -m subsea_slot_tee_reuse INVENTORY.json [TARGET.json] [--consumer NAME]``."""
from __future__ import annotations

import argparse
import json
import sys

from . import free_slot_table, handoff, rank_reuse_options, summarize, validate_inventory
from .inventory import load


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate and summarise a subsea infrastructure inventory; optionally rank reuse against new-build.")
    ap.add_argument("inventory")
    ap.add_argument("target", nargs="?")
    ap.add_argument("--consumer", choices=["export-tie-in-concept", "surf-design-study", "tie-in-screening", "area-development"])
    ap.add_argument("--year", type=int)
    a = ap.parse_args(argv)
    inv = load(a.inventory)
    out = {"validation": validate_inventory(inv, a.year), "summary": summarize(inv, a.year), "free_slots": free_slot_table(inv, a.year)}
    if a.target:
        target = load(a.target)
        ranking = rank_reuse_options(inv, target, a.year)
        out["ranking"] = ranking
        if a.consumer:
            out["handoff"] = handoff(ranking, target, a.consumer)
    json.dump(out, sys.stdout, indent=1)
    sys.stdout.write("\n")
    return 1 if any(i["level"] == "error" for i in out["validation"]) else 0


if __name__ == "__main__":
    sys.exit(main())
