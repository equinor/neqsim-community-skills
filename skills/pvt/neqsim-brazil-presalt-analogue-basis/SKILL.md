---
name: neqsim-brazil-presalt-analogue-basis
calculation_basis: "screening"
version: "0.1.0"
description: "Declared best-guess fluid and flow-assurance basis for Santos Basin pre-salt blocks when no PVT exists: analogue ranges, CO2-rich gas handling, material and EOS checks, and an assumption register. USE WHEN: a frontier block in Santos or Campos pre-salt must be evaluated, a CO2-rich associated gas or CO2 re-injection case is in play, or a near-field analogue fluid is needed."
last_verified: "2026-10-09"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Brazil Pre-Salt Analogue Basis

Advisory skill. It tells an agent how to build a declared, low/base/high fluid and flow-assurance basis for a pre-salt block that has no PVT report, and what to check before trusting a NeqSim result on it.

## Method

1. Start from `neqsim-reference-fluid-synthetic-generation` (no-PVT route): reservoir temperature from the depth and a stated geothermal gradient, GOR and oil density bands from named analogue fields, and low/base/high cases.
2. Treat the analogue values as inputs to confirm, not facts. Pre-salt carbonate reservoirs are generally light to medium oil with high GOR and CO2 in the associated gas that varies strongly between fields and within a field. Set the CO2 range from the analogue data you can cite, and record the source in the assumption register.
3. Run the low and high CO2 cases through the whole chain, not only the base case. CO2 content drives phase envelope, hydrate and dense-phase behaviour, separation and compression duty, and the need for CO2 removal or re-injection.
4. Gate the numbers before use:
   - Check a CO2-rich phase envelope and a saturation pressure against any available analogue PVT; flag if the EOS is outside its validated range. The NeqSim test `Co2RichAssociatedGasConsistencyTest` is the pass/fail gate for physical consistency (pure-CO2 critical temperature, bubble pressure rising with CO2, one dense phase above the cricondenbar). It is not a validation against measured pre-salt PVT; add measured data per field and say so in `data_gaps`.
   - Check hydrate and freezing margins on the CO2-rich gas.
   - Screen materials for sour or CO2 service with `neqsim-flow-assurance` and the material-selection skills; high CO2 partial pressure at depth is a corrosion driver.
5. Show the effect of re-injecting CO2 or gas as a separate case with `neqsim-ccs-hydrogen`.

## Outputs

- Low/base/high fluid composition and properties.
- Phase-envelope and hydrate margin per case.
- CO2 removal and re-injection screening flag.
- `assumptions` and `data_gaps` entries naming every analogue used.

## Related

- `neqsim-reference-fluid-synthetic-generation`, `neqsim-reservoir-model-builder`, `neqsim-phase-envelope`, `neqsim-flow-assurance`, `neqsim-ccs-hydrogen`, `neqsim-psc-bid-economics-screening`.
