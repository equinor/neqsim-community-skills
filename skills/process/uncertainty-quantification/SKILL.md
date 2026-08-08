---
name: neqsim-uncertainty-quantification
version: "0.1.0"
description: "Monte Carlo uncertainty quantification, tornado sensitivity and global sensitivity analysis for NeqSim tasks. Supplies inverse-CDF marginals (uniform, triangular, normal, log-normal fitted from a stated P10/P90, deterministic), unit-hypercube samplers (seeded pseudo-random, Latin hypercube, Halton), a technical/economic model split that caches the expensive flowsheet stage so price and cost parameters never trigger a re-solve, linear-interpolation percentiles in the ascending p10<=p50<=p90 convention the task gate enforces, a scale-invariant split-half convergence check, a swing-ranked one-at-a-time tornado, optional SALib Saltelli/Sobol' and Morris backends that expose the interaction effects a tornado is blind to, an optional chaospy polynomial-chaos surrogate that reaches the same statistics in one to two orders of magnitude fewer model evaluations, and emission of the uncertainty block that the task report generator and CI gate consume. USE WHEN: a task must report P10/P50/P90, a tornado diagram or a probability of a negative outcome, a Monte Carlo loop wraps an expensive NeqSim simulation, parameters must be ranked before a sensitivity budget is committed, an interaction between uncertain inputs is suspected, or an existing uncertainty block must be audited for sample count, convergence and percentile convention."
last_verified: "2026-08-08"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Uncertainty Quantification

A Standard or Comprehensive NeqSim task must report P10/P50/P90 and a tornado
diagram. In practice that gets written from scratch in every notebook, and the
same four defects recur: sampling that clusters because it is plain
pseudo-random at n = 200, a Monte Carlo loop that re-solves the flowsheet for a
gas price that never touches it, no check that the run converged, and a tornado
presented as if it were a sensitivity analysis when it cannot see interaction.

This skill supplies the sampling, the statistics, the caching, the convergence
gate and the report block. It does not own the model — the task supplies that.

## When to Use

- A task must produce `uncertainty` for `results.json`: P10/P50/P90, mean,
  standard deviation, probability of a negative outcome, tornado.
- A Monte Carlo loop wraps an expensive NeqSim flowsheet and the evaluation
  budget is the binding constraint.
- Parameters must be screened before a sensitivity budget is committed.
- An interaction between uncertain inputs is suspected and a tornado is not
  enough.
- An existing uncertainty block must be audited: enough samples, converged,
  correct percentile convention?

## When *Not* to Use

- As an optimiser. Searching for the best setpoints is
  `neqsim-optimization-and-doe`; this skill propagates uncertainty through a
  fixed design.
- To invent input ranges. A distribution with no basis produces a precise
  answer to an arbitrary question — record where each range came from.
- For correlated inputs. Every marginal is sampled independently; correlation
  between, say, price and cost inflation is not represented.
- As a substitute for a risk register. A probability distribution on an output
  is not a hazard assessment.

## Inputs

| Input | Meaning |
| --- | --- |
| `parameters` | list of `Distribution` objects, each with `name`, `unit`, `kind` |
| `kind` | `"technical"` (drives the expensive stage) or `"economic"` (cheap stage only) |
| `model` | `f(values) -> float`, for a single-stage study |
| `technical` / `economic` | the two-stage split: `g(technical) -> intermediate`, `h(intermediate, economic) -> float` |
| `sampling_method` | `"lhs"` (default), `"random"`, or `"halton"` |
| `seed` | integer for reproducibility |
| `n` | sample count; at least 200 for a simulation-backed run |

## Outputs

| Output | Meaning |
| --- | --- |
| `StudyResult.summary` | count, mean, std, min, max, p10/p50/p90, standard error, drift, P(negative) |
| `StudyResult.cache_report` | technical/economic evaluations and cache hits |
| `UncertaintyStudy.tornado()` | swing-ranked `TornadoEntry` list |
| `UncertaintyReport.to_results_json()` | the `uncertainty` block |
| `UncertaintyReport.blockers()` | why the block may not be presented as converged |
| `backends.sobol_indices(...)` | first-order `S1` and total-order `ST` with confidence intervals |
| `backends.fit_polynomial_chaos(...)` | surrogate, mean, std, `S1`, evaluation count |

## Engineering Method

**1. Marginals separated from the sampler.** Every distribution exposes an
inverse CDF, and the sampler only produces points in the unit hypercube. One set
of parameter definitions therefore drives a pseudo-random run, a Latin-hypercube
run, a Halton run, and an optional SALib design without redefinition — and a
triangular input is never silently replaced by a uniform one because a sampler
wanted bounds.

**2. Latin hypercube by default.** At the sample counts a NeqSim-backed study
can afford (a few hundred), plain pseudo-random sampling leaves visible gaps in
the marginals. Latin hypercube places exactly one point per stratum in every
dimension, so the estimate of a percentile is far less sensitive to the seed.

**3. Technical / economic split.** The expensive stage is cached on its inputs:

$$
y = h\big(g(\mathbf{x}_\text{tech}),\; \mathbf{x}_\text{econ}\big)
$$

Where this genuinely pays is the **tornado**: every economic row sits at base
technical values, so four economic parameters cost one flowsheet solve instead
of eight. In the Monte Carlo itself a *continuous* technical parameter takes a
new value on every sample, so there is nothing to reuse — `cache_hits` will be
zero and the report says so rather than implying a saving that did not happen.

**4. Percentile convention.** `p10` is the 10th percentile, the *low* estimate,
so `p10 <= p50 <= p90` always holds — this is what the task gate enforces. It is
the opposite of the petroleum resource convention, where P10 is the optimistic
volume. The block states the convention explicitly; never flip the numbers to
match a habit.

**5. Convergence gate.** Drift of the median between the first and second half
of the run is reported as a percentage of the **P10-P90 spread**, not of the
median's own magnitude — an NPV distribution straddling zero would otherwise
report enormous drift for a perfectly converged run. Above 5 % of spread, the
percentiles are not quotable.

**6. Tornado ranks; Sobol' explains.** A one-at-a-time tornado moves one input
with the rest at base, so it measures only the main effect along a single line.
Variance-based Sobol' indices split the output variance into first-order `S1`
and total-order `ST`; a parameter with `ST >> S1` matters *only through
interaction* and a tornado will rank it as irrelevant. The bundled Ishigami
example demonstrates exactly that failure.

**7. Polynomial chaos when evaluations are the constraint.** A PCE surrogate
fitted on a designed sample reproduces the mean, variance and Sobol' indices
from the coefficients. In the bundled example it reaches the analytical Ishigami
mean of 3.5 in 168 evaluations, against 5120 for the Saltelli design — the
argument for using it when each evaluation is a flowsheet solve.

## Python Usage Pattern

Monte Carlo with a technical/economic split:

```python
from uncertainty_quantification import Triangular, UncertaintyReport, UncertaintyStudy

parameters = [
    Triangular(name="GIP", unit="GSm3", low=105.0, base_value=135.0, high=169.0),
    Triangular(name="Gas price", unit="NOK/Sm3", low=0.8, base_value=1.5,
               high=2.5, kind="economic"),
]

def technical(values):            # the expensive NeqSim stage
    process.getAutomation().setVariableValue("Feed.flowRate", values["GIP"], "kg/hr")
    process.run()
    return {"production": read_production(process)}

def economic(intermediate, values):
    return npv(intermediate["production"], values["Gas price"])

study = UncertaintyStudy(
    parameters=parameters, output_name="NPV after tax", output_unit="MNOK",
    sampling_method="lhs", seed=42, technical=technical, economic=economic,
    simulation_engine="NeqSim (SRK EOS, ProcessModel)",
)
result = study.run(300, skip_failures=True)

report = UncertaintyReport(
    parameters=parameters, result=result, output_name="NPV after tax",
    output_unit="MNOK", tornado=study.tornado(),
    simulation_engine=study.simulation_engine,
)
assert report.blockers() == [], report.blockers()
results["uncertainty"] = report.to_results_json()
```

Global sensitivity when a tornado is not enough:

```python
from uncertainty_quantification.backends import (
    salib_available, saltelli_samples, sobol_indices,
)

if salib_available():
    design = saltelli_samples(parameters, 256, seed=42)   # 256 * (n_vars + 2) runs
    outputs = [study.evaluate(point) for point in design]
    report.sensitivity = sobol_indices(parameters, outputs)
```

Surrogate route when each evaluation is a flowsheet solve:

```python
from uncertainty_quantification.backends import fit_polynomial_chaos, sample_surrogate

fit = fit_polynomial_chaos(parameters, study.evaluate, order=3, seed=42)
sample = sample_surrogate(fit, 100000)      # percentiles from a cheap sample
```

## Validation Checklist

- [ ] At least 200 samples for a simulation-backed run (1000 for a correlation
      or a surrogate).
- [ ] `report.blockers()` is empty, or every entry is explained in the report.
- [ ] Median drift is below 5 % of the P10-P90 spread.
- [ ] `p10 <= p50 <= p90`, and the report states the convention.
- [ ] Every input range has a stated basis, recorded next to the parameter.
- [ ] `seed` and `sampling_method` are reported so the run is reproducible.
- [ ] Failed evaluations are counted and disclosed, not silently dropped.
- [ ] The tornado is labelled as a main-effect ranking, not a full sensitivity
      analysis, unless Sobol' indices were computed.
- [ ] The emitted block passes `python devtools/validate_task_results.py <task>`.
- [ ] A tornado figure and an output histogram or CDF accompany the table.

## Common Mistakes

- **Flipping the percentile convention.** Quoting a petroleum P10 (optimistic)
  in a block the gate reads as the 10th percentile inverts the whole story.
- **Running Monte Carlo on a simplified Python correlation** while a NeqSim
  class exists for the calculation. The task rules require the real model;
  the staged split and the surrogate backend exist so it stays affordable.
- **Treating the tornado as a sensitivity analysis.** It is a main-effect
  ranking along one line through base. Interactions are invisible to it.
- **Too few samples.** A 50-sample P90 is noise; the convergence check exists to
  make that visible before it reaches a report.
- **Expecting the cache to help a continuous technical parameter.** It cannot —
  every sample is a new state. Tag a parameter `economic` only when it truly
  does not enter the expensive stage.
- **Silently dropping non-converged runs.** Use `skip_failures=True` so they are
  counted and reported.
- **Sampling correlated inputs independently** and presenting the resulting
  spread as the real uncertainty.

## Limitations

- Marginals are sampled independently; no copula or correlation matrix.
- Only continuous marginals are provided (plus a deterministic placeholder);
  discrete and categorical uncertainty is not modelled.
- The tornado is one-at-a-time and cannot resolve interaction; use the SALib
  backend for that.
- Halton degrades above roughly ten dimensions because of correlation between
  the higher prime bases.
- The split-half drift is a screening convergence indicator, not a formal
  Monte Carlo error bound; the standard error of the mean is reported alongside.
- Polynomial chaos assumes a smooth response; a discontinuity (a phase change, a
  constraint becoming active) breaks the surrogate, and the fit will not warn.

## Related NeqSim Functionality

- `neqsim.process.automation.ProcessAutomation#evaluateBatchJson` scores a list
  of setpoint candidates, on a `ProcessSystem.copy()` per thread when
  `maxParallel > 1` — the natural way to evaluate a Monte Carlo or Saltelli
  design without disturbing the live model.
- `neqsim.process.automation.ProcessAutomation#evaluate` is the single-sample
  form: it applies setpoints, runs to convergence and returns a `feasible` flag,
  so a non-converged sample can be counted with `skip_failures=True`.
- `neqsim.process.util.optimizer.MonteCarloSimulator` and
  `neqsim.process.fielddevelopment.evaluation.MonteCarloRunner` are NeqSim's own
  flowsheet- and field-level Monte Carlo drivers;
  `neqsim.statistics.montecarlosimulation.MonteCarloSimulation` covers
  parameter-fitting uncertainty. Use them when the study stays inside Java; use
  this skill when the loop is in Python, when the sampler or the convergence gate
  matters, or when SALib/chaospy are needed.
- `neqsim.util.agentic.TaskResultValidator` validates the emitted `uncertainty`
  block in Java; `devtools/validate_task_results.py` is the equivalent CI gate,
  and both enforce `p10 <= p50 <= p90`.

## Related Skills

- `neqsim-benchmark-reference-data` — validate the model *before* propagating
  uncertainty through it. An unbenchmarked model produces a precise distribution
  around an unverified answer.
- `neqsim-optimization-and-doe` — the search counterpart. Optimise the design,
  then propagate uncertainty through the chosen design with this skill.
- `neqsim-asset-value-npv-screening`, `neqsim-capex-opex-screening`,
  `neqsim-economy-basis-screening` — the usual economic models placed in the
  `economic` stage.
- `neqsim-reservoir-depletion-screening` — the usual `technical` stage for a
  field-development study.
- `neqsim-reliability-data-screening` — availability feeding a production
  profile as an uncertain input.

## References

- Saltelli, A., Ratto, M., Andres, T., Campolongo, F., Cariboni, J., Gatelli, D.,
  Saisana, M., & Tarantola, S. (2008). *Global Sensitivity Analysis: The Primer*.
  Wiley.
- Sobol', I. M. (2001). Global sensitivity indices for nonlinear mathematical
  models and their Monte Carlo estimates. *Mathematics and Computers in
  Simulation*, 55(1-3), 271-280.
- Morris, M. D. (1991). Factorial sampling plans for preliminary computational
  experiments. *Technometrics*, 33(2), 161-174.
- McKay, M. D., Beckman, R. J., & Conover, W. J. (1979). A comparison of three
  methods for selecting values of input variables in the analysis of output from
  a computer code. *Technometrics*, 21(2), 239-245.
- Halton, J. H. (1960). On the efficiency of certain quasi-random sequences of
  points in evaluating multi-dimensional integrals. *Numerische Mathematik*,
  2(1), 84-90.
- Xiu, D., & Karniadakis, G. E. (2002). The Wiener-Askey polynomial chaos for
  stochastic differential equations. *SIAM Journal on Scientific Computing*,
  24(2), 619-644.
- Herman, J., & Usher, W. (2017). SALib: an open-source Python library for
  sensitivity analysis. *Journal of Open Source Software*, 2(9), 97.
- Feinberg, J., & Langtangen, H. P. (2015). Chaospy: an open source tool for
  designing methods of uncertainty quantification. *Journal of Computational
  Science*, 11, 46-57.
- Ishigami, T., & Homma, T. (1990). An importance quantification technique in
  uncertainty analysis for computer models. *Proceedings of ISUMA '90*, 398-403.
- ISO 31000:2018, *Risk management - Guidelines* — the risk register that an
  uncertainty distribution supports but does not replace.
- SPE-PRMS (2018), *Petroleum Resources Management System* — the resource
  convention in which P10 is the high estimate.
