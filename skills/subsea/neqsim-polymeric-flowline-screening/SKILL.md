---
name: neqsim-polymeric-flowline-screening
calculation_basis: "screening"
version: "1.0.0"
description: "Educational screening of thermoplastic (polymeric) subsea flowlines: hoop pressure from a vendor table or thin-wall relation, external collapse, gas permeation against annulus vent capacity, steady arrival temperature against bare steel, and bend radius from a strain limit; missing evidence is reported as data gaps. USE WHEN: a tie-back concept considers polymeric or reinforced thermoplastic flowlines instead of steel or flexibles and needs a first screen before vendor qualification."
last_verified: "2026-11-20"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Polymeric Flowline Screening

Polymeric (thermoplastic) flowlines promise lower material cost, no corrosion,
spoolable installation and good insulation. The same properties create the checks
that decide whether the idea survives: a polymer wall is weak in hoop strength
without reinforcement, loses strength and stiffness with temperature, creeps under
sustained load, collapses under external pressure when the line is empty, and lets
gases such as CO2, H2S and methane permeate into the annulus.

This skill runs those first-pass checks in one place and keeps the evidence honest.
It carries no material database. Every strength, modulus, permeability and design
factor is an input from the manufacturer or a qualification report; anything not
supplied is returned as a *data gap*, not as a pass.

## When to Use

- A tie-back or flowline concept compares polymeric, steel and flexible options
  and needs a quick pressure, temperature, depth and thermal screen.
- A candidate polymer grade and wall must be tested against an operating case.
- Permeation of acid gas or hydrocarbon through the wall has to be compared with
  the annulus venting capacity.
- The insulation benefit of a low-conductivity wall needs a number against bare
  steel of the same size.

## When *Not* to Use

- As a qualification or design to a pipe standard. Long-term strength, creep,
  ageing, rapid gas decompression, fatigue and fittings are qualification topics.
- For reinforced pipe with proprietary layers except through a vendor rating
  table; this skill does not model the reinforcement.
- For cooldown and restart; only steady-state arrival temperature is computed.
- With confidential vendor data in a public workspace.

## Inputs

| Input | Meaning |
|---|---|
| `PolymerGrade` | `max_temperature_c`, `long_term_strength_mpa` and `modulus_mpa` tables vs C, `conductivity_w_mk`, `poisson` |
| `PolymerPipe` | `outer_diameter_m`, `wall_m`, `length_m`, optional `pressure_rating_bar` vendor table vs C |
| `OperatingCase` | pressure, temperature, ambient, mass flow, cp, water depth, outer film, optional bend radius, minimum arrival temperature, annulus vent capacity |
| `DesignBasis` | `hoop_design_factor`, `collapse_safety_factor`, optional `allowable_bending_strain` |
| `Permeant` | `partial_pressure_bar`, `permeability_mol_m_s_pa` at a reference temperature, `activation_energy_kj_mol` |

## Outputs

| Output | Contents |
|---|---|
| `ScreeningResult.checks` | `temperature`, `hoop_pressure`, `collapse`, `bend_radius`, `arrival_temperature`, `permeation`, each `pass`, `fail` or `data_gap` with value, limit and utilisation |
| `ScreeningResult.thermal` | Radial resistance, outlet temperature, heat loss, bare-steel outlet for comparison |
| `ScreeningResult.permeation` | Rate per species in Nm3/day per km and per line |
| `overall` | `fail` if any check fails, `incomplete` if only data gaps remain, else `pass` |
| `data_gaps`, `warnings` | Evidence a reviewer must close, and consistency warnings |

## Engineering Method

**Hoop pressure.** With a vendor rating table the allowable pressure is read at
the operating temperature. Without it a thin-wall relation (ISO 12162 style) is
used: `P = 2 sigma t / (D - t)` with `sigma = long-term strength(T) x design factor`.
A table that does not cover the operating temperature is reported as a data gap
rather than extrapolated silently.

**External collapse.** The long-ring elastic collapse pressure is
`Pc = 2E / (1 - nu^2) (t / Dm)^3` with `Dm = D - t` and the temperature-dependent
modulus, divided by the collapse safety factor. The net external pressure is
seawater head minus the internal pressure assumed present (default empty line,
the conservative case during depressurisation or installation).

**Permeation.** Steady permeation through a cylindrical wall,
`Q' = 2 pi Pe dp / ln(Do / Di)`, with the permeability corrected from its
reference temperature by an Arrhenius term and converted to Nm3/day per km.
The sum over species is compared with the supplied annulus vent capacity.

**Thermal.** Radial resistance `R' = ln(Do/Di)/(2 pi k) + 1/(pi Do h_out)` gives
outlet temperature `T_out = T_amb + (T_in - T_amb) exp(-L / (m cp R'))`. The same
formula with steel conductivity gives a bare-steel reference, which isolates the
effect of the polymer wall.

**Bend radius.** Minimum radius from a strain limit, `R_min = D / (2 eps)`.

**Evidence discipline.** A check that lacks its inputs returns `data_gap`, and the
overall verdict becomes `incomplete`, never `pass`.

## Python Usage Pattern

```python
from polymeric_flowline_screening import (
    DesignBasis, OperatingCase, Permeant, PolymerGrade, PolymerPipe, screen,
)

grade = PolymerGrade(
    name="vendor-grade",                     # all values from the vendor datasheet
    max_temperature_c=90.0,
    long_term_strength_mpa=((20.0, 12.0), (80.0, 6.0)),
    modulus_mpa=((20.0, 800.0), (80.0, 400.0)),
    conductivity_w_mk=0.4,
)
pipe = PolymerPipe(
    outer_diameter_m=0.25, wall_m=0.03, length_m=8000.0, polymer=grade,
    pressure_rating_bar=((20.0, 300.0), (80.0, 200.0)),
)
case = OperatingCase(
    internal_pressure_bar=120.0, temperature_c=60.0, ambient_c=5.0,
    mass_flow_kg_s=30.0, fluid_cp_j_kgk=2400.0, water_depth_m=350.0,
    collapse_internal_pressure_bar=0.0,
    minimum_arrival_temperature_c=20.0,
    annulus_vent_capacity_nm3_d_km=500.0,
)
basis = DesignBasis(hoop_design_factor=0.5, collapse_safety_factor=2.0)
result = screen(pipe, case, basis, [Permeant("CO2", 8.0, 2e-15, 20.0, 30.0)])

print(result.overall, result.data_gaps)
for name, check in result.checks.items():
    print(name, check.status, check.utilisation)
print(result.thermal.outlet_temperature_c, result.thermal.steel_outlet_temperature_c)
```

## Validation Checklist

- Strength, modulus, permeability and activation energy trace to a datasheet or
  qualification report, and the modulus is the long-term (creep) value.
- Tables cover the operating temperature range; `data_gaps` has no extrapolation
  entry.
- The collapse case matches the worst credible internal pressure (empty line).
- The design factors come from the governing code or vendor, not from this skill.
- Permeation species and partial pressures match the produced fluid composition.
- `overall` is `pass` only when `data_gaps` is empty, or the gaps are accepted in
  writing.
- Thermal result is compared with a NeqSim thermal-hydraulic model before any
  flow-assurance conclusion.

## Common Mistakes

- Using short-term modulus or strength for a long-term collapse or hoop check.
- Reading hoop capacity at ambient temperature for a hot line.
- Treating a missing permeability as zero.
- Judging acid-gas suitability from total pressure instead of partial pressure.
- Using a homogeneous-wall hoop relation for a reinforced pipe whose capacity is
  in the reinforcement.
- Comparing arrival temperature without the same flow rate and ambient for steel.

## Limitations

- Screening only; it is not a qualification and does not establish compliance.
- No creep rupture, ageing, rapid gas decompression, fatigue, ovality or
  buckling-under-compression models.
- Collapse is for a long unsupported ring; no ovality knock-down or liner/support
  interaction.
- Steady-state thermal only; no cooldown, restart or hydrate analysis.
- Permeation assumes a constant partial-pressure difference and a single-layer wall.
- No material database; all data is caller-supplied and unverified.

## References

- NeqSim: https://github.com/equinor/neqsim
- NeqSim Community Skills: https://github.com/equinor/neqsim-community-skills
- Companion skills: `neqsim-flow-assurance`, `neqsim-umbilical-design`,
  `neqsim-pipeline-survey-processing`
- Public references for the downstream work: ISO 12162 (thermoplastic pipe
  classification and design coefficient), API 15S and API 17J/17B (reinforced
  thermoplastic and unbonded flexible pipe), DNV-ST-F119 (thermoplastic composite
  pipes).
