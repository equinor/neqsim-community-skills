import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from multiphase_flow_slug_screening import SlugScreeningModel


def main() -> None:
    model = SlugScreeningModel()
    result = model.evaluate(
        superficial_gas_velocity=4.0,
        superficial_liquid_velocity=1.0,
        pipe_internal_diameter=0.3,
        slug_length_to_diameter=30.0,
        liquid_holdup_in_slug=0.8,
        surge_factor=1.2,
        available_slug_catcher_volume=1.0,
    )

    print("mixture_velocity_m_per_s:", result.mixture_velocity_m_per_s)
    print("froude_number:", result.froude_number)
    print("flow_regime_indicator:", result.flow_regime_indicator)
    print("estimated_slug_volume_m3:", result.estimated_slug_volume_m3)
    print(
        "recommended_slug_catcher_volume_m3:",
        result.recommended_slug_catcher_volume_m3,
    )
    print("capacity_ratio:", result.capacity_ratio)
    print("slug_warning:", result.slug_warning)
    for assumption in result.assumptions:
        print("-", assumption)


if __name__ == "__main__":
    main()
