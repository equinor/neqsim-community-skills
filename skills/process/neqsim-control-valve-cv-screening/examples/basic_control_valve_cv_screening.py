import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from control_valve_cv_screening import ControlValveCvModel


def main() -> None:
    model = ControlValveCvModel()

    liquid = model.evaluate(
        service="liquid",
        inlet_pressure=10.0,
        pressure_drop=2.0,
        flow_rate=50.0,
        specific_gravity=0.85,
        vapor_pressure=1.0,
        critical_pressure=220.0,
        rated_cv=60.0,
    )
    print("Liquid service")
    print(f"  required_cv     : {liquid.required_cv}")
    print(f"  choked          : {liquid.choked}")
    print(f"  cv_margin_ratio : {liquid.cv_margin_ratio}")
    print(f"  valve_warning   : {liquid.valve_warning}")

    gas = model.evaluate(
        service="gas",
        inlet_pressure=50.0,
        pressure_drop=12.0,
        mass_flow=5000.0,
        inlet_density=40.0,
        specific_heat_ratio=1.3,
    )
    print("Gas service")
    print(f"  required_cv     : {gas.required_cv}")
    print(f"  choked          : {gas.choked}")
    print(f"  choke_limit (x) : {gas.choke_limit}")
    print(f"  valve_warning   : {gas.valve_warning}")


if __name__ == "__main__":
    main()
