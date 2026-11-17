"""Command line: ``run config.json`` or ``setup [--version V] [--dest DIR]``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .runtime import DEFAULT_VERSION, TsaUnavailable, setup_assemblies
from .workflow import run_identification


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dynamic_identification")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the configured identification")
    run.add_argument("config")
    setup = sub.add_parser("setup", help="publish the TimeSeriesAnalysis assemblies from NuGet (once, needs dotnet)")
    setup.add_argument("--version", default=DEFAULT_VERSION)
    setup.add_argument("--dest", default=None)
    args = parser.parse_args(argv)
    if args.command == "setup":
        try:
            print(f"assemblies in {setup_assemblies(args.version, Path(args.dest) if args.dest else None)}")
            return 0
        except TsaUnavailable as exc:
            print(f"setup failed: {exc}", file=sys.stderr)
            return 2
    evidence = run_identification(json.loads(Path(args.config).read_text(encoding="utf-8")))
    loop = evidence["results"].get("loop", {})
    process = loop.get("process_closed_loop", {}) or evidence["results"].get("unit", {})
    usable = {k: v.get("usable") for k, v in (("pid", loop.get("pid") or {}), ("process", process)) if v}
    print(f"status={evidence['status']} usable={usable} pid={ {k: loop.get('pid', {}).get(k) for k in ('kp', 'ti_s')} } "
          f"gains={process.get('gains')} T={process.get('time_constant_s')} delay={process.get('time_delay_s')} "
          f"warnings={len(evidence['warnings'])} missing={evidence['missing']} "
          f"evidence={evidence['outputs'].get('evidence')}")
    return 0 if evidence["status"] == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
