# Gas explosion and dispersion CFD study - report template

Fill every bracket from computed results (results.json), never by hand. A result without a mesh, verification and assumptions status is not reported.

## 0. Verdict (first page)

| Item | Entry |
|---|---|
| Readiness (`assess_explosion_readiness`) | not_ready / ready_screening / ready |
| Result status | SCREENING / VERIFIED-NOT-VALIDATED / VALIDATED |
| Headline numbers | peak overpressure and impulse at the governing panel, equivalent stoichiometric cloud (ESC), distance or load comparison with the design explosion load (DEL) |
| Use as design basis? | yes / no - and why |
| Blocking open points | the exact missing inputs, each with an owner |

## 1. Basis

1. Geometry: sources (drawings, line list, datasheets), obstacle count, volume blockage, projected area blockage, congestion variants, vent/confinement variants.
2. Release: NeqSim flash, hole sizes, rates, ambient-equilibrium vapour fraction, pseudo-source (diameter, velocity, thrust), directions, wind, ignition points.
3. Gas detection and shutdown: detector logic, response and isolation times, how they limit cloud size.
4. Standards: NORSOK Z-013 (clause, Annex F), GL0414 CFD guideline, company DEL document and revision.

## 2. Method

Combustion model, flame-wrinkling / burning-velocity law, turbulence model, obstacle sub-grid model, convection schemes (state the bounded scheme for b),
ignition kernel, time step control, solver and image version, run times.

## 3. Verification and validation

| Test | Reference | Result | Deviation | Status |
|---|---|---|---|---|
| Closed vessel, stoichiometric gas | adiabatic isochoric complete combustion (independent code) | | | PASS/FAIL |
| Laminar burning velocity | literature range | | | |
| Published congested rig (MERGE/EMERGE/SCOPE/CMR) | measured peak and impulse | | | not run = NOT VALIDATED |

## 4. Mesh study

Three levels with a constant refinement ratio: cells, h, metric, burned fraction at end, GCI, apparent order, monotonic? A metric that moves with
refinement is reported as an artefact, with its extrapolated value and band.

## 5. Dispersion results

Table per case: source, wind, direction, ESC and flammable volume at several times (ignition-time dependence), volume above UFL, cloud still growing at end of run?

## 6. Explosion results

Table per case: fill, ignition, congestion, vent, fuel; peak overpressure and impulse at panels and monitors, time of peak, flame progress at end.
Pressure-time figure, sensitivity figure, comparison with the DEL and with the multi-energy class screening (state the class the CFD implies).

## 7. Mitigation sensitivity

Venting, congestion, gas detection / ESD timing, deluge (qualitative unless modelled), with the change in peak and cloud size.

## 8. What the study decides and what it does not

State explicitly: handful of scenarios, not a probabilistic exceedance (Z-013 Annex F needs the full matrix); no buoyancy; no aerosol; rigid wall plane; etc.

## 9. Open points (per finding), hand-off, input package for the company CFD team

Each open point: the test that would close it, owner, effect on the result.
