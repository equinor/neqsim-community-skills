import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pump_hydraulics_screening import PumpHydraulicsModel


def main() -> None:
    model = PumpHydraulicsModel()
    result = model.evaluate(
        flow_rate=120.0,
        head=95.0,
        density=820.0,
        efficiency=0.74,
        suction_pressure=4.0,
        vapor_pressure=1.5,
        static_suction_head=3.0,
        friction_loss=0.8,
        npsh_required=3.5,
        bep_flow_rate=130.0,
    )

    print(f"hydraulic_power_kw : {result.hydraulic_power_kw}")
    print(f"shaft_power_kw     : {result.shaft_power_kw}")
    print(f"npsh_available_m   : {result.npsh_available_m}")
    print(f"npsh_margin_m      : {result.npsh_margin_m}")
    print(f"bep_ratio          : {result.bep_ratio}")
    print(f"pump_warning       : {result.pump_warning}")
    print(f"neqsim_available   : {result.neqsim_available}")
    for line in result.assumptions:
        print(f"  - {line}")


if __name__ == "__main__":
    main()
