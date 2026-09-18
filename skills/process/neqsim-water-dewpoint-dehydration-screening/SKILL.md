---
name: neqsim-water-dewpoint-dehydration-screening
calculation_basis: "screening"
version: "0.2.0"
description: "Educational gas water-content and dehydration screening using the public GPSA Bukacek saturated-water-content correlation. USE WHEN: a task needs a public, screening-level estimate of saturated water content in natural gas, a check against a sales-gas water spec, or a decision on whether a stated stream composition is already DEHYDRATED or merely cooled and knocked out (the saturation test), before detailed dehydration design or before asserting any hydrate/ice finding."
last_verified: "2026-09-11"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Water Dewpoint Dehydration Screening

Use this skill for public, educational gas water-content screening. It estimates the saturated water content of natural gas using the open GPSA Bukacek correlation and compares it to a sales-gas water specification so an agent can flag whether dehydration is likely required before detailed design.

## When to Use

- When a user asks whether a gas stream needs dehydration to meet a water spec.
- When an agent needs a quick saturated-water-content estimate to scope a dehydration study.
- When examples must run without confidential dehydration designs, glycol data, or company gas specs.
- **Before asserting any hydrate, ice, or free-water finding** — run the saturation test below to establish whether free water is actually available. A hydrate finding built on an unverified water number is the single easiest way to produce a confident wrong answer.

## Is the stream already dehydrated? — the saturation test

A stated water content in a datasheet or stream table tells you nothing on its own; you have to compare it against saturation at the *same* pressure and temperature.

```
ratio = stated_water_content / saturated_water_content(P, T)

ratio ~ 1.0   -> stream is AT SATURATION: wet gas, free water available.
                 Water was removed (if at all) by COOLING + KNOCK-OUT, not dehydration.
ratio << 1    -> stream is DEHYDRATED (glycol contactor or molecular sieve upstream).
                 Typical TEG: 30-50 ppm(mol); typical sales-gas spec: ~100 ppm(mol).
ratio > 1.0   -> the stated composition carries entrained/free water, or the stated
                 P/T is not the condition the composition belongs to. Resolve before use.
```

### Dewatering is not dehydration

This is the trap the test exists to catch. A **suction scrubber**, **knock-out drum**, or **cooler + separator** removes *free* water and leaves the gas **exactly at saturation** at the separator outlet condition. It lowers the absolute water content but gives **zero dryness margin** — the stream re-condenses water on any subsequent cooling or expansion. Only a **glycol contactor** or a **molecular sieve** produces an actual water dew-point depression.

Seeing a scrubber on the P&ID and concluding "the gas is dry" is wrong. Seeing a *contactor with a regeneration package* is the evidence that matters.

### Where to get the authoritative water number

Prefer the **PFD heat & material balance** over an equipment datasheet: the H&M stream table shows the whole removal path stream by stream (inlet -> cooled -> separator liquid -> separator gas), so the mechanism is visible, not inferred. A separator liquid stream at tens of mol-% water is direct proof of knock-out.

Two cautions when reading these:

- **A datasheet water content that lands exactly on saturation is a design assumption marker**, not a measurement — the process engineer set "water = saturation at inlet". Treat it as the conservative wet basis it is, and say so.
- **The PFD case and the datasheet case are often different duties** (different year, feed or rate), so their pressures, temperatures and water contents legitimately differ. Carry both; do not silently blend them.

### Computing saturation rigorously

Bukacek (below) is fine for screening. For a decisive answer, or below 0 °C, or with significant CO2/H2S, use NeqSim CPA: add the dry components plus an *excess* of water so a free water phase is guaranteed, flash at the stated P and T, and read the water mole fraction back out of the gas phase.

```python
from neqsim import jneqsim

SystemSrkCPAstatoil = jneqsim.thermo.system.SystemSrkCPAstatoil
ThermodynamicOperations = jneqsim.thermodynamicoperations.ThermodynamicOperations

def saturated_water_mole_fraction(dry_components, pressure_bara, temperature_c):
    """Water mole fraction in the gas when a free water phase is present."""
    s = SystemSrkCPAstatoil(273.15 + temperature_c, pressure_bara)
    total = sum(dry_components.values())
    for name, x in dry_components.items():
        s.addComponent(name, x / total)
    s.addComponent("water", 0.05)          # excess -> guarantees a free water phase
    s.setMixingRule(10)                     # CPA
    s.setMultiPhaseCheck(True)
    ThermodynamicOperations(s).TPflash()
    s.initProperties()
    return float(s.getPhase("gas").getComponent("water").getx())
```

Cross-check with `waterDewPointTemperatureMultiphaseFlash()`: if the computed water dew point of the stated composition equals the stated stream temperature, the stream is saturated.

## Inputs

- `pressure`: gas pressure in bar absolute.
- `temperature`: gas temperature in kelvin.
- `water_spec`: sales-gas water-content specification in lb/MMscf, default 7.0 (common pipeline spec).

## Outputs

- `saturated_water_content_lb_mmscf`: saturated water content from the Bukacek correlation.
- `water_spec_lb_mmscf`: the supplied water specification.
- `spec_ratio`: ratio of saturated water content to the spec.
- `dehydration_required`: whether the saturated content exceeds the spec.
- `dehydration_warning`: `ok`, `watch`, or `dehydration-required`.
- `assumptions`: public assumptions used by the placeholder model.

## Engineering Method

The Python class `WaterDewpointModel` uses the open GPSA Bukacek correlation only:

- the saturated water content uses `W = A / P + B`, where `A` and `B` are public temperature-dependent terms and `P` is in psia.
- the spec ratio compares the saturated content to the supplied water spec.
- the warning is a simple rule-based label aligned with sales-gas dehydration intent.

This is educational and screening-only logic. The Bukacek correlation is for sweet natural gas in equilibrium with liquid water and is most accurate above 32 F. It does not include acid-gas corrections, salinity, hydrate suppression, or glycol contactor performance. It is not a replacement for validated water-content and dehydration design (for example GPSA and rigorous thermodynamics) and a qualified process review.

## Python Usage Pattern

```python
from water_dewpoint_dehydration_screening import WaterDewpointModel

model = WaterDewpointModel()
result = model.evaluate(
    pressure=70.0,
    temperature=305.15,
)

print(result.dehydration_warning)
print(result.saturated_water_content_lb_mmscf)
print(result.dehydration_required)
```

## Related NeqSim Functionality

For validated water-content and dehydration calculations, redirect to existing NeqSim functionality:

- `neqsim.thermo.system.SystemSrkCPAstatoil` (CPA equation of state) — rigorous water content and water dew point for natural gas.
- `neqsim.process.design.template.DehydrationTemplate` — TEG dehydration process template.
- `neqsim.process.equipment.absorber` glycol contactor models — detailed dehydration performance.

This skill is a public Bukacek triage layer that decides when to invoke validated NeqSim water-content and dehydration models.

## Validation Checklist

- [ ] Pressure and temperature are positive and in the stated units.
- [ ] Example inputs are public and synthetic.
- [ ] Tests cover an in-spec case, a dehydration-required case, and invalid input.
- [ ] Results are described as educational screening indicators.
- [ ] Real design is redirected to validated methods, GPSA, NeqSim CPA, and qualified review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Water content too low | Acid-gas content ignored | Add CO2 and H2S corrections with a validated method |
| Spec check wrong | Volume basis mismatch (MMscf vs MMsm3) | Keep the water spec on the same basis as the correlation |
| Out-of-range result | Temperature below the correlation range | Use a validated method below freezing or near hydrate conditions |
| "There is a scrubber, so the gas is dry" | Confusing dewatering with dehydration | Run the saturation test; a scrubber leaves the gas AT saturation |
| Hydrate finding collapses under review | Water basis never verified | Run the saturation test before asserting any hydrate/ice consequence |
| Two documents disagree on water content | Different operating cases (year, feed, rate) | Carry both cases; do not blend or silently pick one |
| `dewPointTemperatureFlash()` raises `IsNaNException: molarVolumeAnalytical - compressibility factor is NaN` | Requested dew point at or above the cricondenbar, where no dew point exists | Guard the call, or get the cricondentherm/cricondenbar from `calcPTphaseEnvelope` instead |

## Limitations

- No proprietary dehydration designs, glycol data, or company gas specs are included.
- No acid-gas, salinity, or hydrate-suppression corrections are performed.
- No glycol contactor or regeneration performance is modeled.

## References

- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Skills Guide: https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
