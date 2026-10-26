---
name: neqsim-h2s-phase-partitioning
calculation_basis: "screening"
version: "0.1.0"
description: "Educational H2S gas/oil/water partitioning with NeqSim SRK-CPA through a separator train, and back-calculation of wellstream H2S from measured separator-gas H2S. USE WHEN: a task has H2S measured in separator or export gas and needs wellstream H2S, the H2S split between gas, oil and produced water, a sour-service pH2S screen, or a gas-to-well H2S conversion table."
last_verified: "2026-10-26"
requires:
  python_packages: ["neqsim"]
  java_packages: []
  env: []
  network: []
---

# H2S Phase Partitioning and Separator-Gas to Wellstream Conversion

Use this skill to turn a measured **separator gas H2S** into a **wellstream H2S**, and to see where H2S goes in a separation train. Gas H2S is what is routinely measured; the reservoir and well question (souring versus injected-water fraction) is about the wellstream. The two differ by the gas/oil/water split, which depends on pressure, temperature, water fraction and composition.

## When to Use

- Convert measured separator or export gas H2S (ppmv) to wellstream H2S (mol fraction or ppmv) per well or per test.
- Build a lookup `factor = wellstream H2S / gas H2S` versus water mole fraction to embed in a larger model.
- Report H2S in oil (ppmw), produced water (mg/L) and each gas stream for a train, with mass-balance closure.
- Screen sour service: H2S partial pressure against the ISO 15156-2 / NACE MR0175 threshold of 0.3 kPa.
- Feed the next step in the souring chain: `neqsim-reservoir-souring-correlation` (fit per-well correlation versus seawater fraction).

## Inputs

- Dry wellstream composition (mole fractions) from the process model, PVT report or E300 file; or use the default demonstration composition.
- Water mole fraction of the wellstream (use `water_mole_fraction(water_sm3_d, dry_kmol_d)` from rates).
- `SeparatorStage(temperature_c, pressure_bara)` list, first stage first, and which stage the gas measurement belongs to.
- Measured gas H2S in ppmv (dry, in the stage gas).

## Outputs

- `ConversionResult`: wellstream H2S (mol fraction, ppmv), conversion factor, full `TrainResult` and warnings.
- `TrainResult`: per stage gas ppmv, oil ppmw, water ppmw and mg/L, pH2S in kPa, and the fractions of H2S leaving with gas, oil and water.
- `conversion_factor_curve(...)`: `(water_mol_fraction, factor)` table for plugging into a setup.

## Engineering Method

1. Build the wellstream with SRK-CPA (`SystemSrkCPAstatoil`, mixing rule 10) including water and H2S; multiphase check on.
2. Flash through `ThreePhaseSeparator` stages. Gas leaves each stage, oil feeds the next stage, water drains with its dissolved H2S.
3. Gas H2S ppmv is monotonic in wellstream H2S, so the back-calculation is a log-space bisection on wellstream H2S to match the measured value (tolerance 1e-6 relative). A measurement outside the reachable bracket raises `ValueError` rather than extrapolating.
4. In the dilute limit gas H2S is linear in wellstream H2S, so one probe level gives the factor curve.

Worked demonstration (default composition, one stage at 70 C and 10 bara): the factor wellstream/gas falls from 0.81 at a dry stream to 0.58 at 30 percent water and 0.34 at 60 percent water mole fraction. Gas is richer in H2S than the wellstream, and more water carries more H2S to the water phase. These are demonstration values, not field values.

## Python Usage Pattern

```python
from h2s_partitioning import (SeparatorStage, make_wellstream, wellstream_h2s_from_separator_gas,
                              conversion_factor_curve, is_sour_service)

stages = [SeparatorStage(70.0, 10.0, "HP"), SeparatorStage(60.0, 2.0, "LP")]
fluid = make_wellstream(composition=None, water_mol_fraction=0.3, h2s_mol_fraction=1e-5)
res = wellstream_h2s_from_separator_gas(fluid, stages, measured_gas_h2s_ppmv=170.0, stage_index=0)
print(res.wellstream_h2s_ppmv, res.conversion_factor, res.train.to_water_fraction)
table = conversion_factor_curve(None, stages, [0.0, 0.1, 0.3, 0.5])
```

Use the project interpreter with `neqsim` installed; for a real field pass the field composition (and a plus-fraction characterisation) instead of the default.

## Validation Checklist

- [ ] H2S balance closure `to_gas + to_oil + to_water` within 2 percent (a warning is raised otherwise).
- [ ] Round trip: flash with the solved wellstream H2S and reproduce the measured gas ppmv.
- [ ] Composition, GOR and water fraction come from the same test or period as the H2S measurement.
- [ ] Separator pressure and temperature are the measured values at the sample time, not design values.
- [ ] Sample point: gas from the stage actually sampled, dry or wet basis stated, ppmv versus mol-ppm treated consistently.
- [ ] Sensitivity run on water fraction and composition (a factor curve), because the factor moves strongly with water.
- [ ] Results reported with the limits below.

## Limits

- Physical partitioning only. H2S ionisation in produced water (HS-, depends on pH, CO2 and alkalinity) and reaction with iron or scale are not modelled; at high pH or high water fraction the real water phase holds more H2S than predicted.
- No PVT tuning for H2S: check against a measured H2S distribution when one exists.
- Water drains per stage (no produced-water degasser, no recycle); compressor recycles and recompressed gas change the measured gas H2S and are not in the simple train.
- Gas sampled wet or after dehydration changes ppmv basis; state it.

## Common Mistakes

- Treating separator gas ppmv as wellstream ppmv. The ratio is 0.3 to 0.9 in the demonstration range, not 1.
- Using one factor for all water fractions. The factor depends strongly on water mole fraction (and so on seawater breakthrough).
- Forgetting `init(0)` on cloned fluids before reading `getz()`; this skill's helpers do it.
- Reporting mg/L in water from mole fractions without the water density.
- Using `getNumberOfMolesInPhase` for phase mole totals; use beta times total moles, or stream flow rates as done here.
