---
name: neqsim-compressor-validation
version: "0.1.0"
description: "Compressor performance checks: polytropic head from suction/discharge conditions, vendor-curve head/efficiency lookup with fan-law speed scaling, chart tuning multipliers, and drivetrain shaft power. USE WHEN: a task needs to compare a centrifugal compressor operating point against a performance curve and estimate shaft power."
last_verified: "2026-06-05"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Compressor Validation

Use this skill to evaluate a centrifugal compressor operating point: compute the
polytropic head implied by measured suction/discharge conditions, look up the expected
head and efficiency from a vendor performance curve (with fan-law scaling between speed
lines), apply chart tuning multipliers, and estimate gas and shaft power through a
simple drivetrain model.

## When to Use

- When you have suction/discharge pressure and temperature and want the polytropic head.
- When you have speed-line performance data (flow, head, efficiency) and want the
  expected head/efficiency at an operating flow and speed.
- When a curve must be tuned to match observed behaviour with multiplicative factors.
- When you need an estimate of gas power and driver shaft power.

For tuning many parameters across a whole model by optimization, use a calibration /
data-reconciliation workflow. This skill owns compressor-curve-specific checks.

## Inputs

- Gas state: `p_in`, `p_out` (bara), `T_in` (K), molar mass `MW` (g/mol),
  compressibility `Z`, isentropic exponent `k`, mass flow (kg/s).
- A `CompressorCurve`: speed lines mapping a shaft speed (rpm) to a list of
  `(flow, head, efficiency)` points, where flow is volumetric (e.g. m3/h), head is
  polytropic head (J/kg or kJ/kg consistently), efficiency is a fraction in (0, 1].
- Optional `ChartTuning(flow_mult, head_mult, eff_mult, shaft_adder_pct)`.
- A `Drivetrain(gear_ratio, mechanical_loss_frac)`.

## Outputs

- `polytropic_head(...)`: polytropic head in J/kg.
- `CompressorCurve.evaluate(flow, speed)`: `(head, efficiency)` after tuning.
- `gas_power(mass_flow, head, efficiency)`: gas power in W.
- `Drivetrain.shaft_power(gas_power)`: driver shaft power in W.
- `OperatingPoint`: bundles measured head, curve head, deviation, efficiency, powers.

## Engineering Method

Polytropic head uses the standard relation:

$$ H_p = \frac{Z\,R\,T_{in}}{MW}\cdot\frac{1}{m}\left(PR^{m}-1\right),\quad m=\frac{k-1}{k\,\eta_p} $$

with $PR=p_{out}/p_{in}$, $R=8.314\ \mathrm{J/(mol\cdot K)}$ and $MW$ in kg/mol.
Curve lookup interpolates linearly along a speed line by flow. Between speed lines the
fan (affinity) laws scale the nearest line: flow scales with $N$ and head with $N^2$.
Chart tuning applies multiplicative factors to flow, head, and efficiency, plus an
additive shaft-power percentage. Gas power is $\dot m\,H_p/\eta_p$; driver shaft power
adds mechanical losses.

These are transparent screening relations using public correlations. They are not a
substitute for a vendor performance model or a validated NeqSim compressor.

## Python Usage Pattern

```python
from compressor_validation import (
    polytropic_head, CompressorCurve, ChartTuning, Drivetrain, evaluate_operating_point,
)

curve = CompressorCurve(
    speed_lines={
        9000: [(5000, 80_000, 0.78), (7000, 72_000, 0.80), (9000, 60_000, 0.77)],
        10000: [(5500, 99_000, 0.78), (7700, 89_000, 0.80), (9900, 74_000, 0.77)],
    }
)

head = polytropic_head(p_in=60.0, p_out=120.0, T_in=313.0, MW=20.0, Z=0.9, k=1.28,
                       eta_p=0.78)
print("polytropic head [J/kg]:", round(head))

op = evaluate_operating_point(
    curve, flow=7000, speed=9500, mass_flow=90.0,
    p_in=60.0, p_out=120.0, T_in=313.0, MW=20.0, Z=0.9, k=1.28,
    tuning=ChartTuning(head_mult=1.02),
    drivetrain=Drivetrain(gear_ratio=1.0, mechanical_loss_frac=0.02),
)
print("curve head:", round(op.curve_head), "measured head:", round(op.measured_head))
print("head deviation %:", round(op.head_deviation_pct, 2))
print("shaft power [MW]:", round(op.shaft_power_W / 1e6, 3))
```

## Validation Checklist

- [ ] Efficiency is a fraction in (0, 1], not a percentage.
- [ ] Head units are consistent between curve data and computed polytropic head.
- [ ] Operating flow is within the curve's flow range (extrapolation is flagged).
- [ ] `k`, `Z`, and `MW` reflect the gas at suction conditions.
- [ ] Example inputs are public and synthetic.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Head off by ~1000x | mixing J/kg and kJ/kg | keep one unit throughout |
| Efficiency > 1 in power calc | efficiency entered as percent | use a fraction |
| Wild head at off-speed | extrapolating far beyond curve speeds | add nearer speed lines |
| Negative power | `p_out < p_in` | check pressure order |

## Limitations

- Fan-law scaling is approximate and valid only near the reference speed line.
- No surge/stonewall limit checking is performed here (see a VFP/constraints skill).
- Real-gas effects beyond a constant `Z` and `k` are not modelled.
- Not a vendor guarantee method or a substitute for a validated compressor model.

## References

- API Standard 617, Axial and Centrifugal Compressors (general concepts).
- Public turbomachinery texts for polytropic head and fan laws.
- NeqSim repository: https://github.com/equinor/neqsim
