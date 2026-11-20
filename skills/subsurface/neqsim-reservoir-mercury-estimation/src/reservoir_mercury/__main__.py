"""Command line: ``python -m reservoir_mercury estimate --prospect p.json --registry r.json --tests t.csv --out DIR``."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Sequence
from typing import Any

from .estimate import estimate_prospect
from .limits import MercuryLimitUnavailable, mercury_limits
from .model import load_registry
from .report import write_report


def read_tests(path: str) -> list[dict[str, Any]]:
    """Read tested intervals from CSV, converting numeric columns and booleans."""
    rows = []
    with open(path, "r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            item: dict[str, Any] = {}
            for key, value in row.items():
                if value is None or value == "":
                    item[key] = None
                elif value in ("True", "False"):
                    item[key] = value == "True"
                else:
                    try:
                        item[key] = float(value)
                    except ValueError:
                        item[key] = value
            rows.append(item)
    return rows


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line interface.

    Args:
        argv: Arguments; default ``sys.argv[1:]``.

    Returns:
        Process exit code.
    """
    parser = argparse.ArgumentParser(prog="reservoir_mercury", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    est = sub.add_parser(
        "estimate",
        help="estimate mercury in the gas of a prospect or discovery and write a report",
    )
    est.add_argument(
        "--prospect", required=True, help="JSON file with the prospect description"
    )
    est.add_argument("--registry", required=True, help="calibration registry JSON")
    est.add_argument(
        "--tests", help="CSV with the tested intervals of the calibration set"
    )
    est.add_argument(
        "--measurement",
        type=float,
        action="append",
        help="gas reading in the discovery, ug/Sm3",
    )
    est.add_argument(
        "--no-limits", action="store_true", help="skip the NeqSim mineral limits"
    )
    est.add_argument("--out", required=True, help="output folder")
    args = parser.parse_args(argv)
    with open(args.prospect, "r", encoding="utf-8") as handle:
        prospect = json.load(handle)
    registry = load_registry(args.registry)
    tests = read_tests(args.tests) if args.tests else []
    limits = None
    if not args.no_limits and prospect.get("res_T_C") and prospect.get("res_P_bara"):
        try:
            limits = mercury_limits(
                float(prospect["res_T_C"]),
                float(prospect["res_P_bara"]),
                fluid_type=prospect.get("fluid_type") or "gas",
                co2_molpct=float(prospect.get("co2_molpct") or 2.0),
                trace_activity=float(registry.get("trace_sulfide_activity", 0.003)),
            )
        except MercuryLimitUnavailable as exc:
            print(f"limits skipped: {exc}", file=sys.stderr)
    result = estimate_prospect(
        prospect,
        registry,
        tests,
        limits,
        args.measurement or prospect.get("gas_readings"),
    )
    files = write_report(result, args.out, registry=registry, tests=tests)
    print(
        json.dumps(
            {
                "best_estimate": result["best_estimate"],
                "p10": result["p10"],
                "p90": result["p90"],
                "recommended_range": result["recommended_range"],
                "files": files,
            },
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
