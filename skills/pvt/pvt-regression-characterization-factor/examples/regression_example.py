"""Example: regress a split factor against saturation pressure and STO density.

Run with:  python examples/regression_example.py
"""

from pvt_regression import RegressionTarget, regress_characterization_factor


def main() -> None:
    def forward(alpha):
        # Toy forward model; replace with a NeqSim characterization + PVT eval.
        return {
            "p_sat": 150.0 + 50.0 * (alpha - 1.0),
            "rho_STO": 800.0 + 25.0 * (alpha - 1.0),
        }

    targets = [
        RegressionTarget("p_sat", measured=170.0, weight=2.0),
        RegressionTarget("rho_STO", measured=810.0, weight=1.0),
    ]
    result = regress_characterization_factor(forward, targets, low=0.5, high=2.5)
    print(f"Fitted factor : {result.factor:.4f}")
    print(f"Objective     : {result.objective:.3e}")
    print("Predicted     :", {k: round(v, 2) for k, v in result.predicted.items()})
    print("Residuals     :", {k: round(v, 4) for k, v in result.residuals.items()})


if __name__ == "__main__":
    main()
