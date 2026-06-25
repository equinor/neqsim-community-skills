from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gas_turbine_performance_screening import GasTurbinePerformanceModel


def main() -> None:
    model = GasTurbinePerformanceModel()
    result = model.evaluate(
        iso_base_power_kw=30000.0,
        iso_heat_rate_kj_kwh=9500.0,
        ambient_temperature_k=303.15,
        site_elevation_m=50.0,
        inlet_pressure_loss_mbar=10.0,
        exhaust_pressure_loss_mbar=10.0,
        required_shaft_power_kw=26000.0,
    )

    print("Gas turbine performance screening result")
    print(f"site_power_kw={result.site_power_kw}")
    print(f"ambient_derate_factor={result.ambient_derate_factor}")
    print(f"altitude_derate_factor={result.altitude_derate_factor}")
    print(f"pressure_loss_derate_factor={result.pressure_loss_derate_factor}")
    print(f"total_derate_factor={result.total_derate_factor}")
    print(f"site_heat_rate_kj_kwh={result.site_heat_rate_kj_kwh}")
    print(f"thermal_efficiency={result.thermal_efficiency}")
    print(f"fuel_heat_input_kw={result.fuel_heat_input_kw}")
    print(f"exhaust_mass_flow_kg_s={result.exhaust_mass_flow_kg_s}")
    print(f"exhaust_temperature_k={result.exhaust_temperature_k}")
    print(f"power_margin_ratio={result.power_margin_ratio}")
    print(f"power_warning={result.power_warning}")


if __name__ == "__main__":
    main()
