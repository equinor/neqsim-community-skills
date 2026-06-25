---
name: neqsim-produced-water-scale-screening
version: "0.1.0"
description: "Public produced-water brine builder and screening-level scale evaluation. USE WHEN: a task needs to turn an ion analysis, preset, or TDS value into a NeqSim-ready electrolyte ion mapping and a quick scale/mixing-incompatibility screening (BaSO4, SrSO4, CaSO4, CaCO3), and should be directed to validated NeqSim checkScalePotential methods for design-grade work."
last_verified: "2026-06-02"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Produced Water Scale Screening

Use this skill to build a normalized produced-water (brine) description from an
ion analysis, a built-in preset, or a single total-dissolved-solids value; check
its charge balance; and emit a **NeqSim-ready ion mapping** for
`neqsim.thermo.util.ProducedWaterFluidBuilder`. It also computes
**screening-level** scale saturation indices, a two-water mixing-incompatibility
sweep, and informational CO2/H2S corrosion flags. It is intentionally simple and
should guide users toward validated NeqSim electrolyte-CPA scale calculations for
real work.

## When to Use

- When a user wants to convert a water analysis into a NeqSim electrolyte fluid input.
- When a user asks which oilfield scales (barite, celestite, gypsum/anhydrite, calcite) a water tends to form.
- When screening seawater-injection or commingling incompatibility (formation-water Ba/Sr meeting injected SO4).
- When an agent should explain that validated NeqSim methods are required for design-grade scale and inhibitor work.

## Inputs

- `ions_mg_l`: explicit ion concentrations in mg/L (e.g. `Na+`, `Cl-`, `Ca++`, `Mg++`, `Ba++`, `Sr++`, `SO4--`, `HCO3-`).
- `preset`: one of `seawater`, `formation_water_high_ba`, `brackish`.
- `tds_mg_l`: total dissolved solids in mg/L (modelled as pure NaCl).
- `temperature_c`: temperature in C (default 25.0).
- `pressure_bara`: pressure in bara (default 1.0).
- `ph`: optional in-situ pH (required for calcite screening).
- For corrosion flags: `co2_mol_percent`, `h2s_mol_percent` of the associated gas.

Exactly one of `ions_mg_l`, `preset`, or `tds_mg_l` must be supplied to `build`.

## Outputs

- `tds_mg_l`: sum of ion concentrations in mg/L.
- `molality`: ion molality in mol/kg.
- `ionic_strength_mol_kg`: brine ionic strength in mol/kg.
- `charge_balance_error_pct`: cation-anion imbalance as a percentage.
- `neqsim_components`: mole-fraction mapping of `water` + ions for the NeqSim builder.
- `neqsim_available`: whether the optional NeqSim package is importable.
- `ScaleResult.saturation_index`: `log10(IAP/Ksp)` per mineral; `>0` means supersaturation.
- `ScaleResult.risk` / `MixIncompatibility.risk`: `low`, `moderate`, `high`, or `unknown`.
- `MixIncompatibility.worst_fraction_a` / `worst_saturation_index`: worst blend point.
- `corrosion_flags`: human-readable CO2/H2S screening flags.
- `warnings`: non-fatal screening warnings (charge balance, ionic-strength validity, unsupported ions).

## Engineering Method

Ion concentrations are converted to molality with public molar masses. Ionic
strength is `I = 0.5 * sum(m_i * z_i^2)`. Activity coefficients use the Davies
equation `log10(gamma) = -A * z^2 * (sqrt(I)/(1+sqrt(I)) - 0.3*I)` with
`A = 0.509`. For each scale the saturation index is
`SI = log10(IAP / Ksp)` where `IAP = (gamma*m_cation)*(gamma*m_anion)`, using
public 25 degC solubility products (BaSO4 1.08e-10, SrSO4 3.44e-7, CaSO4 gypsum
3.14e-5, CaCO3 calcite 3.36e-9). Carbonate is derived from bicarbonate and pH via
`[CO3--] = K2 * [HCO3-] / [H+]` with `K2 = 4.69e-11`. The mixing sweep blends two
waters on a volume basis and reports the worst-case SI per mineral. Risk bands:
`SI >= 0.5` high, `SI >= 0.0` moderate, otherwise low; missing ions or pH give
`unknown`.

This is not a Pitzer or electrolyte-EOS model. Solubility products are fixed at
25 degC, and the Davies model is only valid up to roughly 0.5 mol/kg, so indices
for concentrated brines are indicative only.

## Python Usage Pattern

```python
from produced_water_scale_screening import ProducedWaterBuilder, ScaleScreener

builder = ProducedWaterBuilder()
formation = builder.build(preset="formation_water_high_ba", ph=6.5)
seawater = builder.build(preset="seawater", ph=8.1)

# NeqSim electrolyte-CPA builder input:
print(formation.neqsim_components)

screener = ScaleScreener()
for result in screener.screen(seawater).results:
    print(result.salt, result.saturation_index, result.risk)

# Seawater-injection incompatibility (Ba/Sr meeting SO4):
for item in screener.mixing_incompatibility(formation, seawater):
    print(item.salt, item.worst_fraction_a, item.worst_saturation_index, item.risk)
```

If the optional `neqsim` Python package is available, the result records that
fact so an agent can recommend moving to validated NeqSim scale workflows. If
not, the example still runs with the public screening logic.

## Validation Checklist

- [ ] Exactly one of `ions_mg_l`, `preset`, or `tds_mg_l` is provided.
- [ ] Ion concentrations are finite and non-negative.
- [ ] Charge balance error is reviewed (warned above 10%).
- [ ] pH is supplied when calcite screening is required.
- [ ] Ionic-strength validity warning is heeded for concentrated brines.
- [ ] Saturation indices are not used as inhibitor doses, deposition rates, or operating limits.
- [ ] Real scale work is redirected to validated NeqSim electrolyte-CPA methods and qualified review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Calcite always `unknown` | pH not supplied | Provide in-situ pH so `[CO3--]` can be derived |
| BaSO4 `unknown` for a single water | No sulfate (or no barium) present | Use the mixing sweep with a sulfate-bearing water |
| SI looks too low for a strong brine | Davies model beyond validity (`I > 0.5`) | Treat as indicative; rerun with NeqSim `checkScalePotential` |
| Ion ignored | Unrecognized ion name | Use supported names (`Na+`, `Ca++`, `Ba++`, `SO4--`, ...) |

## Limitations

- No electrolyte-EOS or Pitzer activity model is performed in this skill.
- Solubility products are fixed at 25 degC; no temperature or pressure dependence.
- No kinetics, supersaturation ageing, or deposition modelling.
- No proprietary scale models, inhibitor correlations, or company operating limits.
- Not suitable for scale-management design, inhibitor selection, or operating-limit decisions.

## Related NeqSim Functionality

This educational screening corresponds to validated, rigorous functionality in
the NeqSim Java library that a qualified engineer should use for design-grade work:

- `neqsim.thermo.util.ProducedWaterFluidBuilder` — builds an electrolyte-CPA produced-water system from TDS, a type preset, or explicit ions (the `neqsim_components` mapping feeds `createFromIons`).
- `neqsim.thermodynamicoperations.ThermodynamicOperations#checkScalePotential(int)` — rigorous scale-potential evaluation on an electrolyte-CPA fluid.
- `neqsim.thermodynamicoperations.ThermodynamicOperations#addIonToScaleSaturation(int, String, String)` — register a scale salt / ion pair for saturation tracking.

In Python the same classes are reachable through the `neqsim` package (for
example `from neqsim import jneqsim`).

## References

- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Skills Guide: https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
- NORSOK M-001 (materials selection) and ISO 15156 / NACE MR0175 (sour service) for the corrosion-flag context.
- Public oilfield-scale literature on barite/celestite/calcite saturation for background.
