from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gas_scrubber_sizing_screening import GasScrubberSizingModel


def main() -> None:
    model = GasScrubberSizingModel()
    result = model.evaluate(
        gas_mass_flow_kg_s=8.0,
        gas_density_kg_m3=45.0,
        liquid_density_kg_m3=700.0,
        k_factor_m_s=0.107,
        vessel_inside_diameter_m=1.2,
        mist_eliminator_k_factor=0.12,
        demister_present=True,
    )

    print("Gas scrubber sizing screening result")
    print(f"souders_brown_velocity_m_s={result.souders_brown_velocity_m_s}")
    print(f"gas_volumetric_flow_m3_s={result.gas_volumetric_flow_m3_s}")
    print(f"required_area_m2={result.required_area_m2}")
    print(f"required_diameter_m={result.required_diameter_m}")
    print(f"actual_velocity_m_s={result.actual_velocity_m_s}")
    print(f"velocity_utilisation={result.velocity_utilisation}")
    print(f"gas_load_factor={result.gas_load_factor}")
    print(f"demister_velocity_limit_m_s={result.demister_velocity_limit_m_s}")
    print(f"demister_utilisation={result.demister_utilisation}")
    print(f"sizing_warning={result.sizing_warning}")
    print(f"demister_warning={result.demister_warning}")


if __name__ == "__main__":
    main()
