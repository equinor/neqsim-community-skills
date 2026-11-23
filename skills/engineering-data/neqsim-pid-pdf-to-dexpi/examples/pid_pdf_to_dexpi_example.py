"""Runs a vector-PDF P&ID through extraction, DEXPI, NeqSim simulation and P&ID regeneration.

Usage: python pid_pdf_to_dexpi_example.py SHEET.pdf OUT_DIR [--jar NEQSIM_JAR] [--flow KG_PER_H]
The fluid below is an illustrative gas-oil-water mixture; replace it with the real composition.
"""
import argparse
import json

from pid_pdf_to_dexpi.pipeline import run_pipeline

FLUID = {"eos": "srk", "mixingRule": "classic", "multiPhaseCheck": True, "components": [
    {"name": "nitrogen", "moles": 0.005}, {"name": "CO2", "moles": 0.015}, {"name": "methane", "moles": 0.40},
    {"name": "ethane", "moles": 0.05}, {"name": "propane", "moles": 0.03}, {"name": "n-butane", "moles": 0.02},
    {"name": "n-hexane", "moles": 0.02},
    {"name": "C10", "moles": 0.20, "molarMass": 0.15, "density": 0.79},
    {"name": "C20", "moles": 0.10, "molarMass": 0.30, "density": 0.85},
    {"name": "water", "moles": 0.16}]}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    parser.add_argument("out")
    parser.add_argument("--jar")
    parser.add_argument("--flow", type=float, default=100000.0)
    args = parser.parse_args()
    summary = run_pipeline(args.pdf, args.out, FLUID, feed_flow=args.flow, feed_flow_unit="kg/hr", jar=args.jar)
    print(json.dumps({"passed": summary["passed"], "checks": summary["checks"]}, indent=1))
