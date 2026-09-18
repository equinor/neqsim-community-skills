from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fired_heater_duty_screening import FiredHeaterDutyModel


def main() -> None:
    model = FiredHeaterDutyModel()
    result = model.evaluate(
        mass_flow=15.0,
        specific_heat=2.4,
        inlet_temperature=473.15,
        outlet_temperature=623.15,
        radiant_area=200.0,
    )

    print("Fired heater duty screening result")
    print(f"process_duty_kw={result.process_duty_kw}")
    print(f"fired_duty_kw={result.fired_duty_kw}")
    print(f"fuel_rate_kg_s={result.fuel_rate_kg_s}")
    print(f"average_radiant_flux_kw_m2={result.average_radiant_flux_kw_m2}")
    print(f"flux_ratio={result.flux_ratio}")
    print(f"fired_heater_warning={result.fired_heater_warning}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()
