---
name: neqsim-reservoir-souring-correlation
calculation_basis: "screening"
version: "0.1.0"
description: "Educational reservoir souring screening: seawater fraction from tracers, automatic per-well H2S-versus-seawater-fraction correlations updated from new data, and a substrate-limited mixing-zone H2S bound. USE WHEN: a task asks how well or produced-water H2S develops with seawater breakthrough, needs per-well H2S correlations for a production model, or an upper bound on biogenic souring."
last_verified: "2026-10-26"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Reservoir Souring Correlation

Reservoir souring is biogenic H2S from sulfate-reducing microorganisms: seawater injected for pressure support brings sulfate, formation water and oil bring volatile fatty acids (VFA) as electron donors, and where the two mix at suitable temperature the sulfate is reduced to H2S. The produced H2S then rises with seawater breakthrough. This skill gives the quick, transparent tools: seawater fraction per well, a fitted correlation per well, and a physical upper bound to sanity-check it.

Combine it with `neqsim-h2s-phase-partitioning`, which converts the measured separator gas H2S into wellstream H2S before fitting.

## When to Use

- Per well: H2S versus seawater fraction correlation that a production model, allocation tool or optimiser can call.
- Keeping those correlations current as new H2S measurements and water analyses come in (refit, forgetting of old data, drift warnings).
- Judging whether a measured H2S is physically possible: sulfate balance and mixing-zone bound.
- Screening mitigation: sulfate removal on the injected water, nitrate treatment, or a thermal cutoff in hot zones.

## Inputs

- Paired time series per well: seawater fraction `f_sw` (0 to 1) and H2S (wellstream mol-ppm from the partitioning skill, or gas ppmv, or produced-water mg/L; the correlation carries a `units` label and does not convert).
- Tracer data for `f_sw`: produced-water Cl, Mg, Br (conservative) with formation and seawater end members. Do not use sulfate or barium.
- For the bound: injected sulfate (mg/L), formation-water VFA as acetate-equivalent (mg/L), mixing-zone temperature, reaction efficiency, reservoir sink fraction, mitigation factor.

## Outputs

- `seawater_fraction_from_tracer` / `seawater_fraction_multi_tracer` (fraction plus residual that flags a non-conservative tracer).
- `Correlation`: model, parameters, `n`, RMSE, R2, valid `f_sw` range, AICc, warnings, `predict(f)`; JSON registry per well through `save_registry` / `load_registry`.
- `update_correlation(previous, ...)`: refit, optional exponential forgetting, warnings when the model family changes or the prediction at the latest `f_sw` moves more than 25 percent.
- `mixing_zone_h2s_mg_l`, `sulfate_balance_h2s_mg_l`, rate helpers.

## Engineering Method

1. Seawater fraction by two end-member mixing, `f = (c - c_fw) / (c_sw - c_fw)`, clipped to 0 to 1; several tracers are combined with contrast weights and the residual reported.
2. Candidate models: `linear` (a f + b), `power` (a f^n), `saturating` (a f / (1 + k f)), `threshold` (a max(f - f0, 0), a breakthrough delay), `mixing_zone` (a min(f/f*, (1-f)/(1-f*)), a peak). Nonlinear parameters by grid search, linear ones by least squares, best by AICc. At least five points per well.
3. Update by refit on the newest data with optional half-life weighting; compare with the previous correlation and warn on change.
4. Bound: `H2S <= min(0.355 SO4, 0.577 donor) x efficiency x (1 - sink) x mitigation x thermal`, with `SO4 = f SO4_sw`, `donor = (1 - f) VFA_fw` and a logistic thermal factor around about 80 C. Biogenic H2S stoichiometry: 34.08/96.06 mg H2S per mg sulfate; 34.08/59.04 per mg acetate.

## Python Usage Pattern

```python
from reservoir_souring import (seawater_fraction_from_tracer, fit_well_correlation, update_correlation,
                               save_registry, mixing_zone_h2s_mg_l)

f = [seawater_fraction_from_tracer(cl, 30000.0, 19000.0) for cl in cl_series]
corr = fit_well_correlation("A-12", f, h2s_wellstream_ppmv, units="ppmv")
print(corr.model, corr.params, corr.r2, corr.warnings, corr.predict(0.4))
corr = update_correlation(corr, "A-12", f_new, h2s_new, half_life_points=20)
save_registry([corr], "h2s_correlations.json")
bound = mixing_zone_h2s_mg_l(0.4, sulfate_sw_mg_l=2700.0, donor_fw_mg_l=300.0, temperature_c=70.0)
```

## Validation Checklist

- [ ] `f_sw` from a conservative tracer, with end members documented and the residual of a multi-tracer fit small.
- [ ] H2S series on one consistent basis (wellstream, gas or water) and one unit; no mixing of bases in one fit.
- [ ] Time alignment: H2S sample, water analysis and rate allocation from the same period.
- [ ] At least five points, and a spread of `f_sw`; check `f_min` and `f_max` and do not extrapolate far beyond them.
- [ ] Correlation prediction does not exceed the mixing-zone bound by a large margin (if it does, review data, sink and end members).
- [ ] Wells with no breakthrough yet are reported as `threshold` or low-confidence, not forced to a trend.
- [ ] Update warnings reviewed by a person before the correlation is used downstream.

## Limitations
- Empirical: a correlation is a fit, not a mechanism. Changes in injection water treatment (sulfate removal, nitrate, biocide), rate, temperature front or reservoir sink invalidate history.
- The mixing-zone bound is substrate limited and ignores kinetics, microbial community, pH, and re-oxidation; it is an upper bound only.
- Thermal cutoff is a logistic screen, not a measured population limit; cooled regions around injectors extend the active zone.
- No reservoir transport: use a reservoir simulator for front timing, streamlines and sweep.
- Partitioning of H2S between oil, gas and water in the reservoir and wellbore is not modelled here.

## Common Mistakes

- Using sulfate or barium as a mixing tracer (both are consumed or precipitated).
- Fitting gas ppmv in one period and wellstream ppmv in another to the same correlation.
- Letting AICc pick a complex model on a handful of points; check `n` and the warnings.
- Extrapolating a linear fit to full seawater cut when the mixing-zone bound turns over.
- Hiding a regime change by forgetting too aggressively; keep the old registry entry for audit.

## References

- Reservoir souring literature on mixing-zone and thermal-cutoff models (see the method notes above) and the field's measured H2S history.
- Companion skill `neqsim-h2s-phase-partitioning` for separator-gas to wellstream conversion.
