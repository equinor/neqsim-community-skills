---
name: neqsim-compressor-power-screening
version: "0.1.0"
description: "Educational centrifugal-compressor power screening using the public polytropic-head equation (API 617 / API 619 style). USE WHEN: a task needs a public, screening-level estimate of polytropic head, discharge temperature, and gas power for a single compression stage before detailed compressor selection."
last_verified: "2026-06-18"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Compressor Power Screening

Use this skill for public, educational centrifugal-compressor power screening. It estimates polytropic head, discharge temperature, and gas power for a single compression stage using the open polytropic-head equation so an agent can scope a compression study and check against a rated driver power before detailed selection.

## When to Use

- When a user asks roughly how much power a compression stage needs.
- When an agent needs a quick polytropic-head and discharge-temperature estimate.
- When examples must run without confidential compressor curves, vendor data, or company specs.

## Inputs

- `suction_pressure`: stage suction pressure `P1` in bar absolute.
- `discharge_pressure`: stage discharge pressure `P2` in bar absolute.
- `suction_temperature`: stage suction temperature `T1` in kelvin.
- `mass_flow`: gas mass flow in kg/s.
- `molecular_weight`: gas molecular weight `M` in g/mol.
- `specific_heat_ratio`: ratio of specific heats `k`, default 1.3.
- `compressibility`: average compressibility factor `Z`, default 1.0.
- `polytropic_efficiency`: polytropic efficiency, default 0.78.
- `rated_power`: optional rated driver power in kW for the comparison.

## Outputs

- `pressure_ratio`: `P2 / P1`.
- `polytropic_head_kj_kg`: polytropic head.
- `discharge_temperature_k`: estimated discharge temperature.
- `gas_power_kw`: gas power on the shaft.
- `power_margin_ratio`: ratio of rated power to gas power, or `null` if no rated power supplied.
- `compressor_warning`: `ok`, `watch`, `over-rated`, or `no-rating`.
- `assumptions`: public assumptions used by the placeholder model.

## Engineering Method

The Python class `CompressorPowerModel` uses the open polytropic-head equation only:

- the polytropic exponent uses `(n - 1) / n = (k - 1) / (k * polytropic_efficiency)`.
- the polytropic head uses `Hp = Z R T1 (n / (n - 1)) [(P2 / P1)^((n-1)/n) - 1]`, with `R = 8.314 / M`.
- the discharge temperature uses `T2 = T1 (P2 / P1)^((n-1)/n)`.
- the gas power uses `power = mass_flow * Hp / polytropic_efficiency`.

This is educational and screening-only logic. It assumes a single stage, constant `k` and `Z`, and an ideal-gas head form. It does not include real-gas property variation, intercooling, mechanical losses, surge or stonewall limits, or vendor curves. It is not a replacement for validated compressor selection and a qualified rotating-equipment review.

## Driver Power-Margin Sizing (operating margin to rated/max power)

When the binding limit is the **driver / rated maximum power** (not surge), a
common operations question is *how large a power margin to keep* so the machine
can run close to maximum without tripping. The screening relation is dimensionless:

- At near-constant pressure ratio, `power ∝ mass flow`, so
  **throughput headroom [%] = power_margin / operating_power**.
- Therefore the *same absolute MW margin protects a smaller machine less* — margin
  must be **scaled to each machine's operating power**, not applied as a flat MW.
  To give machine B the same % headroom as machine A: `margin_B = margin_A × (P0_B / P0_A)`.
- Size the margin to the **fastest credible power excursion** before the control
  system reacts. The dominant excursions raise the pressure ratio: a **suction-pressure
  drop** or a **discharge-pressure rise**. A downstream pressure controller (e.g. an
  MPC holding delivery pressure fixed) removes a first-order power disturbance and so
  *buys back* margin: residual swing `≈ (∂power/∂P_discharge) × ΔP_controlled`.

Obtain the local slopes `∂power/∂flow`, `∂power/∂P_suction`, `∂power/∂P_discharge`,
`∂power/∂T_suction` by finite-differencing a validated `Compressor.getPower()` around
the operating point (this screening class only gives the flow-proportional term). The
**driver rated power and performance curves must come from STID/vendor data** before
any margin is fixed. (Pattern first used for a Troll A export-compressor power-margin
PEPR action; see the `compressor-agent` / `enterprise-compressor-agent`.)

## Python Usage Pattern

```python
from compressor_power_screening import CompressorPowerModel

model = CompressorPowerModel()
result = model.evaluate(
    suction_pressure=30.0,
    discharge_pressure=90.0,
    suction_temperature=313.15,
    mass_flow=25.0,
    molecular_weight=19.0,
    rated_power=8000.0,
)

print(result.compressor_warning)
print(result.gas_power_kw)
print(result.discharge_temperature_k)
```

## Related NeqSim Functionality

For validated compressor calculations, redirect to existing NeqSim classes:

- `neqsim.process.equipment.compressor.Compressor` — rigorous polytropic compression with real-gas properties and curves.
- `neqsim.process.equipment.compressor.CompressorChart` — vendor performance maps and surge control.
- `neqsim.process.mechanicaldesign.compressor.CompressorMechanicalDesign` — compressor mechanical design and feasibility.

This skill is a public polytropic-head triage layer that decides when to invoke those validated compressor classes.

## Validation Checklist

- [ ] Suction and discharge pressures are positive and `P2 > P1`.
- [ ] Temperature, mass flow, and molecular weight are positive.
- [ ] Tests cover a head and power calculation, a rating comparison, and invalid input.
- [ ] Results are described as educational screening indicators.
- [ ] Real selection is redirected to validated NeqSim compressor classes and qualified review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Discharge temperature too high | Single high-ratio stage assumed | Split into stages with intercooling |
| Power off significantly | Constant `Z` over a wide range | Use a real-gas method like the NeqSim Compressor |
| Head looks wrong | Molecular weight in kg/mol not g/mol | Keep `M` in g/mol |

## Limitations

- No proprietary compressor curves, vendor data, or company specs are included.
- No intercooling, mechanical losses, or surge and stonewall limits are modeled.
- No real-gas property variation across the stage is included.

## References

- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Skills Guide: https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
