"""Score NeqSim (SRK) against ThermoML points.

Run offline with the synthetic fixture:  python examples/compare_with_neqsim.py
Run on a real article (anonymous):         python examples/compare_with_neqsim.py 10.1021/je3001427 density
ThermoML names must map to NeqSim component names; edit NAME_MAP for compounds NeqSim names differently.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from neqsim import jneqsim  # noqa: E402

from thermoml_experimental_data import ThermomlClient, compare_points, parse_thermoml  # noqa: E402

NAME_MAP = {"octan-1-ol": "1-octanol"}


def srk_density(point) -> float:
    """Mass density (kg/m3) of the point's composition at its T and P from an SRK TP flash."""
    if point.temperature_k is None or point.pressure_bara is None or not point.mole_fractions:
        raise ValueError("point lacks T, P or composition")
    fluid = jneqsim.thermo.system.SystemSrkEos(point.temperature_k, point.pressure_bara)
    for name, x in point.mole_fractions.items():
        fluid.addComponent(NAME_MAP.get(name, name), x)
    fluid.setMixingRule("classic")
    jneqsim.thermodynamicoperations.ThermodynamicOperations(fluid).TPflash()
    fluid.initProperties()
    return fluid.getDensity("kg/m3")


def main() -> None:
    if len(sys.argv) > 1:
        report = ThermomlClient().get_report(sys.argv[1])
        prop = sys.argv[2] if len(sys.argv) > 2 else "density"
    else:
        from test_thermoml import FIXTURE

        report, prop = parse_thermoml(FIXTURE), "density"
    summary = compare_points(report.points(property_contains=prop), srk_density, tolerance_pct=2.0)
    print(f"{report.doi}: {summary.status} n={summary.n_points} skipped={summary.n_skipped} "
          f"AAD={summary.aad_pct} % bias={summary.bias_pct} %")


if __name__ == "__main__":
    main()
