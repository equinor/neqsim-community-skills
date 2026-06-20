---
name: neqsim-control-valve-cv-screening
version: "0.1.0"
description: "Educational control-valve sizing screening that estimates the required flow coefficient (Kv/Cv) and flags choked flow per public IEC 60534-2-1 / ISA-75.01 equations for liquid and gas service. USE WHEN: a task needs a public, screening-level required Cv and a choked-flow flag before detailed control-valve selection."
last_verified: "2026-06-18"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Control Valve Cv Screening

Use this skill for public, educational control-valve sizing screening. It estimates the required flow coefficient (Kv and Cv) and flags choked flow for liquid and gas service using the open IEC 60534-2-1 / ISA-75.01 equations so an agent can scope a valve and decide whether to invoke validated NeqSim valve calculations.

## When to Use

- When a user asks roughly what Cv a control valve needs for a duty.
- When an agent needs a quick choked-flow (flashing or critical) flag.
- When examples must run without confidential valve data, vendor curves, or company specs.

## Inputs

Common:

- `service`: `"liquid"` or `"gas"`.
- `inlet_pressure`: valve inlet pressure `P1` in bar absolute.
- `pressure_drop`: valve pressure drop `dP` in bar.
- `rated_cv`: optional rated valve Cv for the margin check.

Liquid service:

- `flow_rate`: volumetric flow in m3/h.
- `specific_gravity`: liquid specific gravity (water = 1).
- `vapor_pressure`: fluid vapor pressure in bar absolute, default 0.
- `critical_pressure`: fluid critical pressure in bar absolute (for `FF`), optional.
- `fl`: liquid pressure-recovery factor `FL`, default 0.9.

Gas service:

- `mass_flow`: gas mass flow in kg/h.
- `inlet_density`: inlet gas density in kg/m3.
- `specific_heat_ratio`: ratio of specific heats `k`, default 1.3.
- `xt`: pressure-drop-ratio factor `xT`, default 0.7.

## Outputs

- `service`: the resolved service.
- `required_kv`: required flow coefficient in metric Kv.
- `required_cv`: required flow coefficient in US Cv (`1.156 * Kv`).
- `choked`: choked-flow flag.
- `choke_limit`: choked pressure drop in bar (liquid) or choking `x` (gas).
- `cv_margin_ratio`: `rated_cv / required_cv`, or `null` if no rating.
- `valve_warning`: `ok`, `watch`, `under-sized`, `choked`, or `no-rating`.
- `assumptions`: public assumptions used by the placeholder model.

## Engineering Method

The Python class `ControlValveCvModel` uses public IEC 60534-2-1 / ISA-75.01 equations:

- liquid Kv uses `Kv = Q * sqrt(SG / dP_sizing)`.
- the liquid liquid-critical-pressure-ratio factor uses `FF = 0.96 - 0.28 * sqrt(Pv / Pc)`.
- liquid choke occurs when `dP >= FL^2 * (P1 - FF * Pv)`; the sizing `dP` is capped at this limit.
- gas uses `x = dP / P1`, `Fk = k / 1.4`, choke `x = Fk * xT`, expansion factor `Y = 1 - x / (3 Fk xT)` bounded to `[0.667, 1]`, and the mass-flow form `Kv = W / (N6 * Y * sqrt(x * P1 * rho1))` with `N6 = 27.3`.
- `Cv = 1.156 * Kv`.

This is educational and screening-only logic. It assumes single-phase, fully turbulent flow with no piping geometry factor (`Fp`), no Reynolds-number correction, and no two-phase or flashing mixture handling. It is not a replacement for validated control-valve sizing and qualified selection.

## Python Usage Pattern

```python
from control_valve_cv_screening import ControlValveCvModel

model = ControlValveCvModel()
result = model.evaluate(
    service="gas",
    inlet_pressure=50.0,
    pressure_drop=12.0,
    mass_flow=5000.0,
    inlet_density=40.0,
    specific_heat_ratio=1.3,
)

print(result.required_cv)
print(result.choked)
print(result.valve_warning)
```

## Related NeqSim Functionality

For validated control-valve behaviour, redirect to existing NeqSim classes:

- `neqsim.process.equipment.valve.ThrottlingValve` — flow-vs-Cv valve with `getCv` / `setCv` and pressure-drop response.
- `neqsim.process.equipment.valve.ControlValve` — control valve with characteristic and controller coupling.
- `neqsim.process.equipment.valve.SafetyValve` — relief-valve modelling for the relieving case.

This skill is a public sizing triage layer that decides when to invoke those validated valve classes.

## Validation Checklist

- [ ] `inlet_pressure` and `pressure_drop` are positive and `dP < P1`.
- [ ] Liquid service supplies flow and specific gravity; gas service supplies mass flow and density.
- [ ] The choked flag uses `FL` (liquid) or `Fk xT` (gas).
- [ ] Tests cover liquid sizing, gas sizing, choking, rating margin, and invalid input.
- [ ] Real sizing is redirected to validated NeqSim valve classes and qualified review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Cv too small | Used choked `dP` not realising flow is critical | The model caps `dP`; check the `choked` flag |
| Gas Cv off | Density not at inlet conditions | Pass `inlet_density` at `P1`, `T1` |
| Liquid choke never flags | `vapor_pressure` left at 0 | Provide vapor and critical pressure |
| Wrong units | `Q` in m3/s or `W` in kg/s | Use m3/h (liquid) and kg/h (gas) |

## Limitations

- No piping geometry factor `Fp`, Reynolds correction, or low-flow laminar handling.
- No two-phase, flashing, or multiphase valve sizing.
- No vendor valve characteristic, noise, or actuator sizing.
