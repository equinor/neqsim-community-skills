"""Minimal example for the design-basis screening skill."""

from design_basis_screening import DesignBasisModel


def main() -> None:
    model = DesignBasisModel()
    result = model.evaluate(
        operating_flow=100.0,
        design_flow=120.0,
        operating_pressure_bara=60.0,
        design_pressure_bara=70.0,
        operating_temperature_c=40.0,
        design_temperature_c=60.0,
        standards=("ASME VIII Div.1", "NORSOK P-001"),
    )

    print(f"Flow margin:          {result.flow_margin:.2f} [{result.flow_flag}]")
    print(f"Pressure margin:      {result.pressure_margin:.2f} [{result.pressure_flag}]")
    print(f"Temperature margin:   {result.temperature_margin_c:.1f} C [{result.temperature_flag}]")
    print(f"Standards:            {', '.join(result.standards) or 'none'}")
    print(f"Design warning:       {result.design_warning}")
    if result.flags:
        print("Flags:")
        for flag in result.flags:
            print(f"  - {flag}")


if __name__ == "__main__":
    main()
