---
name: neqsim-e300-fluid-io
version: "0.1.0"
description: "Read, write, and add water to Eclipse E300 fluid files for NeqSim. USE WHEN: a task needs to load an E300 file into a NeqSim fluid, write a NeqSim fluid to E300, or add water to a fluid or E300 file with the public PVTsim water parameters (volume shift 0.084004, parachor 10.0, kij 0.5)."
last_verified: "2026-06-01"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# E300 Fluid I/O

Use this skill to move fluids between Eclipse 300 (E300) compositional EOS files
and NeqSim, and to add water to a fluid or E300 file using the public PVTsim
water parameterization.

The skill has two layers:

- A **pure-Python** layer that parses, edits, and writes the E300 keyword format
  without requiring NeqSim. It is used to inspect files, add water, and produce
  E300 files that NeqSim can read back.
- A **NeqSim bridge** that wraps `neqsim.thermo.util.readwrite.EclipseFluidReadWrite`
  to load E300 files into rigorous NeqSim `SystemInterface` fluids, add water,
  and write fluids back to E300.

## When to Use

- When a task provides an E300 file and needs a NeqSim fluid for simulation.
- When a NeqSim fluid must be exported to an E300 file for PVTsim or Eclipse.
- When water must be added to a dry fluid using the public PVTsim water
  parameters (reproducing a PVTsim `*_water.e300` file).
- When an existing E300 file must be copied with water appended as the last
  component with a binary interaction parameter of 0.5 against all components.
- When a task must document or verify the E300 keyword layout.

## Inputs

- `e300_path`: path to an Eclipse E300 file.
- `add_water`: whether to append a water component (H2O).
- `water_kij`: water binary interaction parameter (PVTsim default 0.5).
- `reservoir_temp_c`: reservoir temperature written to the RTEMP keyword.
- `neqsim_fluid`: a NeqSim `SystemInterface` fluid (for export).

## Outputs

- `neqsim_fluid`: a NeqSim fluid created from an E300 file.
- `e300_file`: a written E300 file (with or without water).
- `e300_string`: E300 keyword text for a NeqSim fluid.
- `E300Fluid`: a pure-Python object with component names, EOS parameters, the
  binary interaction matrix, and the overall composition.

## Engineering Method

### E300 file format

An E300 file is a keyword text file. Each keyword introduces a value block that
is terminated by a `/`. Lines starting with `--` are comments. The keywords this
skill reads and writes are:

| Keyword | Meaning | Unit |
| --- | --- | --- |
| `METRIC` | Unit system flag | — |
| `NCOMPS` | Number of components | — |
| `EOS` + `PRCORR`/`PRLKCORR` | Equation of state and correction | — |
| `RTEMP` | Reservoir temperature | °C |
| `STCOND` | Standard temperature and pressure | °C, bara |
| `CNAMES` | Component names | — |
| `TCRIT` | Critical temperature | K |
| `PCRIT` | Critical pressure | bar |
| `ACF` | Acentric factor | — |
| `OMEGAA`, `OMEGAB` | EOS omega A and B | — |
| `MW` | Molecular weight | g/mol |
| `TBOIL` | Normal boiling point | K |
| `VCRIT` | Critical volume | m³/kg-mole |
| `ZCRIT` | Critical Z-factor | — |
| `SSHIFT` | Volume translation (co-volume) | — |
| `PARACHOR` | Parachor | dyn/cm |
| `ZI` | Overall mole fractions | — |
| `BIC` / `BICS` | Binary interaction parameters (lower triangular) | — |
| `PEDERSEN` | Pedersen viscosity correlation flag | — |
| `SSHIFTS` | Volume translation at surface conditions | — |

The `BIC` block lists, for component `r` (1-based, `r = 1..n-1`), the `r`
interaction values against components `0..r-1`. The skill reconstructs the full
symmetric matrix with a zero diagonal.

### Adding water

Water is appended as the last component with the public PVTsim Peng-Robinson
water calibration. These constants match a PVTsim `*_water.e300` file:

| Parameter | Value |
| --- | --- |
| `TCRIT` | 647.096 K |
| `PCRIT` | 220.6 bar |
| `ACF` | 0.344 |
| `OMEGAA` | 0.42748 |
| `OMEGAB` | 0.07780 |
| `MW` | 18.0153 g/mol |
| `TBOIL` | 373.15 K |
| `VCRIT` | 0.056 m³/kg-mole |
| `ZCRIT` | 0.29159 |
| `SSHIFT` (volume shift) | 0.084004 |
| `PARACHOR` | 10.0 |
| `ZI` | 0.0 |
| `BIC` vs all components | 0.5 |
| `SSHIFTS` | 0.126143 |

NeqSim's `EclipseFluidReadWrite.addWaterToFluid` applies the same volume shift
(0.084004), parachor (10.0), and binary interaction parameter (0.5) and enables
the multiphase check, so the pure-Python path and the NeqSim path agree.

## Python Usage Pattern

### Pure-Python: add water to an E300 file

```python
from e300_fluid_io import add_water_to_e300_file, read_e300_file

# Read an E300 file (no NeqSim required)
fluid = read_e300_file("osebergfluid.e300")
print(fluid.names, fluid.ncomps)

# Add water and write a PVTsim-style *_water.e300 file
add_water_to_e300_file("osebergfluid.e300", "osebergfluid_water.e300")
```

### NeqSim bridge: E300 to fluid, fluid to E300

```python
from e300_fluid_io import (
    read_e300_to_neqsim,
    neqsim_add_water,
    write_neqsim_to_e300,
    neqsim_to_e300_string,
)

# Read an E300 file into a rigorous NeqSim fluid
fluid = read_e300_to_neqsim("osebergfluid.e300")
fluid.setMixingRule("classic")

# Or read and add water in one call (PVTsim water parameters)
wet = read_e300_to_neqsim("osebergfluid.e300", add_water=True, water_kij=0.5)

# Add water to an existing NeqSim fluid
neqsim_add_water(fluid, water_kij=0.5)

# Write a NeqSim fluid back to an E300 file
write_neqsim_to_e300(fluid, "exported.e300", reservoir_temp_c=110.0)

# Or render the E300 text directly
text = neqsim_to_e300_string(fluid, reservoir_temp_c=110.0)
```

The bridge functions raise a clear `RuntimeError` when the optional `neqsim`
Python package is not installed. The pure-Python functions always work.

## Validation Checklist

- [ ] `E300Fluid.validate()` returns an empty list (vectors match component count, BIC is square).
- [ ] Overall composition `ZI` sums to the expected basis before simulation.
- [ ] Water appears once as the last component after adding water.
- [ ] Water volume shift is 0.084004 and parachor is 10.0.
- [ ] Water binary interaction parameter is 0.5 (or the chosen `water_kij`) against all components.
- [ ] An E300 file written by this skill reloads in NeqSim without error.
- [ ] `setMixingRule("classic")` is called before NeqSim property calculations.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| `RuntimeError: NeqSim is not installed` | Bridge function used without NeqSim | Use the pure-Python functions, or `pip install neqsim` |
| Water added twice | `add_water` called on a fluid that already has H2O | The helper is idempotent; check `has_water()` |
| NeqSim properties return zero | Mixing rule not set | Call `fluid.setMixingRule("classic")` after reading |
| Vector length mismatch on write | A section was edited inconsistently | Run `E300Fluid.validate()` before writing |
| Wrong reservoir temperature in output | RTEMP defaulted to 100 °C | Pass `reservoir_temp_c` explicitly |

## Limitations

- The pure-Python writer emits one value per line and one BIC row per line. This
  is valid E300 that NeqSim reads back, but it is not byte-identical to a PVTsim
  Nova export.
- The skill does not characterize plus fractions, regress binary interaction
  parameters, or tune the equation of state.
- Water is added with the public PVTsim calibration only; project-specific water
  models require qualified data and review.
- The skill does not validate laboratory data or replace PVT specialist judgement.

## Related NeqSim Functionality

This skill wraps validated, rigorous NeqSim Java functionality that a qualified
engineer should use for design-grade work:

- `neqsim.thermo.util.readwrite.EclipseFluidReadWrite#read(String)` — read an E300 file into a NeqSim fluid.
- `neqsim.thermo.util.readwrite.EclipseFluidReadWrite#read(String, boolean, double)` — read an E300 file and add water.
- `neqsim.thermo.util.readwrite.EclipseFluidReadWrite#addWaterToFluid(SystemInterface, double)` — add water with the PVTsim water parameters.
- `neqsim.thermo.util.readwrite.EclipseFluidReadWrite#write(SystemInterface, String, double)` — write a NeqSim fluid to an E300 file.
- `neqsim.thermo.util.readwrite.EclipseFluidReadWrite#toE300String(SystemInterface, double)` — render a NeqSim fluid as E300 text.

In Python these classes are reachable through the `neqsim` package
(`from neqsim import jneqsim`).

## References

- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Skills Guide: https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
- Eclipse 300 / PVTsim Nova compositional EOS keyword documentation (vendor manuals).
