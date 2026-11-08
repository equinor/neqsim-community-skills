"""Run ONE fluid through a forward-only multi-stage separator train.

Liquid cascades HP -> MP -> LP -> stock tank, every gas stream leaves the system
(no recycle), the same layout PVTsim and ECL300 separator tests use.

Examples:
    python run_forward_separator.py fluid.e300
    python run_forward_separator.py fluid.e300 --feed-p 300 --feed-t 110 \
        --stages "70:60,20:50,2:40" --out result.json
    python run_forward_separator.py --composition comp.json --out result.json

comp.json: {"eos": "srk", "components": {"methane": 0.7, "ethane": 0.1, "n-heptane": 0.2}}
"""
import argparse
import json
import math
import sys

SM3_PER_KMOL = 23.6446  # ideal gas, 15 C and 1.01325 bara
STD_P_BARA = 1.01325
STD_T_C = 15.0
WATER_DENSITY_15C = 999.016


def load_jneqsim():
    """Return the jneqsim namespace from the pip package."""
    try:
        from neqsim import jneqsim
        return jneqsim
    except ImportError:
        sys.exit("The neqsim Python package is required (pip install neqsim).")


def build_fluid(jneqsim, args):
    """Create the feed fluid from an E300 file or a composition JSON."""
    if args.e300:
        fluid = jneqsim.thermo.util.readwrite.EclipseFluidReadWrite.read(args.e300)
    else:
        with open(args.composition) as f:
            spec = json.load(f)
        cls = {"srk": "SystemSrkEos", "pr": "SystemPrEos"}[spec.get("eos", "srk").lower()]
        fluid = getattr(jneqsim.thermo.system, cls)(273.15 + args.feed_t, args.feed_p)
        for name, z in spec["components"].items():
            fluid.addComponent(name, float(z))
        fluid.createDatabase(True)
        fluid.setMixingRule(2)
    fluid.setTemperature(args.feed_t + 273.15)
    fluid.setPressure(args.feed_p)
    return fluid


def parse_stages(text):
    """Parse 'P:T,P:T' (bara:degC) into a list of tuples."""
    stages = [tuple(float(x) for x in item.split(":")) for item in text.split(",")]
    if any(p <= STD_P_BARA for p, _ in stages):
        sys.exit("Stage pressures must be above standard pressure (1.01325 bara).")
    if any(a[0] <= b[0] for a, b in zip(stages, stages[1:])):
        sys.exit("Stage pressures must decrease along the train.")
    return stages


def run_train(jneqsim, fluid, stages, flow_kg_h):
    """Build and run the forward train; return feed stream, stage records, stock tank liquid."""
    eq = jneqsim.process.equipment
    ps = jneqsim.process.processmodel.ProcessSystem()
    feed = eq.stream.Stream("feed", fluid)
    feed.setFlowRate(flow_kg_h, "kg/hr")
    ps.add(feed)
    liquid = feed
    records = []
    for k, (p, t) in enumerate(stages + [(STD_P_BARA, STD_T_C)], start=1):
        name = "stage%d" % k if k <= len(stages) else "stock_tank"
        valve = eq.valve.ThrottlingValve("valve_" + name, liquid)
        valve.setOutletPressure(p)
        ps.add(valve)
        heater = eq.heatexchanger.Heater("heater_" + name, valve.getOutletStream())
        heater.setOutTemperature(t + 273.15)
        ps.add(heater)
        sep = eq.separator.Separator(name, heater.getOutletStream())
        ps.add(sep)
        records.append((name, p, t, sep.getGasOutStream(), sep.getLiquidOutStream()))
        liquid = sep.getLiquidOutStream()
    ps.run()
    return feed, records, liquid


def collect(feed, records, flow_kg_h):
    """Reduce the run to stage rows and bulk PVT-style numbers."""
    feed.getFluid().initProperties()
    stages, gas_total = [], 0.0
    gas_mass = 0.0
    for name, p, t, gas, liq in records:
        g_kg = gas.getFlowRate("kg/hr")
        g_sm3 = gas.getFlowRate("mole/sec") * 3.6 * SM3_PER_KMOL if g_kg > 0 else 0.0
        gas_total += g_sm3
        gas_mass += g_kg
        stages.append({
            "stage": name, "P_bara": p, "T_C": t,
            "gas_Sm3_h": g_sm3,
            "gas_MW_gmol": gas.getFluid().getMolarMass() * 1000.0 if g_kg > 0 else None,
            "liquid_kg_h": liq.getFlowRate("kg/hr"),
        })
    sto = records[-1][4]
    sto_kg = sto.getFlowRate("kg/hr")
    if sto_kg <= 0:
        raise RuntimeError("No stock tank liquid: fluid is gas at the first separator.")
    sto_rho = sto.getFluid().getDensity("kg/m3")
    sto_m3 = sto_kg / sto_rho
    rho_feed = feed.getFluid().getDensity("kg/m3")
    return {
        "GOR_Sm3_Sm3": gas_total / sto_m3,
        "Bo_m3_Sm3": (flow_kg_h / rho_feed) / sto_m3,
        "STO_Sm3_h": sto_m3,
        "STO_density_kgm3": sto_rho,
        "STO_API": 141.5 / (sto_rho / WATER_DENSITY_15C) - 131.5,
        "total_gas_Sm3_h": gas_total,
        "feed_density_kgm3": rho_feed,
        "feed_n_phases": int(feed.getFluid().getNumberOfPhases()),
        "mass_balance_rel_err": (sto_kg + gas_mass - flow_kg_h) / flow_kg_h,
        "stages": stages,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("e300", nargs="?", help="E300 fluid file")
    ap.add_argument("--composition", help="JSON with eos and component mole fractions")
    ap.add_argument("--feed-p", type=float, default=250.0, help="feed pressure, bara")
    ap.add_argument("--feed-t", type=float, default=100.0, help="feed temperature, degC")
    ap.add_argument("--stages", default="70:60,20:50,2:40", help="bara:degC per stage, comma separated")
    ap.add_argument("--flow", type=float, default=100000.0, help="feed rate, kg/hr")
    ap.add_argument("--out", help="write result JSON here")
    args = ap.parse_args()
    if bool(args.e300) == bool(args.composition):
        ap.error("give exactly one of an E300 file or --composition")

    jneqsim = load_jneqsim()
    stages = parse_stages(args.stages)
    fluid = build_fluid(jneqsim, args)
    feed, records, _ = run_train(jneqsim, fluid, stages, args.flow)
    result = collect(feed, records, args.flow)
    result["inputs"] = {"fluid": args.e300 or args.composition, "feed_P_bara": args.feed_p,
                        "feed_T_C": args.feed_t, "stages_bara_C": stages, "feed_kg_h": args.flow}
    result["warnings"] = []
    if result["feed_n_phases"] > 1:
        result["warnings"].append("Feed is two-phase at the given feed P/T; Bo and GOR are for the "
                                  "mixed stream, not a single-phase reservoir fluid.")
    if not math.isfinite(result["GOR_Sm3_Sm3"]):
        result["warnings"].append("GOR is not finite.")
    text = json.dumps(result, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text)
    print(text)


if __name__ == "__main__":
    main()
