"""Rebuild the bundled NCS network snapshot from the open APIs.

Usage (shared NeqSim environment)::

    C:\\appl\\neqsim-venv\\Scripts\\python.exe scripts/build_snapshot.py
    ... scripts/build_snapshot.py --raw-cache raw.json      # keep the raw reads
    ... scripts/build_snapshot.py --from-raw raw.json       # rebuild offline

Reads Sodir DataService (fields, discoveries, reserves, descriptions, facilities,
pipelines, yearly profiles) and the norskpetroleum pipeline capacity tables.
Read-only, bounded, no credentials.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from ncs_infrastructure_network.build import build_snapshot, fetch_raw  # noqa: E402

DEFAULT_OUT = HERE.parent / "src" / "ncs_infrastructure_network" / "data" / "ncs_network_snapshot.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--raw-cache", help="also write the raw API reads to this file")
    parser.add_argument("--from-raw", help="build from a previously cached raw file (offline)")
    args = parser.parse_args()

    if args.from_raw:
        raw = json.loads(Path(args.from_raw).read_text(encoding="utf-8"))
    else:
        raw = fetch_raw()
        if args.raw_cache:
            Path(args.raw_cache).write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    snapshot = build_snapshot(raw)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1, sort_keys=False), encoding="utf-8")
    summary = {k: len(v) for k, v in snapshot.items() if isinstance(v, (list, dict))}
    print(json.dumps({"out": str(out), "counts": summary}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
