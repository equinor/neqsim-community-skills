"""Command line.

``python -m seismic_structure discover <folder>... [--out inventory.json]``
``python -m seismic_structure run <config.json>`` (see :mod:`seismic_structure.workflow`)
"""

from __future__ import annotations

import argparse
import json
import sys

from .discovery import discover, geometry_attempts, geometry_candidates
from .workflow import run_structure_workflow


def main(argv=None) -> int:
    """Run discovery or the structure workflow; exit 2 when the workflow is blocked."""
    parser = argparse.ArgumentParser(prog="seismic_structure", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser(
        "discover", help="inventory surfaces, seismic, logs and ties in folders"
    )
    d.add_argument("paths", nargs="+")
    d.add_argument("--out")
    r = sub.add_parser("run", help="run the workflow from a JSON config")
    r.add_argument("config")
    args = parser.parse_args(argv)

    if args.command == "discover":
        inventory = discover(args.paths)
        result = {
            "inventory": inventory,
            "geometry_candidates": geometry_candidates(inventory),
            "absent_geometry_rungs": geometry_attempts(inventory),
        }
        text = json.dumps(result, indent=2)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as handle:
                handle.write(text)
            counts = ", ".join(f"{k}={len(v)}" for k, v in inventory.items())
            sys.stdout.write(f"wrote inventory ({counts}) to {args.out}\n")
        else:
            sys.stdout.write(text + "\n")
        return 0

    with open(args.config, encoding="utf-8") as handle:
        config = json.load(handle)
    evidence = run_structure_workflow(config)
    closure = evidence.get("closure") or {}
    sys.stdout.write(
        f"status={evidence['status']} crest={closure.get('crest_m')} spill={closure.get('spill_m')} "
        f"contact={evidence.get('contact_m')} builder_inputs={evidence.get('builder_inputs')} "
        f"missing={evidence['missing']} evidence={evidence['outputs'].get('evidence_json')}\n"
    )
    return 2 if evidence["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
