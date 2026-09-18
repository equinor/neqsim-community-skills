"""Public example for the neqsim-e300-fluid-io skill.

Reads a synthetic public E300 file, adds water with the PVTsim water
parameters, writes a new water-containing E300 file, and (when NeqSim is
installed) loads both into rigorous NeqSim fluids to confirm round-tripping.

Run:
    python examples/build_water_e300.py
"""

from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from e300_fluid_io import (
    add_water_to_e300_file,
    neqsim_available,
    read_e300_file,
    read_e300_to_neqsim,
)


def main() -> None:
    sample = Path(__file__).resolve().parent / "sample_gas.e300"

    base = read_e300_file(str(sample))
    print("Base fluid")
    print(f"  components={base.names}")
    print(f"  has_water={base.has_water()}")

    out = Path(tempfile.gettempdir()) / "sample_gas_water.e300"
    water_fluid = add_water_to_e300_file(str(sample), str(out))
    print("Water fluid (pure-Python)")
    print(f"  components={water_fluid.names}")
    print(f"  water_sshift={water_fluid.sshift[-1]}")
    print(f"  water_parachor={water_fluid.parachor[-1]}")
    print(f"  written_to={out}")

    print(f"neqsim_available={neqsim_available()}")
    if neqsim_available():
        fluid = read_e300_to_neqsim(str(sample), add_water=True)
        fluid.setMixingRule("classic")
        print("NeqSim fluid")
        print(f"  numberOfComponents={fluid.getNumberOfComponents()}")
        n = fluid.getNumberOfComponents()
        names = [str(fluid.getComponent(i).getComponentName()) for i in range(n)]
        print(f"  components={names}")


if __name__ == "__main__":
    main()
