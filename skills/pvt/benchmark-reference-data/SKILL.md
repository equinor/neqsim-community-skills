---
name: neqsim-benchmark-reference-data
version: "0.1.0"
description: "Turn the mandatory benchmark-validation step of a NeqSim task into a reproducible, source-traceable comparison. Supplies a registry of independent reference sources with authority tiers, validated ranges and stated uncertainties (IAPWS-95, IAPWS-IF97, Span-Wagner CO2, Setzmann-Wagner methane, Span nitrogen, Bucker-Wagner ethane, Lemmon propane, GERG-2008, CoolProp HEOS, NIST WebBook), an offline anchor table of published critical points, triple points, boiling points and one ambient liquid density that runs with no optional dependency and no network, an optional CoolProp backend for reference values at any state, and a comparison layer that grades PASS/WARN/FAIL, rejects a reference that does not outrank the model basis, records whether the deviation is inside the reference's own uncertainty, enforces the three-point minimum, and emits the exact benchmark_validation block that the task report generator and CI gate consume. USE WHEN: a task must validate NeqSim output against independent reference data, a benchmark notebook is being written, a benchmark_validation block must be produced for results.json, a reported deviation must be traced to a citable source, or an existing benchmark claim must be checked for independence and resolution before it is trusted."
last_verified: "2026-08-08"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Benchmark Reference Data

Every Standard and Comprehensive NeqSim task must compare its results against
independent reference data before the numbers are reported. In practice that
step gets rewritten in every benchmark notebook, with the reference values pasted
in as bare literals, no citation, an invented tolerance, and no check that the
reference is actually independent of the model being tested.

This skill supplies the parts that should not be rewritten: *where the reference
came from*, *whether it is allowed to be used as a benchmark here*, *how far the
model may deviate before the comparison fails*, and *what the result block must
look like* so the report generator and the CI gate accept it.

It does not compute NeqSim results. It provides the other side of the comparison
and the verdict.

## When to Use

- A task is writing its `XX_benchmark_validation.ipynb` notebook.
- A `benchmark_validation` block must be produced for `results.json`.
- A property, critical constant, or saturation condition from a NeqSim fluid
  needs an independent, citable reference value.
- A number quoted in a report needs a traceable provenance chain from value to
  citation.
- An existing benchmark claim must be audited: is the reference independent, is
  the deviation larger than the reference's own uncertainty, are there enough
  points?

## When *Not* to Use

- As a property engine. CoolProp and the anchor table are references, not the
  model — do not use them to produce the answer the task is asked for.
- For mixtures outside a reference formulation's validated range. The
  applicability gate will refuse, and it is right to refuse.
- As a substitute for measured data on the actual fluid. A reference EOS for a
  pure component does not validate a characterised reservoir fluid; it validates
  the pure-component limit of the model.
- To manufacture a PASS. Loosening the tolerance until a comparison passes is
  the failure mode this skill exists to make visible.

## Inputs

| Input | Meaning |
| --- | --- |
| `model_value` | the number the task computed (NeqSim, or any model under test) |
| `reference` | a `ReferencePoint` from the anchor table or the CoolProp backend |
| `tolerance_pct` | acceptance band in percent; defaults per property when omitted |
| `model_tier` | authority tier of the model basis, default `"correlation"` |
| `model_label` | label used in the output block, default `"neqsim"` |
| `informational` | mark a comparison as context only, never graded |

`ReferencePoint` carries `fluid`, `property_name`, `value`, `unit`, `state`,
`source_key`, and the citation reached through the source registry.

## Outputs

| Output | Meaning |
| --- | --- |
| `BenchmarkResult.status` | `PASS`, `WARN`, `FAIL`, or `INFO` |
| `deviation`, `deviation_pct` | signed model-minus-reference difference |
| `within_source_uncertainty` | whether the deviation is smaller than the reference's own stated uncertainty |
| `independent` | whether the reference outranks the model basis |
| `citation` | full reference citation for the report's reference list |
| `BenchmarkReport.overall_status` | roll-up: FAIL beats WARN beats PASS |
| `BenchmarkReport.blockers()` | why the benchmark may not be presented as validated |
| `to_results_json()` | the `benchmark_validation` block for `results.json` |
| `to_markdown()` | the table for the notebook cell and the report body |

## Engineering Method

**1. Authority tiers.** Sources are ranked
`primary_standard` > `reference_eos` > `measured_data` > `published_case` >
`correlation`. A benchmark reference must rank *strictly above* the model basis
it tests. Comparing SRK against SRK, or GERG-2008 against a CoolProp HEOS
evaluation of the same formulation, is a consistency check, not a benchmark — it
is graded `INFO`, never `PASS`, and appears in `blockers()`.

**2. Applicability gate.** Each source declares the fluids and the temperature
and pressure ranges over which it is validated (for example Span-Wagner CO2 from
the triple point 216.592 K to 1100 K and up to 800 MPa). `sources_for(...)`
returns only sources valid at the requested state, so a reference is never quoted
outside its published range.

**3. Deviation and grading.** Deviation is
$\delta = x_\text{model} - x_\text{ref}$ and
$\delta_\% = 100\,\delta / |x_\text{ref}|$. With tolerance $\tau$:

$$
\text{status} =
\begin{cases}
\text{PASS} & |\delta_\%| \le \tau \\
\text{WARN} & \tau < |\delta_\%| \le 2\tau \\
\text{FAIL} & |\delta_\%| > 2\tau
\end{cases}
$$

A zero reference value cannot be graded relatively and returns `INFO`.

**4. Resolution check.** Agreement cannot be claimed finer than the reference's
own uncertainty. `within_source_uncertainty` records whether
$|\delta_\%|$ is below the source's stated uncertainty for that property, so a
report does not claim 0.01 % agreement against a source good to 0.5 %.

**5. Three-point minimum.** The task rules require at least three independent
comparison points. `meets_minimum_points()` counts only *graded* results, so
padding a thin benchmark with `INFO` rows does not satisfy the gate.

**6. Offline anchors.** The anchor table holds published constants — critical
points, triple points, normal boiling points, the CO2 sublimation point, and
water density at 25 °C and 1 atm — taken directly from the cited reference
formulations. It exists so a benchmark is still possible with no optional
dependency and no network. It is a smoke-test set; a real study extends it with
CoolProp, lab data, or a published case for the fluid actually modelled.

## Python Usage Pattern

Offline, no optional dependency:

```python
from benchmark_reference_data import BenchmarkReport, compare, find_anchor

report = BenchmarkReport(description="SRK pure-component anchors")

report.add(compare(
    "CO2 critical temperature",
    fluid.getPhase(0).getComponent("CO2").getTC(),   # NeqSim value
    find_anchor("co2", "critical_temperature"),
))
report.add(compare(
    "Methane critical temperature",
    fluid.getPhase(0).getComponent("methane").getTC(),
    find_anchor("methane", "critical_temperature"),
))
report.add(compare(
    "Water density at 25 C, 1 atm",
    water_density_kg_m3,
    find_anchor("water", "density", temperature_K=298.15, pressure_Pa=101325.0),
))

print(report.to_markdown())
results["benchmark_validation"] = report.to_results_json()
```

With the optional CoolProp backend, at states the task actually operates at:

```python
from benchmark_reference_data import BenchmarkReport, compare
from benchmark_reference_data.coolprop_backend import is_available, reference_grid

if is_available():
    references = reference_grid("co2", "density", (280.0, 300.0, 320.0), (5.0e6, 10.0e6))
    report = BenchmarkReport(description="CO2 density vs CoolProp HEOS")
    for ref in references:
        state = ref.state
        report.add(compare(
            "CO2 density at {:g} K, {:g} bar".format(
                state["temperature_K"], state["pressure_Pa"] / 1.0e5),
            neqsim_density(state["temperature_K"], state["pressure_Pa"]),
            ref,
        ))
```

Auditing an existing benchmark before trusting it:

```python
if not report.meets_minimum_points():
    raise AssertionError(report.blockers())
for issue in report.blockers():
    print("BLOCKER:", issue)
results["references"] = [{"id": "ref", "text": c} for c in report.citations()]
```

## Validation Checklist

- [ ] At least three **graded** comparisons (`meets_minimum_points()` is true).
- [ ] `blockers()` is empty, or every entry is explained in the report.
- [ ] Every reference outranks the model basis (`independent` is true).
- [ ] Every reference state lies inside the source's validated range.
- [ ] Tolerances are the project's acceptance criteria, not the screening
      defaults, whenever acceptance criteria exist.
- [ ] `within_source_uncertainty` is checked before claiming tight agreement.
- [ ] `report.citations()` is copied into `results["references"]`.
- [ ] The emitted block passes `python devtools/validate_task_results.py <task>`.
- [ ] The benchmark notebook includes a parity or deviation plot alongside the
      table.

## Common Mistakes

- **Benchmarking a model against itself.** A CoolProp HEOS density is not an
  independent check on a NeqSim GERG-2008 density — both evaluate the same
  formulation. Set `model_tier` honestly and let the gate say so.
- **Pasting reference values without a citation.** A number with no source
  cannot be defended in review; use the registry so the citation travels with
  the value.
- **Tuning the tolerance to the result.** Set the tolerance from the acceptance
  criteria or the source uncertainty *before* running the comparison.
- **Claiming agreement finer than the reference.** Check
  `within_source_uncertainty`.
- **Padding to three points with `INFO` rows.** Only graded results count.
- **Quoting a reference outside its range.** Span-Wagner CO2 does not extend
  below the triple point at 216.592 K; the applicability gate refuses for a
  reason.
- **Validating a characterised reservoir fluid with pure-component anchors.**
  That validates the pure-component limit only; say so in the report.

## Limitations

- The anchor table is intentionally small and pure-component only. It is a smoke
  test, not a validation dataset.
- CoolProp is optional and not vendored; without it, reference values are limited
  to the anchor table.
- No mixture reference data is bundled. GERG-2008 is registered as a source, but
  values must come from CoolProp, a publication, or a lab report.
- Tolerances are screening defaults derived from typical reference-EOS
  uncertainties. They are not project acceptance criteria.
- The skill grades a comparison; it does not decide whether the property being
  compared is the one that matters for the engineering decision.

## Related NeqSim Functionality

- `neqsim.thermodynamicoperations.ThermodynamicOperations#TPflash()` followed by
  `SystemInterface#initProperties()` produces the model values compared here —
  transport properties are zero without `initProperties()`.
- `neqsim.thermo.system.SystemGERG2008Eos` and
  `neqsim.thermo.util.gerg.NeqSimGERG2008` give NeqSim's own GERG-2008
  evaluation. Because it is the *same formulation* as the `gerg2008` source, use
  `model_tier="reference_eos"` so the comparison is correctly graded `INFO`.
- `neqsim.thermo.util.steam.Iapws_if97` and `neqsim.thermo.phase.PhaseWaterIAPWS`
  are NeqSim's IAPWS implementations, with the same independence caveat against
  the `iapws95` / `iapws_if97` sources.
- `neqsim.util.agentic.TaskResultValidator` validates the emitted
  `benchmark_validation` block in Java; `devtools/validate_task_results.py` is
  the equivalent CI gate.
- `neqsim.thermodynamicoperations.ThermodynamicOperations#calcPTphaseEnvelope`
  supplies the cricondenbar and cricondentherm that a lab CME/CVD or GERG-2008
  reference is compared against.

## Related Skills

- `neqsim-fluid-quality-check` — run before benchmarking; a composition that
  fails the quality check makes any benchmark meaningless.
- `neqsim-pvt-regression-characterization-factor`,
  `neqsim-pseudocomponent-split-characterization` — supply the characterised
  fluid whose pure-component limits this skill checks.
- `neqsim-e300-fluid-io` — supplies the fluid basis a benchmark is run on.
- `neqsim-cfd-coupling`, `neqsim-fem-coupling` — same gate-before-quoting
  discipline applied to CFD and FEM studies rather than property values.

## References

- Wagner, W., & Pruss, A. (2002). The IAPWS formulation 1995 for the
  thermodynamic properties of ordinary water substance for general and scientific
  use. *Journal of Physical and Chemical Reference Data*, 31(2), 387-535.
- IAPWS R7-97(2012). *Revised Release on the IAPWS Industrial Formulation 1997
  for the Thermodynamic Properties of Water and Steam.*
- Span, R., & Wagner, W. (1996). A new equation of state for carbon dioxide
  covering the fluid region from the triple-point temperature to 1100 K at
  pressures up to 800 MPa. *Journal of Physical and Chemical Reference Data*,
  25(6), 1509-1596.
- Setzmann, U., & Wagner, W. (1991). A new equation of state and tables of
  thermodynamic properties for methane covering the range from the melting line
  to 625 K at pressures up to 100 MPa. *Journal of Physical and Chemical
  Reference Data*, 20(6), 1061-1155.
- Span, R., Lemmon, E. W., Jacobsen, R. T., Wagner, W., & Yokozeki, A. (2000). A
  reference equation of state for the thermodynamic properties of nitrogen.
  *Journal of Physical and Chemical Reference Data*, 29(6), 1361-1433.
- Bucker, D., & Wagner, W. (2006). A reference equation of state for the
  thermodynamic properties of ethane. *Journal of Physical and Chemical Reference
  Data*, 35(1), 205-266.
- Lemmon, E. W., McLinden, M. O., & Wagner, W. (2009). Thermodynamic properties
  of propane. III. A reference equation of state. *Journal of Chemical and
  Engineering Data*, 54(12), 3141-3180.
- Kunz, O., & Wagner, W. (2012). The GERG-2008 wide-range equation of state for
  natural gases and other mixtures. *Journal of Chemical and Engineering Data*,
  57(11), 3032-3091. Adopted as ISO 20765-2 and ISO 20765-3.
- Bell, I. H., Wronski, J., Quoilin, S., & Lemort, V. (2014). Pure and pseudo-pure
  fluid thermophysical property evaluation and the open-source thermophysical
  property library CoolProp. *Industrial & Engineering Chemistry Research*,
  53(6), 2498-2508.
- Linstrom, P. J., & Mallard, W. G. (Eds.). *NIST Chemistry WebBook, NIST
  Standard Reference Database Number 69*. National Institute of Standards and
  Technology, Gaithersburg MD.
- ASME V&V 20-2009, *Standard for Verification and Validation in Computational
  Fluid Dynamics and Heat Transfer* — comparison error and validation
  uncertainty, the basis for the resolution check.
