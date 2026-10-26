"""Command line: search the catalog, describe a layer, run a bounded query.

    python -m sodir_open_data search wellbore formation top
    python -m sodir_open_data describe wellbore_dst
    python -m sodir_open_data query field "fldName='TROLL'" --max-rows 5
    python -m sodir_open_data usecase reserves
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import List

from . import catalog
from .client import SodirOpenData
from .guides import USE_CASES, use_case


def main(argv: List[str]) -> int:
    """Run the CLI and return the process exit code."""
    parser = argparse.ArgumentParser(prog="sodir_open_data")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("search")
    p.add_argument("text", nargs="+")
    p = sub.add_parser("describe")
    p.add_argument("layer")
    p = sub.add_parser("query")
    p.add_argument("layer")
    p.add_argument("where", nargs="?", default="1=1")
    p.add_argument("--max-rows", type=int, default=20)
    p = sub.add_parser("usecase")
    p.add_argument("topic", nargs="?")
    args = parser.parse_args(argv)
    if args.cmd == "search":
        for item in catalog.search(" ".join(args.text)):
            print(f"{item['id']:>5} {item['name']:<40} {item['kind']:<5} {item['score']}")
    elif args.cmd == "describe":
        print(catalog.describe(args.layer))
    elif args.cmd == "query":
        rows = SodirOpenData().query(args.layer, args.where, max_rows=args.max_rows)
        print(json.dumps(rows, indent=1, default=str))
    else:
        if args.topic:
            print(json.dumps(use_case(args.topic), indent=1))
        else:
            print("\n".join(sorted(USE_CASES)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
