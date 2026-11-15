---
name: neqsim-reservoir-material-balance
calculation_basis: "neqsim-java"
version: "0.1.0"
description: "Screen gas and oil reservoir in-place volumes with pressure-production material balance, including gas p/z, Havlena-Odeh, black-oil and volatile-oil fits, aquifer-support scenarios, uncertainty and identifiability checks. USE WHEN: an MBAL model, STOIIP/OOIP/GIIP estimate, pressure history match, lower-in-place-volume claim, gas-cap or water-drive evaluation is needed."
last_verified: "2026-11-15"
requires:
  python_packages: [numpy, pandas, jneqsim]
  java_packages: [neqsim]
  env: []
  network: []
---

# Reservoir Material-Balance Analysis

Use pressure and cumulative production to test an in-place-volume hypothesis. This is a tank-level
screening method, not a spatial reservoir simulator or a reserves classification.

## When to Use

- Estimate or reconcile gas initially in place (GIIP), original oil in place (OOIP), or total
  surface-component inventories from pressure and production history.
- Compare a prior volumetric estimate with a pressure-production material balance.
- Test depletion-drive, gas-cap, known-water-influx, or known-compressibility cases.
- Separate formations or pressure compartments before matching a field total.

For compositional gas-condensate depletion, produced composition, or wellstream forecasts, use
`neqsim-reservoir-history-match-forecast`. Use both workflows only when their fluid and volume bases
are explicitly reconciled.

## Inputs

- Dated static/average reservoir pressures, including test type, depth, unit, datum, source and
  correction provenance.
- Formation-allocated cumulative production and injection for oil, gas and water on one declared
  surface-volume basis.
- Initial and pressure-dependent PVT, initial pressure and temperature, and relevant rock/fluid
  compressibilities.
- Supported formation/tank boundaries, pressure communication evidence, and gas-cap/aquifer inputs
  where applicable.
- Prior in-place estimates and their date, range, volumetric/PVT basis and allocation assumptions.

## Outputs

- In-place volumes and units by tank and supported model case.
- Pressure/volume residuals, fit diagnostics and identifiability warnings.
- Cumulative production, injection, aquifer influx and drive contributions on a consistent basis.
- Sensitivity range, comparison with the prior estimate, data gaps and discriminating next evidence.

## Required Evidence

Before fitting, assemble one time-aligned history per candidate tank:

- Static or otherwise justified average reservoir pressure with date, wellbore, test type, gauge
  depth, pressure unit, datum, source, quality and correction method.
- Cumulative oil, gas and water produced and injected, on one declared surface-volume basis. Keep
  the formation allocation and its uncertainty; a field total is not automatically a formation
  history.
- PVT at initial conditions and at each pressure observation: pressure, Bo, Bg, Bw, Rs and Rv as
  applicable, with units, standard conditions and separator basis.
- Initial pressure, temperature, formation/water compressibility and saturation assumptions.
- Formation and pressure-compartment mapping, well completion intervals, shut-in/stabilization
  status, and evidence for or against pressure communication.
- The previous in-place estimate, estimate date, range, and the pore-volume, saturation, PVT and
  allocation basis used to calculate it.

Normalize pressures to absolute pressure and a common datum before matching. Preserve the raw
measurement and the correction alongside every normalized value. Do not mix flowing pressures with
static observations or treat a wellhead pressure as average tank pressure without a documented
conversion.

## Select the Model

| Reservoir/fluid case | NeqSim route | Important boundary |
|---|---|---|
| Dry or lean gas, closed tank, negligible water drive | `MaterialBalanceHistoryMatch.fitPzLine` | This is a p/z versus cumulative-production line fit. Check the pressure and Z basis, residuals and outliers; sigma clipping does not validate the data. |
| Conventional black-oil depletion or gas-cap drive | `OilMaterialBalance` | Build and inspect withdrawal and expansion terms before `fitDepletionDrive` or `fitGasCapDrive`. |
| Conventional black-oil water drive | `OilMaterialBalance.fitWaterDrive` | Requires an independently specified cumulative aquifer-influx history. It does not infer that history from pressure alone. |
| Initially oil or gas, with both solution gas Rs and vaporized oil Rv | `GeneralizedMaterialBalance` with `BlackOilPVTTable.Record` | Use one fixed surface basis and net cumulative produced-minus-injected components. The fitted residual is reservoir-volume balance, not pressure error. |
| Compositional gas condensate with changing produced composition | `neqsim-reservoir-history-match-forecast` | Use a tuned EOS and composition/yield observations; do not substitute a black-oil fit when liquid dropout and composition change matter. |

`OilMaterialBalance` uses the Havlena-Odeh balance
`F = N(Eo + m Eg + Efw) + We Bw`. Its depletion-drive and gas-cap regressions estimate OOIP
(surface oil volume); the water-drive regression takes known `We`. `GeneralizedMaterialBalance`
supports initially-oil, initially-gas, specified-gas-cap and joint oil/gas fits. It rejects
non-identifiable two-component fits by a scaled condition-number gate, but that gate is not a full
uncertainty interval.

## Engineering Method

1. **Freeze the basis.** Record standard conditions, surface-volume units, pressure datum, initial
   state, PVT source, rate allocation, and the date through which each history is final.
2. **Choose tank boundaries.** Split formations or compartments only when the pressure and
   completion evidence supports distinct inventories. Keep alternative tank maps when the evidence
   is ambiguous.
3. **Check closure and inventory.** Reconcile allocated field and well totals, net production versus
   injection, and formation-level allocation. A fitted inventory must not be smaller than the net
   component withdrawal it is required to contain.
4. **Build competing hypotheses.** Include closed depletion, supported aquifer, gas-cap, and
   compressibility cases only where their inputs are evidenced. Hold uncertain allocation and
   pressure corrections as explicit sensitivities, not hidden fit parameters.
5. **Fit and diagnose.** Report residuals by date, tank and observation source; retained/rejected
   pressure points; condition number or other identifiability warnings; bound hits; and sensitivity
   to tank split, PVT, allocation, compressibility and aquifer assumptions.
6. **Compare with the prior estimate.** Compare on the same initial date and surface basis. Reconcile
   differences back to measurable inputs and present ranges for each defensible model structure.
7. **Separate in-place from recoverable volumes.** Do not call a material-balance inventory a
   recoverable reserve or a forecast without a supported recovery and deliverability model.

## Python Usage Pattern

This is a basis-selection and result-interpretation workflow, not a generic runnable script. Use
capability discovery and verified NeqSim API signatures for the selected Java model. Keep data
preparation, unit normalization and plotting in a task notebook only when needed; validate the
calculation independently before reporting an in-place estimate.

## Validation Checklist

- Pressure observations are static/average values normalized to absolute pressure and a common
  datum with raw values retained.
- Production and injection are formation-allocated and reconciled on one surface-volume basis.
- The fitted inventory satisfies net component withdrawal and the selected PVT/model assumptions.
- Fit residuals, identifiability, bounds and sensitivity are reported; pressure fit alone is not
  treated as proof of a unique volume.
- The prior estimate comparison uses the same initial date and volume basis.

## Common Mistakes

- Inferring a lower in-place volume from pressure observations alone.
- Treating flowing pressure as average tank pressure or ignoring datum corrections.
- Fitting independent aquifers per formation and labeling them one shared aquifer.
- Comparing field-total production with a formation-level balance without validated allocation.
- Treating a material-balance inventory as recoverable reserves or a production forecast.

## Aquifer and Shared-Support Gate

Pressure decline by itself cannot distinguish a larger tank with weaker support from a smaller tank
with stronger support. Use measured aquifer pressure, water production/injection, pressure
communication, aquifer geometry and compressibility to constrain support. Fetkovich or
Van Everdingen-Hurst aquifer calculations are forward scenarios when their physical inputs are
specified; they do not establish aquifer size from pressure history alone.

For multiple formations that may share an aquifer, do not fit each formation with an independent
aquifer and present the results as one common-aquifer model. A shared support hypothesis needs one
consistent coupled balance and a documented allocation of influx to the tanks. If the selected
workflow cannot solve that coupled structure, report the alternative cases and the limitation, or
route the question to a reservoir simulator for a coupled evaluation.

## Output Interpretation

For every tank and case, report:

- Model type, tank boundaries and evidence tier for each input.
- Estimated in-place volume and units; fitted gas-cap ratio when applicable.
- Pressure/volume residuals and fit diagnostics, including identifiability or condition warnings.
- Cumulative production, injection, aquifer influx and drive contributions on the same basis.
- Sensitivity range and comparison with the previous estimate.
- Data gaps, unsupported assumptions, and the observation or test that would best discriminate
  between competing hypotheses.

## Limitations

### Stop Conditions

- No unambiguous initial PVT or surface-volume basis.
- Pressure points cannot be reconciled to a common datum, or are mainly flowing/non-stabilized.
- Formation-level production allocation is missing and materially changes the inferred volume.
- An aquifer or gas-cap case is being fitted without an independent constraint.
- A joint oil/gas fit is ill-conditioned, violates component inventory, or depends on a bound.
- Competing tank/support hypotheses fit within the observation uncertainty but imply different
  in-place volumes.

In these cases report the limitation and the next required evidence. Do not silently substitute a
default drive mechanism or report a single best-fit volume as a conclusion.

## Partner-Memo and Cross-Estimator QC Checklist

Lessons from a Tyrihans North memo QC (Nov 2026); apply when a balance feeds a partner or decision document:

- **Cross-check the tank with the native estimator.** Run the same pressures, PVT and net production through
  `GeneralizedMaterialBalance` (volume-residual estimator, `fitKnownGasCap` or `fitInitiallyGas`) next to your
  own pressure-misfit tank. Agreement within about 0.1 GSm3 for a closed tank confirms the implementation;
  differences that grow with water injection show an estimator effect, not an error.
- **Report aquifer as influx, not only volume.** Give pore volume, compressibility, and cumulative influx at the
  last pressure (`We = Waq*(cf+cw)*(pi-p)` is the infinite-productivity limit; `FetkovichAquifer` gives the finite
  productivity case). Partner aquifers quoted in MSm3 are comparable to Mrm3 only within the water compressibility.
- **Condition every aquifer bound on the water-support assumption** (for example, W-2 water to the tank or not);
  the acceptable aquifer range shrinks when injected water is credited to the tank.
- **State free gas versus total gas and the gas/oil split.** Free gas moves with the assumed gas fraction
  (about 0.27 GSm3 per 0.01 for a gas-cap/oil-rim tank); total gas (free plus dissolved) does not. Derive the
  fraction from the deck EQUIL contacts and state the OWC used.
- **One rock compressibility per formation, checked per case.** A table of results for two formations must say
  which cf each used; rerun the formation that used the other value.
- **Name the pressure basis per row** (number and tier of points, datum). A different estimator of the same
  formation may use a different pressure set; do not mix them in one sentence.
- **Initial pressure and datum:** quote pressure with its depth; test a partner initial pressure on your own
  pressures (fit RMSE and gas) before attributing a volume difference to it.
- **Scenario posterior.** Where pressure cannot fix aquifer or W-2 share, weight explicit scenarios with
  prior x exp(-chi2/2) (the `ReservoirHistoryEnsemble` rule), state the prior masses, and report lower-tail
  quantiles as scenario quantiles, not confidence intervals. The compositional `ReservoirHistoryEnsemble` itself
  needs measured component histories and a joint candidate set.

## References

- Havlena, D. and Odeh, A.S. (1963, 1964), material-balance analysis of volumetric and water-drive
  reservoirs.
- Walsh, M.P. (1995), generalized material balance for oil and gas reservoirs,
  doi:10.2118/95-01-07.
- Craft, B.C. and Hawkins, M.F., *Applied Petroleum Reservoir Engineering*.
