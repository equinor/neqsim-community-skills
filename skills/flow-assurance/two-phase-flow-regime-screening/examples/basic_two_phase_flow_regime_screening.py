import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from two_phase_flow_regime_screening import TwoPhaseRegimeModel


def main() -> None:
    model = TwoPhaseRegimeModel()
    result = model.evaluate(
        pipe_inner_diameter=0.25,
        gas_mass_flow=3.0,
        liquid_mass_flow=12.0,
        gas_density=45.0,
        liquid_density=780.0,
    )

    print(f"superficial_gas_velocity_m_s    : {result.superficial_gas_velocity_m_s}")
    print(f"superficial_liquid_velocity_m_s : {result.superficial_liquid_velocity_m_s}")
    print(f"mixture_velocity_m_s            : {result.mixture_velocity_m_s}")
    print(f"flow_regime                     : {result.flow_regime}")
    print(f"slug_risk                       : {result.slug_risk}")
    print(f"regime_warning                  : {result.regime_warning}")
    print(f"neqsim_available                : {result.neqsim_available}")
    for line in result.assumptions:
        print(f"  - {line}")


if __name__ == "__main__":
    main()
