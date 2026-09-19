"""Example: calibrate a split factor and blend wells into a field fluid.

Run with:  python examples/reference_fluid_example.py
"""

from reference_fluid import blend_compositions, generate_fluid_cases, match_split_factor


def main() -> None:
    measured_psat = 170.0

    def forward_psat(alpha):
        # Toy forward model; replace with a NeqSim saturation-pressure call.
        return 150.0 + 40.0 * (alpha - 1.0)

    def objective(alpha):
        rel = (forward_psat(alpha) - measured_psat) / measured_psat
        return rel * rel

    match = match_split_factor(objective, low=0.5, high=2.5)
    print(f"Calibrated split factor: {match.factor:.4f} (objective {match.objective:.2e})")

    def build(alpha):
        heavy = 0.05 / alpha
        return {"methane": 1.0 - heavy, "C7plus": heavy}

    cases = generate_fluid_cases([0.8, match.factor, 1.2], build)
    print("Generated cases:", [{k: round(v, 4) for k, v in c.items()} for c in cases])

    field = blend_compositions(
        [
            (3200.0, {"methane": 0.90, "ethane": 0.10}),
            (1500.0, {"methane": 0.70, "ethane": 0.30}),
        ]
    )
    print("Field composition:", {k: round(v, 4) for k, v in field.composition.items()})
    print("Allocation weights:", tuple(round(w, 3) for w in field.weights))


if __name__ == "__main__":
    main()
