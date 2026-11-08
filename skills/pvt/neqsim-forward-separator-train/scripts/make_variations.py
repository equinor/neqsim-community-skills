"""Make Latin-hypercube variations of a base E300 fluid and a manifest for fit_separator_pt.py.

C1-C6 components are varied individually, the C7+ amount and a tilt of the C7+ distribution
(heavier or lighter pseudo-components) are varied too, all within +-spread. Pseudo-component
EOS parameters from the E300 file are kept, so MW and SG shift consistently.

Optional synthetic targets (for testing the regression): --truth-stages runs every fluid through
a known train and writes its oil/gas rates, optionally with relative noise.

Example:
    python make_variations.py base.e300 --n 30 --outdir variations
    python make_variations.py base.e300 --n 30 --outdir test --truth-stages "60:55,15:45,1.8:35" --noise 0.02
"""
import argparse
import csv
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fit_separator_pt as fit  # noqa: E402
import run_forward_separator as rfs  # noqa: E402


def lhs(n, d, rng):
    """Latin hypercube sample in [0, 1]^d."""
    u = (rng.random((n, d)) + np.arange(n)[:, None]) / n
    for j in range(d):
        rng.shuffle(u[:, j])
    return u


def classify(fluid):
    """Return (light, heavy) component index lists; non-hydrocarbons are held fixed."""
    light, heavy = [], []
    for i in range(fluid.getNumberOfComponents()):
        c = fluid.getComponent(i)
        if c.isIsTBPfraction() or c.isIsPlusFraction():
            heavy.append(i)
        elif c.isHydrocarbon():
            (light if c.getMolarMass() <= 0.0865 else heavy).append(i)
    return light, heavy


def compositions(fluid, n, spread, rng):
    """Return an (n, ncomp) array of normalised mole fractions."""
    nc = fluid.getNumberOfComponents()
    z0 = np.array([fluid.getComponent(i).getz() for i in range(nc)])
    mw = np.array([fluid.getComponent(i).getMolarMass() for i in range(nc)])
    light, heavy = classify(fluid)
    u = lhs(n, len(light) + 2, rng) * 2.0 - 1.0
    out = []
    for k in range(n):
        z = z0.copy()
        for j, i in enumerate(light):
            z[i] = z0[i] * (1.0 + spread * u[k, j])
        if heavy:
            amount = 1.0 + spread * u[k, len(light)]
            tilt = u[k, len(light) + 1]
            rank = np.empty(len(heavy))
            rank[np.argsort(mw[heavy])] = np.linspace(-1.0, 1.0, len(heavy))
            zh = z0[heavy] * np.maximum(1.0 + spread * tilt * rank, 1e-6)
            z[heavy] = zh * (z0[heavy].sum() * amount / zh.sum())
        out.append(z / z.sum())
    return np.array(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("e300")
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--spread", type=float, default=0.20)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--outdir", default="variations")
    ap.add_argument("--feed-p", type=float, default=250.0)
    ap.add_argument("--feed-t", type=float, default=100.0)
    ap.add_argument("--kmol-h", type=float, default=1000.0)
    ap.add_argument("--truth-stages", help="bara:degC list; fills oil/gas targets from this train")
    ap.add_argument("--noise", type=float, default=0.0, help="relative gaussian noise on targets")
    args = ap.parse_args()

    jneqsim = rfs.load_jneqsim()
    base = jneqsim.thermo.util.readwrite.EclipseFluidReadWrite.read(args.e300)
    rng = np.random.default_rng(args.seed)
    comps = compositions(base, args.n, args.spread, rng)
    os.makedirs(args.outdir, exist_ok=True)
    truth = rfs.parse_stages(args.truth_stages) if args.truth_stages else None
    rows = []
    for k, z in enumerate(comps, start=1):
        fl = base.clone()
        fl.setMolarComposition(z.tolist())
        name = "fluid_%02d.e300" % k
        jneqsim.thermo.util.readwrite.EclipseFluidReadWrite.write(fl, os.path.join(args.outdir, name))
        row = {"fluid": name, "oil_Sm3_h": "", "gas_Sm3_h": "", "feed_kmol_h": args.kmol_h}
        if truth:
            res = fit.oil_gas_rates(jneqsim, fl, truth, args.kmol_h, args.feed_p, args.feed_t)
            if res is None:
                continue
            row["oil_Sm3_h"] = res[0] * (1 + args.noise * rng.standard_normal())
            row["gas_Sm3_h"] = res[1] * (1 + args.noise * rng.standard_normal())
        rows.append(row)
    path = os.path.join(args.outdir, "manifest.csv")
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["fluid", "oil_Sm3_h", "gas_Sm3_h", "feed_kmol_h"])
        w.writeheader()
        w.writerows(rows)
    print("wrote %d E300 files and %s" % (len(rows), path))


if __name__ == "__main__":
    main()
