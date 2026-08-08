# Uncertainty Quantification

Monte Carlo uncertainty quantification, tornado sensitivity, and optional global
sensitivity analysis for NeqSim tasks.

P10/P50/P90 and a tornado diagram are mandatory for Standard and Comprehensive
tasks, but they are usually re-coded in every notebook: hand-written triangular
sampling, an ad-hoc percentile, a one-at-a-time tornado that re-runs the whole
flowsheet for parameters that never touch it. This skill supplies the sampling,
the statistics, the convergence check, the technical/economic caching, and the
`uncertainty` block that the task report generator and CI gate consume — with
SALib and chaospy as optional backends for what a tornado cannot do.

## Install

```bash
python -m pip install -e skills/process/uncertainty-quantification
```

Optional backends:

```bash
python -m pip install SALib      # Saltelli sampling, Sobol' and Morris indices
python -m pip install chaospy    # polynomial chaos surrogate
```

## Run Examples

```bash
python skills/process/uncertainty-quantification/examples/monte_carlo_npv_study.py
python skills/process/uncertainty-quantification/examples/global_sensitivity_with_salib.py
```

The second example prints install hints and exits cleanly when the optional
backends are absent.

## Run Tests

```bash
python -m pytest skills/process/uncertainty-quantification/tests
```

## Public Scope

All methods are standard, openly published techniques: inverse-CDF sampling,
Latin hypercube, Halton sequences, linear-interpolation percentiles, one-at-a-time
tornado, Saltelli/Sobol' and Morris via SALib, polynomial chaos via chaospy. No
proprietary cost models, price forecasts, or internal acceptance criteria are
included. Sample-count minimums are the public NeqSim task-workflow rules, not
project acceptance criteria.
