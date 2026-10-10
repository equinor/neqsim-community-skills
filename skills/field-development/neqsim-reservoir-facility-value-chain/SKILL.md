---
name: neqsim-reservoir-facility-value-chain
calculation_basis: "screening"
version: "0.1.0"
description: "History-match and forecast a gas chain from reservoir to export: p/z tank from shut-in wellhead pressure, well deliverability, facility capacity from process-model sweeps, separation pressure at the supply/capacity crossing, multi-field export coupling, scenarios, P10/P90. USE WHEN: linking reservoir depletion to a platform or export system, history matching, finding whether wells or facility limit production, or valuing compression and well levers."
last_verified: "2026-10-07"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Reservoir-to-Facility Gas Value Chain

Screening workflow that couples a reservoir tank, well deliverability and a facility capacity curve,
so one model answers "who limits production now, and when does that change?". It was built for the
Troll A/B/C to Kollsnes chain (Troll East, Troll West gas province, Troll B and C oil rims) and is
field-agnostic. Use NeqSim process models (ProcessSystem, ProcessModel) for the facility numbers and
NeqSim `SimpleReservoir` or OPM Flow when a 3D reservoir model exists; this skill is the fast layer
between them.

## Method and classes

| Step | Python (this skill) | NeqSim Java (`neqsim.process.fielddevelopment.integrated`) |
|------|---------------------|-------------------------------------------------------------|
| Shut-in WHP to reservoir pressure | `static_bottomhole_pressure` | `MaterialBalanceHistoryMatch.staticBottomholePressure` |
| p/z line, GIIP, outlier rejection | `fit_pz_line` | `MaterialBalanceHistoryMatch.fitPzLine` |
| Real-gas p/z tank | `GasTank` | `RealGasMaterialBalanceDrive` + `DranchukAbouKassemZ` |
| Well law q = C (pr^2 - pwh^2)^n | `RSDeliverability.fit` | `RawlinsSchellhardtFit`, `WellDeliverabilityCurve.fromRawlinsSchellhardt` |
| Facility capacity from sweep | `capacity_from_sweep`, `PressureCapacityCurve` | `SupplyCapacityBalance.PressureCapacityCurve` |
| Best separation pressure | `maximise_rate` | `SupplyCapacityBalance.maximiseRate` |

## Workflow

1. **Data.** Monthly allocated volumes per wellbore and a daily sample (a few days every 6 months) with
   WHP, choke, on-stream hours. Pull per year with retries and check month coverage per facility:
   a 5-year query window can time out and silently return zero rows.
2. **Tank.** Use shut-in WHP (on-stream hours = 0, WHP above ~20 barg, per-window maximum or upper
   quartile) as the pressure proxy. Convert with the static column, fit p/z against cumulative gas,
   reject outliers (single-well, recently shut-in). Check that the intercept is a sane initial pressure
   and that two compartments with the same gas give similar p/z_i.
3. **Wells.** Fit the Rawlins-Schellhardt law on rows with the choke wide open only. Early-life rates are
   choke-controlled and give nonsense (negative quadratic term, R2 below 0). Keep n between 0.5 and 1.0;
   a short window can return n above 1, so fix n from a longer-record neighbour and refit C. Always
   hold out the latest 2-3 years.
4. **Equivalent wells.** Wells on stream = sum of on-stream hours / (24 x days in month). Do not use the
   well count from the register; subsea templates ramp up and wells cycle.
5. **Facility.** Run the platform process model over a throughput grid at several separation pressures
   (`throughput_sweep`). Capacity is where first-constraint utilisation reaches 1.0
   (`capacity_from_sweep`). Utilisation above 1.0 at every rate means a head or speed limit that does
   not depend on flow, so that pressure is below the facility floor. Scale capacity with polytropic
   head when the discharge or export pressure changes.
6. **Balance.** Wellhead pressure is the separation pressure plus a flowline drop that scales with
   rate squared. Solve `q = rate(Ps + dp (q/q0)^2)` by bisection (`flow_balance`); fixed-point iteration
   oscillates and can collapse to zero. Choose Ps with `maximise_rate`; the binding side (SUPPLY or
   FACILITY) is the headline result, per month.
7. **Export coupling.** Several fields feeding one export line raise the discharge pressure through
   P_man^2 = P_arr^2 + K q_total^2 (K from one measured point). The arrival pressure is an input;
   the receiving terminal is not modelled unless asked.
8. **Scenarios and uncertainty.** Fixed versus optimised Ps, extra low-pressure compression (extra
   capacity and a lower Ps floor), extra wells, capacity upgrades. Bootstrap the p/z points and refit
   (p/z_i and GIIP jointly), sample the deliverability exponent, well performance and capacity.

## Traps (each cost a failed run)

- **Pressure is a difference of two large numbers.** Moving GIIP by 8 % with p/z_i fixed put the
  present reservoir pressure at the wellhead pressure and the calibration became complex. Sample
  (p/z_i, GIIP) together from a bootstrap of the data, never independently.
- Oil-rim shut-in WHP is an index, not an absolute pressure (liquid column); report it as such and
  label the fitted GIIP "effective".
- Allocated gas of oil-rim wells is largely gas-cap gas; model it by drawdown scaling against the gas-cap
  pressure, not by GOR times oil.
- Month 0 of a pull is usually partial. Exclude the current month from rates and totals.
- Hindcast honestly: tank fitted to 2020, deliverability trained to 2023, tested 2024-2026. Report the
  bias per year; monthly errors are dominated by outages that on-stream hours do not capture.
- **Comparing options (a well swap, a tie-back, a host change):** (1) put every option on one calendar
  - a surrogate that starts both routes in the same year hides the years a template delays the gas
  (it flipped a separate-compartment NPV from -0.5 to -1.0 GNOK). (2) Decompose a bundled proposal
  into its parts (an extra well on a shared tank is acceleration worth about +1 GNOK; the tie-back
  that carries it can cost about -1 GNOK) and value each alone; the sum hides which part pays.
  (3) A well-count cap on "extra wells" must be read against the base project's own wells; a cap of a
  few MSm3/d silently removes the whole project. Give capacity as MSm3/d for all wells at that host,
  sized to the planned wells. (4) Check that the stated base case and the code agree (a notes table
  said f = 0.8 while the headline run used f = 1.0); run both and say which one the headline uses.
  (5) Check a flowline dP assumption against a real hydraulic run at the actual well rate and host
  pressure. For a 320 m riser in wet gas the gas-only head is about 1 bar, but Beggs and Brill adds
  2-3 bar of condensate holdup; treat that as an upper bound and cross-check with OLGA.

## Validation

Run `python -m pytest` in the skill folder. For a real study, validate the tank against held-out
shut-in pressures, the wells against a hold-out period, and the facility curve against the process
model at two operating points.

## Related

`neqsim-integrated-production-and-lifecycle`, `neqsim-capacity-and-utilization-analysis`,
`neqsim-production-optimization`, `neqsim-reservoir-model-builder`, `neqsim-near-well-and-injectivity`,
`neqsim-ncs-value-chain-optimization`, `neqsim-optimization-and-doe`.
