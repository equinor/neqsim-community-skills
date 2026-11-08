"""Fit ONE set of stage pressures and temperatures to reservoir-simulation oil and gas rates.

A reservoir simulator replaces the surface process by a pseudo process: the same
stage P/T is applied to every fluid it produces. This script finds the single set of
(P_i, T_i) that gives the best overall match of produced oil and gas rate (hence GOR)
over all fluids. Bo, densities etc. are not used.

Manifest CSV (one row per fluid), columns:
    fluid        path to an E300 file (relative to the manifest)
    oil_Sm3_h    target stock-tank oil rate
    gas_Sm3_h    target total gas rate (all stages and tank, 15 C / 1.01325 bara)
    feed_kmol_h  optional, wellstream molar rate for that rate pair (default 1000)
    feed_P_bara, feed_T_C   optional per-row feed conditions (default --feed-p/--feed-t)
    weight       optional, row weight (default 1)
    formation    optional label; all formations share ONE P/T set, the label only splits the error report

Residual per fluid: ln(model/target) for oil and for gas, so errors are relative and
GOR (= gas/oil) is matched by construction.

Example:
    python fit_separator_pt.py manifest.csv --stages 3 --x0 "70:60,20:50,2:40" --out fit.json
"""
import argparse
import csv
import json
import math
import os
import sys

import numpy as np
from scipy.optimize import least_squares

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_forward_separator as rfs  # noqa: E402

P_FLOOR = 1.1  # lowest allowed last-stage pressure, bara
PENALTY_RESIDUAL = 5.0  # ln-error assigned to a case that cannot be evaluated


def load_manifest(path, default_p, default_t):
    """Read the manifest into a list of dict rows."""
    base = os.path.dirname(os.path.abspath(path))
    rows = []
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            fp = r["fluid"]
            rows.append({
                "fluid": fp if os.path.isabs(fp) else os.path.join(base, fp),
                "oil": float(r["oil_Sm3_h"]), "gas": float(r["gas_Sm3_h"]),
                "kmol_h": float(r.get("feed_kmol_h") or 1000.0),
                "p": float(r.get("feed_P_bara") or default_p),
                "t": float(r.get("feed_T_C") or default_t),
                "w": float(r.get("weight") or 1.0),
                "formation": (r.get("formation") or "all").strip(),
            })
    return rows


def oil_gas_rates(jneqsim, base, stages, kmol_h, feed_p, feed_t):
    """Run the forward train; return (oil_Sm3_h, gas_Sm3_h) or None if no stock-tank oil."""
    fluid = base.clone()
    fluid.setTemperature(feed_t + 273.15)
    fluid.setPressure(feed_p)
    feed, records, _ = rfs.run_train(jneqsim, fluid, stages, kmol_h * 1000.0 / 3600.0, "mole/sec")
    sto = records[-1][4]
    sto_kg = sto.getFlowRate("kg/hr")
    if not sto_kg > 0:
        return None
    oil = sto_kg / sto.getFluid().getDensity("kg/m3")
    gas = 0.0
    for _, _, _, g, _ in records:
        if g.getFlowRate("kg/hr") > 0:
            gas += g.getFlowRate("mole/sec") * 3.6 * rfs.SM3_PER_KMOL
    return oil, gas


def decode(x, n):
    """x = [P_last, d_(n-1)..d_1, T_1..T_n] -> list of (P, T), pressure falling by construction."""
    p = [0.0] * n
    p[n - 1] = x[0]
    for k in range(n - 2, -1, -1):
        p[k] = p[k + 1] * math.exp(x[1 + (n - 2 - k)])
    return [(p[k], x[n + k]) for k in range(n)]


def encode(stages):
    """Inverse of decode."""
    n = len(stages)
    p = [s[0] for s in stages]
    d = [math.log(p[k] / p[k + 1]) for k in range(n - 2, -1, -1)]
    return np.array([p[-1]] + d + [s[1] for s in stages])


def make_bounds(n, p_max, t_min, t_max):
    """Bounds for the encoded parameters."""
    lo = [P_FLOOR] + [0.15] * (n - 1) + [t_min] * n
    hi = [p_max] + [4.0] * (n - 1) + [t_max] * n
    return np.array(lo), np.array(hi)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("manifest")
    ap.add_argument("--x0", default="70:60,20:50,2:40", help="start stages bara:degC (sets stage count)")
    ap.add_argument("--feed-p", type=float, default=250.0)
    ap.add_argument("--feed-t", type=float, default=100.0)
    ap.add_argument("--p-max", type=float, default=150.0, help="upper bound on first-stage pressure, bara")
    ap.add_argument("--t-min", type=float, default=10.0)
    ap.add_argument("--t-max", type=float, default=150.0)
    ap.add_argument("--starts", type=int, default=2, help="start points: x0 plus jittered ones")
    ap.add_argument("--prior-weight", type=float, default=0.02,
                    help="weak pull toward --x0 (ln P and T/50 units) that picks one solution along a flat valley;\n"
                         "0 = pure data fit (P/T then usually not unique)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--robust", action="store_true", help="soft-L1 loss against outlier fluids")
    ap.add_argument("--out", default="fit_result.json")
    args = ap.parse_args()

    jneqsim = rfs.load_jneqsim()
    rows = load_manifest(args.manifest, args.feed_p, args.feed_t)
    cache = {}
    for r in rows:
        if r["fluid"] not in cache:
            cache[r["fluid"]] = jneqsim.thermo.util.readwrite.EclipseFluidReadWrite.read(r["fluid"])
    stages0 = rfs.parse_stages(args.x0)
    n = len(stages0)
    lo, hi = make_bounds(n, args.p_max, args.t_min, args.t_max)
    sqrt_w = np.sqrt([r["w"] for r in rows])
    n_eval = [0]

    def model_all(x):
        stages = decode(x, n)
        out = []
        for r in rows:
            try:
                out.append(oil_gas_rates(jneqsim, cache[r["fluid"]], stages, r["kmol_h"], r["p"], r["t"]))
            except Exception:
                out.append(None)
        n_eval[0] += 1
        return out

    def residuals(x):
        res = []
        for r, m, sw in zip(rows, model_all(x), sqrt_w):
            if m is None or not (m[0] > 0 and m[1] > 0):
                res += [PENALTY_RESIDUAL * sw, PENALTY_RESIDUAL * sw]
            else:
                res += [sw * math.log(m[0] / r["oil"]), sw * math.log(m[1] / r["gas"])]
        st = decode(x, n)
        res.append(10.0 * max(0.0, math.log(st[0][0] / args.p_max)))
        for (p, t), (p0, t0) in zip(st, stages0):
            res += [args.prior_weight * math.log(p / p0), args.prior_weight * (t - t0) / 50.0]
        return np.array(res)

    rng = np.random.default_rng(args.seed)
    starts = [np.clip(encode(stages0), lo, hi)]
    for _ in range(max(0, args.starts - 1)):
        jitter = np.concatenate(([0.0], 0.3 * rng.standard_normal(n - 1), 15.0 * rng.standard_normal(n)))
        starts.append(np.clip(encode(stages0) + jitter, lo, hi))
    runs = []
    for i, x_start in enumerate(starts):
        sol = least_squares(residuals, x_start, bounds=(lo, hi), diff_step=1e-3, x_scale="jac",
                            loss="soft_l1" if args.robust else "linear", max_nfev=40)
        runs.append(sol)
        print("start %d: cost %.5g, stages %s" % (i, sol.cost, [(round(float(p), 2), round(float(t), 1))
                                                              for p, t in decode(sol.x, n)]))
    best = min(runs, key=lambda s: s.cost)
    stages = decode(best.x, n)

    final = model_all(best.x)
    per_fluid, e_oil, e_gor = [], [], []
    for r, m in zip(rows, final):
        row = {"fluid": os.path.basename(r["fluid"]), "formation": r["formation"],
               "oil_target": r["oil"], "gas_target": r["gas"],
               "GOR_target": r["gas"] / r["oil"]}
        if m:
            row.update({"oil_model": m[0], "gas_model": m[1], "GOR_model": m[1] / m[0],
                        "oil_err_pct": 100 * (m[0] / r["oil"] - 1), "gas_err_pct": 100 * (m[1] / r["gas"] - 1),
                        "GOR_err_pct": 100 * ((m[1] / m[0]) / (r["gas"] / r["oil"]) - 1)})
            e_oil.append(row["oil_err_pct"])
            e_gor.append(row["GOR_err_pct"])
        per_fluid.append(row)

    jac = best.jac
    sv = np.linalg.svd(jac, compute_uv=False)
    cond = float(sv[0] / sv[-1]) if sv[-1] > 0 else float("inf")
    dof = max(1, len(best.fun) - len(best.x))
    s2 = float(np.sum(best.fun ** 2) / dof)
    names = ["P_%d" % (n) ] + ["ln(P_%d/P_%d)" % (k, k + 1) for k in range(n - 1, 0, -1)] + \
            ["T_%d" % (k + 1) for k in range(n)]
    try:
        cov = np.linalg.inv(jac.T @ jac) * s2
        se = np.sqrt(np.diag(cov))
    except np.linalg.LinAlgError:
        se = np.full(len(best.x), float("nan"))
    at_bound = [names[i] for i in range(len(best.x))
                if abs(best.x[i] - lo[i]) < 1e-6 * (1 + abs(lo[i])) or abs(best.x[i] - hi[i]) < 1e-6 * (1 + abs(hi[i]))]
    spread = [[(round(p, 3), round(t, 2)) for p, t in decode(s.x, n)] for s in runs]
    warnings = []
    if at_bound:
        warnings.append("Parameters at a bound: %s. Widen the bounds or the match is constrained." % at_bound)
    if cond > 1e6:
        warnings.append("Jacobian condition number %.2g: some P/T combinations are weakly determined "
                        "by these fluids; add fluids with different volatility or fix the weak stage." % cond)
    costs = sorted(s.cost for s in runs)
    if len(runs) > 1 and costs[-1] - costs[0] > 0.02 * (costs[0] + 1e-9):
        warnings.append("Starts ended at different minima; the best one is reported. Increase --starts.")
    if cond > 1e6 or float(np.nanmax(se / np.maximum(np.abs(best.x), 1e-9))) > 1.0:
        warnings.append("Large parameter uncertainty: the oil and gas rates alone do not pin down every P/T "
                        "(std_error in the parameter table). The reported set is the one closest to --x0 "
                        "among equally good fits; treat poorly determined stages as free design choices.")
    by_formation = {}
    for row in per_fluid:
        if "GOR_err_pct" in row:
            by_formation.setdefault(row["formation"], []).append(row)
    formation_report = {
        k: {"n": len(v),
            "oil_err_pct_mean": float(np.mean([x["oil_err_pct"] for x in v])),
            "GOR_err_pct_mean": float(np.mean([x["GOR_err_pct"] for x in v])),
            "GOR_err_pct_mean_abs": float(np.mean([abs(x["GOR_err_pct"]) for x in v]))}
        for k, v in by_formation.items()}
    if len(formation_report) > 1:
        bias = max(abs(v["GOR_err_pct_mean"]) for v in formation_report.values())
        if bias > 2.0 * max(0.5, float(np.mean(np.abs(e_gor)))):
            warnings.append("A formation is biased by %.1f %% in GOR: one P/T set does not fit all formations "
                            "equally well (see formation_report)." % bias)
    result = {
        "stages_bara_degC": [{"stage": k + 1, "P_bara": p, "T_C": t} for k, (p, t) in enumerate(stages)],
        "stock_tank": {"P_bara": rfs.STD_P_BARA, "T_C": rfs.STD_T_C},
        "n_fluids": len(rows),
        "fit_quality": {
            "rms_ln_error": float(math.sqrt(np.mean(best.fun ** 2))),
            "oil_err_pct_mean_abs": float(np.mean(np.abs(e_oil))) if e_oil else None,
            "GOR_err_pct_mean_abs": float(np.mean(np.abs(e_gor))) if e_gor else None,
            "GOR_err_pct_max_abs": float(np.max(np.abs(e_gor))) if e_gor else None,
        },
        "parameters": [{"name": nm, "value": float(v), "std_error": float(s)} for nm, v, s in zip(names, best.x, se)],
        "jacobian_condition": cond,
        "start_solutions": spread,
        "start_costs": [float(s.cost) for s in runs],
        "model_evaluations": n_eval[0],
        "per_fluid": per_fluid,
        "formation_report": formation_report,
        "warnings": warnings,
    }
    with open(args.out, "w") as f:
        json.dump(result, f, indent=2)
    csv_path = os.path.splitext(args.out)[0] + "_per_fluid.csv"
    with open(csv_path, "w", newline="") as f:
        fields = list(per_fluid[0])
        for r in per_fluid:
            fields += [k for k in r if k not in fields]
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(per_fluid)
    print(json.dumps({k: result[k] for k in ("stages_bara_degC", "fit_quality", "jacobian_condition", "warnings")}, indent=2))
    print("wrote", args.out, "and", csv_path)


if __name__ == "__main__":
    main()
