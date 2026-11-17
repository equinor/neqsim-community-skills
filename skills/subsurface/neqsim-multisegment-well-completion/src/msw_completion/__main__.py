"""Command line: ``<python> -m msw_completion run config.json`` or ``... devices deck.DATA``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from .runner import read_device_layer
from .workflow import run_completion_workflow


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="msw_completion", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the configured completion workflow")
    run.add_argument("config")
    dev = sub.add_parser(
        "devices", help="summarise the device layer of a completor deck"
    )
    dev.add_argument("deck")
    args = parser.parse_args(argv)
    if args.command == "run":
        evidence = run_completion_workflow(
            json.loads(Path(args.config).read_text(encoding="utf-8"))
        )
        layer = {
            w: v["device_segments"] for w, v in evidence.get("device_layer", {}).items()
        }
        screening = evidence.get("screening") or {}
        print(
            f"status={evidence['status']} devices={layer} "
            f"water_change={screening.get('water_change_fraction')} gas_change={screening.get('gas_change_fraction')} "
            f"missing={evidence['missing']} evidence={evidence['outputs'].get('evidence')}"
        )
        return 0 if evidence["status"] == "ok" else 2
    summary = read_device_layer(
        Path(args.deck).read_text(encoding="utf-8", errors="replace")
    )
    print(
        json.dumps(
            {
                w: {k: v for k, v in s.items() if k != "devices"}
                for w, s in summary.items()
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
