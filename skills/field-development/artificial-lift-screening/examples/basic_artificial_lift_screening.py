from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from artificial_lift_screening import ArtificialLiftModel


def main() -> None:
    model = ArtificialLiftModel()
    result = model.evaluate(
        reservoir_pressure_bar=250.0,
        bottomhole_flowing_pressure_bar=200.0,
        productivity_index_sm3_d_bar=8.0,
        target_rate_sm3_d=800.0,
        water_cut=0.2,
        gas_lift_available=True,
        esp_max_head_m=2500.0,
        well_depth_m=2200.0,
    )

    print("Natural rate (Sm3/d):", result.natural_rate_sm3_d)
    print("Required Pwf (bar):", result.required_pwf_bar)
    print("Required pressure reduction (bar):", result.required_pressure_reduction_bar)
    print("ESP required head (m):", result.esp_required_head_m)
    print("Gas lift feasible:", result.gas_lift_feasible)
    print("ESP feasible:", result.esp_feasible)
    print("Recommended method:", result.recommended_method)
    print("NeqSim available:", result.neqsim_available)
    print("Assumptions:")
    for line in result.assumptions:
        print("  -", line)


if __name__ == "__main__":
    main()
