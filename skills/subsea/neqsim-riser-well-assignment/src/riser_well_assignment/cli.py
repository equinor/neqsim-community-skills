"""Command line: ``python -m riser_well_assignment problem.json --pareto``."""

from __future__ import annotations

import argparse
import json
import sys

from .optimizer import check_solution, pareto_swaps, solve
from .schema import load_problem
from .synthetic import synthetic_problem


def _solution_dict(problem, sol):
    """Convert a solution to JSON-ready dictionaries."""
    ev = sol.evaluation
    return {
        "status": sol.status,
        "mip_gap": sol.mip_gap,
        "net_value": sol.objective,
        "revenue": ev.revenue if ev else None,
        "swap_cost": ev.swap_cost if ev else None,
        "sibling_cost": ev.sibling_cost if ev else None,
        "swaps": sol.n_swaps,
        "moves": sol.moves,
        "binding_limits": sol.binding_limits,
        "unproducible_wells": sol.unproducible_wells,
        "connections": sol.plan.connections if sol.plan else [],
        "lineups": sol.plan.lineups if sol.plan else [],
        "assignment": [{w: {"riser": r, "manifold": m, "rate_fraction": round(f, 4)} for w, (r, m, f) in per.items()}
                       for per in sol.assignment],
        "stream_totals": ev.stream_totals if ev else [],
        "check_violations": check_solution(problem, sol),
    }


def main(argv=None) -> int:
    """Run the optimizer from the command line."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("problem", nargs="?", help="problem JSON (omit with --synthetic)")
    ap.add_argument("--synthetic", action="store_true", help="use the built-in synthetic demo")
    ap.add_argument("--max-swaps", type=int, default=None)
    ap.add_argument("--lock-manifolds", action="store_true", help="keep every riser lined up as today")
    ap.add_argument("--pareto", action="store_true", help="value versus swap budget")
    ap.add_argument("--out", default=None, help="write result JSON here")
    args = ap.parse_args(argv)
    if args.synthetic:
        data = synthetic_problem()
    elif args.problem:
        with open(args.problem, encoding="utf-8") as fh:
            data = json.load(fh)
    else:
        ap.error("give a problem file or --synthetic")
    problem = load_problem(data)
    out = {"warnings": problem.warnings}
    lock = True if args.lock_manifolds else None
    out["optimal"] = _solution_dict(problem, solve(problem, args.max_swaps, lock))
    out["no_swap"] = _solution_dict(problem, solve(problem, 0, lock))
    if args.pareto:
        out["pareto"] = pareto_swaps(problem, lock_manifolds=lock)
    text = json.dumps(out, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
    sys.stdout.write("net value %.4g (no-swap %.4g), swaps %d\n" % (
        out["optimal"]["net_value"], out["no_swap"]["net_value"], out["optimal"]["swaps"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
