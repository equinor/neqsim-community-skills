"""Command line entry point: ``<python> -m integrated_well_planning <command> ...``.

Commands: init-study, validate-basis, run-model, envelope, alternatives, drawings, report, all, ledger, runtime, list-cases.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional


def _print(obj) -> None:
    sys.stdout.write(json.dumps(obj, indent=2, default=str) + "\n")


def main(argv: Optional[List[str]] = None) -> int:
    """Run the CLI; returns the process exit code (non-zero when validation fails or a step cannot run)."""
    ap = argparse.ArgumentParser(prog="integrated_well_planning", description="Integrated well planning workflow")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init-study", help="create the study folder and the starting basis")
    s.add_argument("folder")
    s.add_argument("--well-type", default="oil_producer", choices=["oil_producer", "gas_producer", "gas_condensate_producer", "water_injector", "gas_injector"])
    s.add_argument("--environment", default="platform", choices=["onshore", "platform", "subsea"])
    s.add_argument("--basis", help="existing planning basis (YAML/JSON) to start from")
    s.add_argument("--overwrite", action="store_true")
    for name in ("validate-basis", "envelope", "report", "drawings"):
        sub.add_parser(name).add_argument("folder")
    r = sub.add_parser("run-model")
    r.add_argument("folder")
    r.add_argument("--segments", type=int, default=10)
    a = sub.add_parser("alternatives")
    a.add_argument("folder")
    a.add_argument("--no-tornado", action="store_true")
    a.add_argument("--profile-years", default="", help="comma separated years for the deliverability profile")
    a.add_argument("--segments", type=int, default=10)
    al = sub.add_parser("all", help="validate, run-model, alternatives, envelope, drawings, report")
    al.add_argument("folder")
    al.add_argument("--profile-years", default="0,5,10")
    sub.add_parser("ledger").add_argument("--json", action="store_true")
    sub.add_parser("runtime")
    sub.add_parser("list-cases")
    args = ap.parse_args(argv)

    from . import study as st

    if args.cmd == "init-study":
        from .basis import load_basis

        basis = load_basis(Path(args.basis)) if args.basis else None
        paths = st.init_study(Path(args.folder), args.well_type, args.environment, basis, args.overwrite)
        _print({k: str(v) for k, v in paths.items()})
        return 0
    if args.cmd == "validate-basis":
        out = st.validate(Path(args.folder))
        _print(out)
        return 0 if out["status"] != "FAIL" else 2
    if args.cmd == "run-model":
        res = st.run_model(Path(args.folder), args.segments)
        _print({"envelope_summary": res["envelope"]["summary"], "cases": {k: {c: {"status": v["status"], "target_met": v.get("target_met")} for c, v in res[k].items()} for k in ("producer", "injector") if k in res}})
        return 0
    if args.cmd == "envelope":
        _print(st.envelope(Path(args.folder)))
        return 0
    if args.cmd == "alternatives":
        years = [float(x) for x in args.profile_years.split(",") if x.strip()]
        out = st.alternatives(Path(args.folder), not args.no_tornado, years or None, args.segments)
        _print({"recommendation": out["recommendation"], "pareto_front": out["pareto_front"]})
        return 0
    if args.cmd == "drawings":
        from .drawings_run import make_drawings

        _print(make_drawings(Path(args.folder))["register"])
        return 0
    if args.cmd == "report":
        from .report import build_report

        _print(build_report(Path(args.folder)))
        return 0
    if args.cmd == "all":
        root = Path(args.folder)
        v = st.validate(root)
        if v["status"] == "FAIL":
            _print(v)
            return 2
        st.run_model(root)
        st.alternatives(root, True, [float(x) for x in args.profile_years.split(",") if x.strip()] or None)
        st.envelope(root)
        from .drawings_run import make_drawings
        from .report import build_report

        make_drawings(root)
        _print(build_report(root))
        return 0
    if args.cmd == "ledger":
        from .ledger import JAVA_FOLLOW_UPS, ledger_rows, status_counts

        _print({"counts": status_counts(), "ledger": ledger_rows(), "java_follow_ups": JAVA_FOLLOW_UPS} if args.json else status_counts())
        return 0
    if args.cmd == "runtime":
        from .runtime import ensure_runtime

        st_ = ensure_runtime()
        _print(st_.to_dict())
        return 0 if st_.wellplanning_available else 3
    if args.cmd == "list-cases":
        from .examples_data import CASE_NAMES

        _print(sorted(CASE_NAMES.values()))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
