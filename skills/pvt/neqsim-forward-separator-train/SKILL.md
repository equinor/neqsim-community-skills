---
name: neqsim-forward-separator-train
calculation_basis: "neqsim-java"
version: "0.1.0"
description: "Run one fluid (E300 file or composition) through a forward-only, no-recycle multi-stage separator train (HP, MP, LP, stock tank) the way PVTsim and ECL300 do, and return GOR, Bo, stock-tank oil density/API and gas per stage. USE WHEN: a user says 'run this fluid through the separator train', 'kjør dette for et gitt fluid', needs surface-process results (GOR, Bo, STO, gas rates) for an E300 fluid, or wants a single reproducible case that can later be repeated for many compositions."
last_verified: "2026-11-08"
requires:
  python_packages: [neqsim]
  java_packages: []
  env: []
  network: []
---

# Forward Separator Train for One Fluid

A forward train has no recycle: liquid cascades from stage to stage and every gas
stream leaves the system. For a fixed composition and fixed stage pressures and
temperatures the result is therefore unique and needs no iteration. This is the
same separator test PVTsim and ECL300 run, so results can be compared directly.

The skill runs **one** fluid. To study variation, call it once per fluid
(see "Many fluids" below).

## When to Use

- A fluid is given as an E300 file (or a mole-fraction table) and surface results are needed.
- GOR, Bo, stock-tank oil density/API, or gas rate and gas MW per stage are requested.
- A PVTsim or ECL300 separator-test number must be reproduced or sanity-checked.

Do not use it for trains with recycles or with feedback from compressors or
coolers into earlier stages; build a `ProcessSystem` with recycles instead.

## Inputs

| Input | Default | Notes |
| --- | --- | --- |
| E300 file or `--composition` JSON | required | Exactly one. JSON: `{"eos":"srk","components":{"methane":0.7,...}}` (`srk` or `pr`, library component names). |
| `--feed-p` | 250 bara | Set to reservoir (or wellstream) pressure. |
| `--feed-t` | 100 degC | Set to reservoir (or wellstream) temperature. |
| `--stages` | `70:60,20:50,2:40` | `bara:degC` per stage, strictly falling pressure. Stock tank at 15 degC and 1.01325 bara is always appended. |
| `--flow` | 100000 kg/hr | Only scales absolute rates; GOR and Bo do not depend on it. |
| `--out` | none | Writes the result JSON. |

Ask the user for the stage P/T and feed conditions if they are not given. The
defaults are placeholders, not a design.

## Run

```
<python> scripts/run_forward_separator.py fluid.e300 --feed-p 300 --feed-t 110 \
    --stages "70:60,20:50,2:40" --out result.json
```

`<python>` is the interpreter with the `neqsim` package. The script builds, per
stage: `ThrottlingValve` to the stage pressure, `Heater` to the stage
temperature, `Separator`; the liquid outlet feeds the next stage.

## Outputs (JSON)

- `GOR_Sm3_Sm3`: total gas of all stages including stock tank, per Sm3 of stock-tank oil (gas at 15 degC, 1.01325 bara, ideal-gas conversion).
- `Bo_m3_Sm3`: feed volume at feed P/T divided by stock-tank oil volume.
- `STO_density_kgm3`, `STO_API`, `STO_Sm3_h`: stock-tank oil.
- `stages[]`: `P_bara`, `T_C`, `gas_Sm3_h`, `gas_MW_gmol`, `liquid_kg_h` per stage.
- `feed_n_phases`, `mass_balance_rel_err`, `warnings[]`.

## Validation checks (do before reporting)

1. `mass_balance_rel_err` below 1e-6.
2. `feed_n_phases`: if 2 at feed P/T, the feed is not a single-phase reservoir
   fluid (feed below saturation, or feed P/T wrong). Bo then describes the mixed
   stream; say so, or correct the feed conditions.
3. GOR and API are physically plausible for the fluid type (black oil about
   50-300 Sm3/Sm3, 25-40 API; volatile oil/condensate much higher GOR, higher API).
4. For a PVTsim/ECL300 comparison, confirm the same stage P/T, the same standard
   conditions (15 degC, 1.01325 bara) and the same EOS parameters (volume shift,
   kij) before attributing differences to the model.

## Many fluids

The user normally runs variations themselves: loop the script over several E300
files or composition JSONs and collect the `GOR_Sm3_Sm3`, `Bo_m3_Sm3` and
`STO_API` fields into a table. If asked to generate the compositions, use a
Latin hypercube of mole fractions (for example +-20 % on each C1-C6 component and
on the C7+ amount, and a tilt of the C7+ distribution so MW and SG shift
consistently with the pseudo-component EOS parameters), renormalise to 1.0, and
keep stage P/T and feed P/T fixed across cases so the cases are comparable.

## Limits

- Equilibrium stages only; no entrainment, carry-over or separation efficiency.
- Water is not treated specially; an aqueous phase in the liquid outlet is counted as liquid.
- Stage gas rates are ideal-gas standard volumes, which can differ by a fraction of a percent from PVTsim's real-gas standard volumes.
