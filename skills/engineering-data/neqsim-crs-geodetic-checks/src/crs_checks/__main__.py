"""Command line: ``check config.json`` or ``transform SRC DST X Y [--operation EPSG:n]``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .transform import CrsError, transform
from .workflow import run_crs_check


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="crs_checks")
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="run the configured CRS checks")
    check.add_argument("config")
    one = sub.add_parser("transform", help="transform one point with provenance")
    one.add_argument("src")
    one.add_argument("dst")
    one.add_argument("x", type=float)
    one.add_argument("y", type=float)
    one.add_argument("--operation", default=None)
    args = parser.parse_args(argv)
    if args.command == "transform":
        try:
            result = transform([(args.x, args.y)], args.src, args.dst, args.operation)
        except CrsError as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 2
        print(json.dumps({"coordinates": result.coordinates[0], **result.provenance()}, indent=2))
        return 0
    evidence = run_crs_check(json.loads(Path(args.config).read_text(encoding="utf-8")))
    shift = (evidence["results"].get("datum_sensitivity") or {}).get("max_shift_m")
    print(f"status={evidence['status']} engine={evidence['engine']} findings={len(evidence['findings'])} "
          f"datum_shift_m={shift} missing={evidence['missing']} evidence={evidence['outputs'].get('evidence')}")
    return 2 if evidence["status"] == "blocked" else 0


if __name__ == "__main__":
    sys.exit(main())
