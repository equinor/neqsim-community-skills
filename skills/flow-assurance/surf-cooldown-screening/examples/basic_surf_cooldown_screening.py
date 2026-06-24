from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from surf_cooldown_screening import SurfCooldownModel


def main() -> None:
    model = SurfCooldownModel(hydrate_margin=3.0, required_no_touch_time=8.0)

    tau = SurfCooldownModel.time_constant_from_lumped_mass(
        fluid_density=180.0,
        specific_heat=2600.0,
        internal_diameter=0.254,
        overall_u_value=2.5,
    )

    result = model.evaluate(
        initial_temperature=65.0,
        seabed_temperature=4.0,
        hydrate_equilibrium_temperature=20.0,
        time_constant_hours=tau,
    )

    print("SURF cooldown screening result")
    print(f"time_constant_hours={round(tau, 2)}")
    print(f"no_touch_time_hours={result.no_touch_time_hours}")
    print(f"target_temperature_c={result.target_temperature_c}")
    print(f"verdict={result.verdict}")
    print(f"neqsim_available={result.neqsim_available}")


if __name__ == "__main__":
    main()
