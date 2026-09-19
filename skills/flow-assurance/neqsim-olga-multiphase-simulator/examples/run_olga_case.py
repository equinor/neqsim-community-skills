"""End-to-end OLGA batch example: discover, rule-check, run, read results.

Usage::

    python run_olga_case.py path/to/case.genkey [--endtime "600 s"] [--nthreads 4]

The script never edits the original case in place: when ``--endtime`` is given it
writes a variant next to the original so relative PVT-table references still
resolve.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from olga_multiphase_simulator import (
    OlgaNotFoundError,
    OlgaRunner,
    find_olga_installations,
    license_environment,
    read_ppl,
    read_tpl,
    write_variant,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path, help="OLGA .genkey or .key input file")
    parser.add_argument("--endtime", help='Override INTEGRATION ENDTIME, e.g. "600 s"')
    parser.add_argument("--nthreads", type=int, default=None, help="OpenMP threads")
    parser.add_argument("--timeout", type=float, default=None, help="Wall-clock limit in seconds")
    args = parser.parse_args()

    installations = find_olga_installations()
    if not installations:
        raise SystemExit(
            "No OLGA installation found. Set OLGA_HOME or OLGA_ENGINE and retry."
        )
    print("OLGA versions found:", ", ".join(i.version for i in installations))
    print("Licence environment:", license_environment() or "<none set>")

    try:
        runner = OlgaRunner(default_nthreads=args.nthreads)
    except OlgaNotFoundError as exc:
        raise SystemExit(str(exc)) from exc
    print("Using engine:", runner.installation.engine)

    case = args.case
    if args.endtime:
        case = write_variant(
            case,
            case.with_name(f"{case.stem}_variant{case.suffix}"),
            {"INTEGRATION": {"ENDTIME": args.endtime}},
        )
        print("Wrote variant:", case)

    # 1. Cheap input validation before spending a licence and CPU hours.
    check = runner.rule_check(case)
    if not check.succeeded:
        print(json.dumps(check.summary(), indent=2))
        print(check.stdout[-4000:])
        return check.returncode

    # 2. Full run.
    result = runner.run(case, timeout=args.timeout)
    print(json.dumps(result.summary(), indent=2))
    if not result.succeeded:
        print(result.stdout[-4000:])
        return result.returncode

    # 3. Post-process.
    if "tpl" in result.outputs:
        trend = read_tpl(result.outputs["tpl"])
        print(f"\nTrend: {len(trend.time)} samples, {len(trend.variables)} variables")
        for variable in trend.variables:
            series = trend.series(variable.name, variable.branch)
            print(f"  {variable.label():<60} final = {series[-1]:.6g} {variable.unit}")

    if "ppl" in result.outputs:
        profile = read_ppl(result.outputs["ppl"])
        print(f"\nProfile: {len(profile.times)} output times, {len(profile.variables)} variables")
        for branch in profile.branches:
            print(f"  branch {branch.name}: {branch.nsections} sections")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
