---
name: neqsim-pvt-regression-characterization-factor
version: "0.1.0"
description: "Public weighted multi-target regression of a split/characterization factor against measured PVT and separator data (saturation pressure, GOR, stock-tank-oil density, formation volume factor). USE WHEN: a task must calibrate one heavy-end characterization factor so a fluid model reproduces several measured PVT/separator quantities at once, with per-target weights and residual reporting, before rigorous NeqSim EOS regression."
last_verified: "2026-07-14"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# PVT Regression of a Characterization Factor

Use this skill to **regress a single split / characterization factor against
several measured PVT or separator targets at once**, with per-target weights and
explicit residual reporting. It mirrors FluidMagic's regression (which fits
EOS/characterization parameters to measured PVT experiment values with weights)
and NeqSim's characterization plus PVT-simulation workflow.

The forward model is **injected** by the caller, so this skill has no dependency
on a particular EOS. In practice it wraps a NeqSim characterization + flash /
PVT-simulation evaluation, or the community
`pseudocomponent-split-characterization` and `reference-fluid-synthetic-generation`
skills.

## When to Use

- When one heavy-end factor must reproduce **multiple** measured quantities
  (for example saturation pressure and stock-tank-oil density) simultaneously.
- When targets have **different importance** and need weighting.
- When you must report **per-target residuals** to judge whether the match is
  acceptable.
- When a full EOS regression is not warranted but a calibrated split factor is.

## Inputs

- `forward_model(factor) -> {target_name: predicted_value}`: caller-supplied.
- `targets`: a list of `RegressionTarget(name, measured, weight)`.
- `low`, `high`: bounds of the factor search interval.
- `tol`, `max_iter`: search controls.

## Outputs

- `RegressionResult`: fitted factor, objective, per-target residuals and
  predictions, iterations, and convergence flag.
- `weighted_ssr(predicted, targets)`: the weighted sum of squared relative
  residuals, usable as a standalone objective.

## Engineering Method

Each residual is normalized: `(predicted - measured) / measured`, so quantities
of different magnitude and units contribute comparably. The objective is the
weighted sum of squared relative residuals. The factor is fitted by a robust
golden-section 1-D search over `[low, high]` — no gradients, suitable for the
noisy forward models produced by flash and PVT calculations.

Typical targets and units:

| Target | Symbol | Typical unit |
| --- | --- | --- |
| Saturation pressure | `p_sat` | bara |
| Gas-oil ratio | `GOR` | Sm³/Sm³ |
| Stock-tank-oil density | `rho_STO` | kg/m³ |
| Oil formation volume factor | `Bo` | m³/Sm³ |

## Python Usage Pattern

```python
from pvt_regression import RegressionTarget, regress_characterization_factor

def forward(alpha):
    # Replace with a NeqSim characterization + PVT evaluation for this factor.
    fluid = build_fluid_with_split_factor(alpha)
    return {
        "p_sat": saturation_pressure_bara(fluid),
        "rho_STO": stock_tank_oil_density(fluid),
    }

targets = [
    RegressionTarget("p_sat", measured=248.0, weight=2.0),
    RegressionTarget("rho_STO", measured=832.0, weight=1.0),
]
result = regress_characterization_factor(forward, targets, low=0.6, high=3.0)
print(result.factor, result.residuals)
```

## Related NeqSim Functionality

- `neqsim.thermo.characterization.PlusFractionModel` / `PlusCharacterize` — the
  factor (`alpha`/`eta`) regressed here.
- `SystemInterface` + `ThermodynamicOperations` — saturation pressure
  (`bubblePointPressureFlash`), GOR and density via separator/flash calculations.
- For a full EOS parameter regression (kij, Tc, Pc, omega, volume shift), use the
  rigorous NeqSim PVT-simulation and tuning classes rather than this
  single-factor screening.

Pair this skill with `neqsim-pseudocomponent-split-characterization` (the split)
and `neqsim-reference-fluid-synthetic-generation` (generate the fluids).

## Validation Checklist

- Each measured target has a stated value, unit, source, and weight.
- The forward model returns every target name the regression expects.
- The returned `converged` flag is checked and per-target residuals are within a
  documented acceptable-match threshold.
- The fitted factor lies inside (not on) the search bounds; widen bounds if it
  sits at an endpoint.
- Assumptions and limitations are recorded and qualified PVT review is planned.

## Common Mistakes

- A forward model that omits a target name (raises a missing-prediction error).
- A measured value of zero (relative residual is undefined; raises).
- Passing `low >= high` (raises).
- Interpreting a single-factor fit as a full EOS regression.

## Limitations

- Screening-level and single-factor; it does not tune the full EOS.
- The caller's forward model determines physical accuracy.
- Acceptable-match criteria (residual thresholds) must be set by the engineer.
- Results require qualified PVT review before design or operational use.

## References

- Whitson, C.H., Brulé, M.R. (2000). *Phase Behavior*, SPE Monograph 20.
- Pedersen, K.S. et al. (2015). *Phase Behavior of Petroleum Reservoir Fluids*, 2nd ed.
- NeqSim: https://github.com/equinor/neqsim
