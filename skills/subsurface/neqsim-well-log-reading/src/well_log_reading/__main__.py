"""Command line: ``python -m well_log_reading <file-or-folder> [--out evidence.json] [--csv DIR]``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .evidence import scan_folder, to_evidence, write_evidence, write_frame_csv
from .readers import read_well_log


def main(argv=None) -> int:
    """Print or write a curve inventory for a log file or every log file in a folder."""
    parser = argparse.ArgumentParser(prog="well_log_reading", description=__doc__)
    parser.add_argument("path", help="DLIS, LIS or LAS file, or a folder to scan")
    parser.add_argument("--out", help="write the evidence JSON here instead of stdout")
    parser.add_argument(
        "--csv", help="also write the main frame of a single file as CSV here"
    )
    parser.add_argument(
        "--no-recursive", action="store_true", help="do not scan sub-folders"
    )
    args = parser.parse_args(argv)

    target = Path(args.path)
    if target.is_dir():
        records = scan_folder(target, recursive=not args.no_recursive)
    else:
        log = read_well_log(target)
        records = to_evidence(log)
        if args.csv:
            records["csv"] = str(write_frame_csv(log, args.csv))
    if args.out:
        write_evidence(records, args.out)
        count = len(records) if isinstance(records, list) else 1
        sys.stdout.write(
            f"wrote {count} well_log_evidence.v1 record(s) to {args.out}\n"
        )
    else:
        json.dump(records, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
