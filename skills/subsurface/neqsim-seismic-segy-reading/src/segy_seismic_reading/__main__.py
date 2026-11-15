"""Command line: ``python -m segy_seismic_reading <file-or-folder> [--out evidence.json]``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .evidence import scan_folder, to_evidence, write_evidence
from .geometry import inspect_segy


def main(argv=None) -> int:
    """Print or write the evidence record of a SEG-Y file or every SEG-Y file in a folder."""
    parser = argparse.ArgumentParser(prog="segy_seismic_reading", description=__doc__)
    parser.add_argument("path", help="SEG-Y file or folder to scan")
    parser.add_argument("--out", help="write the evidence JSON here instead of stdout")
    parser.add_argument("--coordinates", default="cdp", choices=["cdp", "source", "group"],
                        help="trace-header coordinate pair to use")
    args = parser.parse_args(argv)

    target = Path(args.path)
    if target.is_dir():
        records = scan_folder(target)
    else:
        records = to_evidence(inspect_segy(target, coordinate_source=args.coordinates))
    if args.out:
        write_evidence(records, args.out)
        count = len(records) if isinstance(records, list) else 1
        sys.stdout.write(f"wrote {count} seismic_dataset_evidence.v1 record(s) to {args.out}\n")
    else:
        json.dump(records, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
