"""Command line: run a design from a spec/basis JSON, or render figures from a saved result."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .figures import FigureMeta
from .handoff import write_handoff
from .runner import load_result, run_design
from .spec import UmbilicalSpec


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="umbilical_design", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="size the umbilical from a spec or COMMON_BASIS JSON and write the hand-off")
    run.add_argument("--spec", required=True, help="JSON file: an umbilical spec, or a basis with an 'umbilical' block")
    run.add_argument("--out", required=True)
    run.add_argument("--title", default=None)
    run.add_argument("--basis-version", default=None)

    render = sub.add_parser("render", help="render figures and hand-off from a saved design result JSON")
    render.add_argument("--result", required=True)
    render.add_argument("--out", required=True)
    render.add_argument("--title", default="Umbilical")
    render.add_argument("--basis-version", default="not stated")

    args = parser.parse_args(argv)
    if args.command == "run":
        data = json.loads(Path(args.spec).read_text(encoding="utf-8"))
        spec = UmbilicalSpec.from_common_basis(data) if "umbilical" in data else UmbilicalSpec.from_dict(data)
        version = args.basis_version or str(data.get("created", "not stated"))
        result = run_design(spec)
        paths = write_handoff(result, Path(args.out), spec, FigureMeta(args.title or spec.name, version))
    else:
        result = load_result(args.result)
        paths = write_handoff(result, Path(args.out), None, FigureMeta(args.title, args.basis_version))
    for name, path in paths.items():
        print("%-12s %s" % (name, path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
