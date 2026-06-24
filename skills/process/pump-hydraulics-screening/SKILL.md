---
name: neqsim-pump-hydraulics-screening
version: "0.1.0"
description: "Educational centrifugal-pump hydraulics screening for hydraulic/shaft power, NPSH-available, and best-efficiency-point window using public pump relations and affinity laws. USE WHEN: a task needs a public, screening-level pump power, NPSH-available estimate, and BEP-window check before detailed pump selection."
last_verified: "2026-06-18"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Pump Hydraulics Screening

Use this skill for public, educational centrifugal-pump hydraulics screening. It estimates hydraulic and shaft power, the available net positive suction head (NPSHa), and the best-efficiency-point (BEP) flow ratio so an agent can scope a pumping duty and decide whether to invoke validated NeqSim pump calculations.

## When to Use

- When a user asks roughly how much power a pump duty needs.
- When an agent needs a quick NPSH-available margin and cavitation triage.
- When an agent must check that an operating flow sits inside a sensible BEP window.
- When examples must run without confidential pump curves, vendor data, or company specs.

## Inputs

- `flow_rate`: operating volumetric flow in m3/h.
- `head`: pump differential head in m.
- `density`: pumped-fluid density in kg/m3.
- `efficiency`: pump hydraulic efficiency, default 0.70.
- `suction_pressure`: optional suction pressure in bar absolute (for NPSHa).
- `vapor_pressure`: optional fluid vapor pressure in bar absolute (for NPSHa).
- `static_suction_head`: optional static suction head in m, default 0.
- `friction_loss`: optional suction friction loss in m, default 0.
- `npsh_required`: optional NPSH required in m (for the margin).
- `bep_flow_rate`: optional best-efficiency-point flow in m3/h (for the ratio).

## Outputs

- `hydraulic_power_kw`: hydraulic (fluid) power.
- `shaft_power_kw`: estimated shaft power.
- `npsh_available_m`: available NPSH, or `null` if suction data is not supplied.
- `npsh_margin_m`: `NPSHa - NPSHr`, or `null` if not enough data.
- `bep_ratio`: `flow_rate / bep_flow_rate`, or `null` if BEP flow not supplied.
- `pump_warning`: `ok`, `watch`, `off-bep`, `npsh-deficit`, or `no-rating`.
- `assumptions`: public assumptions used by the placeholder model.

## Engineering Method

The Python class `PumpHydraulicsModel` uses public pump relations only:

- hydraulic power uses `P = rho * g * Q * H`, with `Q` converted from m3/h to m3/s.
- shaft power uses `P_shaft = P_hydraulic / efficiency`.
- available NPSH uses `NPSHa = (P_suction - P_vapor) / (rho * g) + static_suction_head - friction_loss`.
- the BEP check uses the flow ratio `Q / Q_bep` against a public preferred window (default 0.70 to 1.20).

This is educational and screening-only logic. It assumes constant density, a single operating point, and does not model affinity-law scaling beyond the inputs, suction recirculation, viscosity correction, minimum-flow recycle, or vendor curves. It is not a replacement for validated pump selection and a qualified rotating-equipment review.

## Python Usage Pattern

```python
from pump_hydraulics_screening import PumpHydraulicsModel

model = PumpHydraulicsModel()
result = model.evaluate(
    flow_rate=120.0,
    head=95.0,
    density=820.0,
    efficiency=0.74,
    suction_pressure=4.0,
    vapor_pressure=1.5,
    static_suction_head=3.0,
    friction_loss=0.8,
    npsh_required=3.5,
    bep_flow_rate=130.0,
)

print(result.pump_warning)
print(result.shaft_power_kw)
print(result.npsh_margin_m)
```

## Related NeqSim Functionality

For validated pump calculations, redirect to existing NeqSim classes:

- `neqsim.process.equipment.pump.Pump` — rigorous pump power and head with real-fluid properties.
- `neqsim.process.equipment.pump.PumpCurve` / `PumpChart` — vendor head, efficiency, and power curves.
- `neqsim.process.equipment.pump.ESPPump` / `JetPump` — specialized pump types.

This skill is a public hydraulics triage layer that decides when to invoke those validated pump classes.

## Validation Checklist

- [ ] Flow, head, and density are positive.
- [ ] Efficiency is in the interval (0, 1].
- [ ] NPSHa is only reported when suction and vapor pressures are supplied.
- [ ] Tests cover power, NPSH margin, BEP ratio, and invalid input.
- [ ] Real selection is redirected to validated NeqSim pump classes and qualified review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Power off by a factor | Flow left in m3/h not converted to m3/s | The model converts internally; pass m3/h |
| NPSHa missing | Suction or vapor pressure not supplied | Provide both `suction_pressure` and `vapor_pressure` |
| BEP ratio missing | `bep_flow_rate` not supplied | Provide the pump BEP flow |
| Cavitation not caught | Constant-density assumption near bubble point | Use the validated NeqSim Pump with real properties |

## Limitations

- No proprietary pump curves, vendor data, or company specs are included.
- No viscosity correction, suction recirculation, or minimum-flow recycle is modeled.
- No real-fluid property variation across the pump is included.

## References

- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Skills Guide: https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
