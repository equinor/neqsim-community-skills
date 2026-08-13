---
name: neqsim-flow-induced-vibration-screening
version: "0.1.0"
description: "Educational flow-induced vibration (FIV) screening using a public fluid kinetic-energy (rho v^2) likelihood-of-failure index. USE WHEN: a task needs a public, screening-level check of whether a main-line flow velocity and density produce a kinetic-energy level that warrants a detailed Energy Institute style FIV assessment before piping vibration design."
last_verified: "2026-06-18"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Flow-Induced Vibration Screening

Use this skill for public, educational flow-induced vibration (FIV) screening. It computes a fluid kinetic-energy index `rho v^2` and compares it to a configurable kinetic-energy threshold so an agent can flag piping that may need a detailed Energy Institute style FIV likelihood-of-failure assessment before vibration design.

## When to Use

- When a user asks whether a line could be prone to flow-induced vibration.
- When an agent needs a quick kinetic-energy triage to scope a piping vibration study.
- When examples must run without confidential piping classes, project line lists, or company piping specs.

## Inputs

- `fluid_velocity`: actual flowing velocity in the line in m/s.
- `mixture_density`: flowing mixture density in kg/m3.
- `kinetic_energy_threshold`: screening kinetic-energy threshold in Pa, default 10000.0.
- `small_bore_present`: optional flag that a small-bore connection or thermowell is present, default False.

## Outputs

- `kinetic_energy_pa`: fluid kinetic-energy index `rho v^2` in Pa.
- `threshold_ratio`: ratio of the kinetic energy to the screening threshold.
- `likelihood_of_failure_band`: qualitative `low`, `medium`, or `high` band.
- `fiv_warning`: `ok`, `watch`, or `high`.
- `small_bore_flag`: True when a small-bore connection raises the screening sensitivity.
- `assumptions`: public assumptions used by the placeholder model.

## Engineering Method

The Python class `FlowInducedVibrationModel` uses an open, published screening concept only:

- the fluid kinetic energy uses the widely published index `FKE = rho v^2`, the same quantity used as the primary driver in public Energy Institute style FIV likelihood-of-failure screening.
- the threshold ratio compares the kinetic energy to a configurable screening threshold.
- a small-bore connection flag lowers the effective warning thresholds because small-bore and thermowell connections are a common FIV failure location.
- the likelihood-of-failure band is a simple rule-based label derived from the threshold ratio.

This is educational and screening-only logic. It does not reproduce the proprietary Energy Institute Guidelines, scoring tables, or correction factors. It is not a vibration standard, a fatigue method, a modal analysis, or a replacement for a qualified piping vibration assessment.

## Python Usage Pattern

```python
from flow_induced_vibration_screening import FlowInducedVibrationModel

model = FlowInducedVibrationModel()
result = model.evaluate(
    fluid_velocity=20.0,
    mixture_density=60.0,
    kinetic_energy_threshold=10000.0,
    small_bore_present=False,
)

print(result.fiv_warning)
print(result.kinetic_energy_pa)
print(result.likelihood_of_failure_band)
```

If the optional `neqsim` Python package is available, the result records that fact so an agent can recommend moving to validated NeqSim property models for mixture density and velocity, followed by a detailed FIV assessment. If it is not installed, the example still runs with public placeholder logic.

## Related NeqSim Functionality

NeqSim already implements a validated Energy Institute style FIV likelihood-of-failure model. Redirect real assessments to:

- `neqsim.process.measurementdevice.FlowInducedVibrationAnalyser` — likelihood-of-failure analyser attached to a pipe segment.
- `neqsim.process.mechanicaldesign.manifold.ManifoldMechanicalDesignCalculator` — acoustic-induced vibration (AIV) likelihood-of-failure for manifold piping.

This skill is a public `rho v^2` triage layer that decides when to invoke `FlowInducedVibrationAnalyser` for a full assessment.

## Calibrated LOF ratios when the line size is unknown

A very common real situation is that the **design LOF is known but the line list is not**:
a project states "max rate X was set at LOF ≈ 1", yet the diameter, wall thickness and
support-arrangement category cannot be retrieved. The assessment is still fully defensible,
because the validated correlation is

```
LOF = rho_mix * v_mix^2 * FVF / F_v      with   F_v = alpha * (D/t)^beta
```

For two operating points **on the same line**, `F_v` is identical and the flow area `A` also
cancels (since `rho v^2 = mdot^2 / (rho A^2)`), so

```
LOF_2 / LOF_1 = (rho_mix v_mix^2 FVF)_2 / (rho_mix v_mix^2 FVF)_1
```

is **exactly independent of D, t and the support category**. The recommended pattern is:

1. Reproduce the stated design point with an assumed geometry and record `LOF_raw_anchor`.
2. Report every other case as `LOF = LOF_raw_case / LOF_raw_anchor * LOF_design`.
3. Verify the cancellation numerically by re-running one case with a different
   `setSupportArrangement(...)` — the calibrated LOF must not move.
4. Use the assumed geometry **only** to report absolute velocities, and flag it as an assumption.

The same identity gives the operating envelope directly, since `LOF ~ Q^2` at fixed pressure:

```
Q_allow(P) = Q_design * sqrt( LOF_design / LOF(Q_design, P) )
```

Sweeping `P` turns a single design rate into an allowable-rate-versus-pressure curve, which
is usually what an operator actually needs.

## Wet gas versus dry gas: which way does the driver move?

A recurring and consequential mistake is to assume that drying a wet-gas line makes flow-induced
vibration **worse**. It makes it **better**. At the same standard gas rate and pressure:

- the mixture density falls a lot (entrained liquid is what makes the mixture heavy), while the
  velocity rises only a few percent, so `rho v^2` falls slightly; and
- decisively, `FVF` drops from the two-phase branch (~0.3-0.4 at GVF 0.97-0.99) to
  `sqrt(mu_gas [cP])` ~ 0.11 for a single-phase gas.

The net wet-over-dry driver ratio for a typical rich gas at 40-50 bara is **about 3 to 4**.

> **Sanity rule.** If a calculation reports that removing liquid from a wet-gas line *raises*
> the LOF, the calculation is wrong. Check `FVF` first: it must fall, not rise, as GVF goes to 1.
> At GVF = 0.99 the two-phase branch gives `FVF = 0.268`, so a single-phase gas must come out
> **below** that. (A NeqSim defect that returned `FVF ~ 0.61` for dry gas - an extra square root
> plus a Pa*s/cP unit mismatch - was found exactly this way and is fixed; the branch is now
> `FVF = sqrt(mu_cP / REFERENCE_VISCOSITY_CP)`.)

### The corollary that matters operationally

Because main-line FIV *relaxes* when a line goes dry, a wet-gas rate limit derived from FIV is
conservative for dry service, and **main-line FIV usually stops being the binding mechanism**.
Do not carry a wet-gas FIV rate derating into dry-gas operation. The dry-gas concern is a
different mechanism - **flow-induced pulsation of dead legs** - see the hand-off below.

## Hand-off: dry-gas service means screening dead legs, not re-deriving a rate limit

When a line is converted from wet gas to dry gas, screen closed side branches with
`neqsim.process.safety.vibration.FlowInducedPulsationScreening` (quarter-wave branch modes,
Strouhal lock-in band 0.2-0.6, mode-weighted severity). Three protections that wet gas provided
all disappear at once:

1. **Acoustic damping collapses** - liquid films and droplets are strong absorbers, so a dry
   branch is a high-Q resonator.
2. **The branch-mouth shear layer becomes coherent** - wet/slugging flow continually disrupts it,
   which is what prevents sustained lock-in.
3. **Liquid-filled legs empty** - a condensate-filled drain resonates near 850-1000 m/s; once it
   drains to gas the sound speed falls to ~375 m/s and its modes drop by a factor ~2.3.

Run-pipe accelerometers are largely **blind** to branch pulsation, so a clean main-line vibration
record does not clear this mechanism. Pair the two screenings whenever a dry-gas transition,
an increased-velocity case, or a "we measured the main line and it was fine" argument appears.

## Gotchas with the validated analyser

| Symptom | Cause | Fix |
| --- | --- | --- |
| Dry gas reports a **higher** LOF than wet gas at the same rate and pressure | Physically impossible - `FVF` is being evaluated wrongly on the GVF > 0.99 branch (historically a unit mismatch: `getSegmentMixtureViscosity` returns **cP**, not Pa*s). | Assert `FVF(dry) < 0.268` and `LOF(dry) < LOF(wet)`. Update NeqSim if the installed build predates the fix. |
| `IllegalStateException` about wall thickness | `pipe.setThickness(...)` not set; the LOF correlation divides by `D/t`. | Set the wall thickness in metres before measuring. |
| GVF comes out ~0.99+ for a "wet" case | The synthetic fluid is too lean - a plausible-looking composition can carry far less liquid than the field. | Calibrate the heavy-end/water content to the **measured** liquid-to-gas ratio at line conditions; GVF is the property the correlation is most sensitive to. |
| Comparing cases that straddle GVF = 0.99 | `FVF` changes branch there (quadratic below, viscosity-based above). The branches are continuous in direction but not in slope, so a mixed case set mixes two regimes. | Keep compared cases on the same branch where possible, and **always print GVF next to LOF** so a branch change is visible. |
| Screening says the main line is fine but the plant has a vibration problem | Main-line LOF does not cover **small-bore connections** (valve cavity drains, thermowells), **loose supports**, or **dead-leg pulsation**, which is where AVIFF failures actually occur. | Treat the main-line LOF as necessary but not sufficient; pair it with a small-bore-connection survey, a support inspection, and `FlowInducedPulsationScreening` for closed branches. |

## Field validation pattern

When permanent vibration probes exist, validate the driver before using LOF as a control
parameter: correlate the measured velocity (mm/s rms) against a driver proxy built from
historian tags, `q^2 / P` (proportional to `rho v^2`). A strong Pearson correlation confirms
the response is flow-kinetic-energy driven rather than machinery or acoustic in origin, which
is what justifies expressing the operating limit in rate **and** pressure.

## Validation Checklist

- [ ] Inputs are positive and densities and velocities are in SI units.
- [ ] Example inputs are public and synthetic.
- [ ] Tests cover low, warning, high, small-bore, and invalid-input cases.
- [ ] Results are described as educational screening indicators.
- [ ] Real FIV assessment is redirected to validated methods, Energy Institute guidelines, and qualified review.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Kinetic energy looks too low | Density taken at standard rather than flowing conditions | Evaluate density at line pressure and temperature |
| Threshold never triggers | Threshold set above realistic main-line limits | Use a service-appropriate threshold and consider the small-bore flag |
| Result treated as a fatigue life | Confusing screening with assessment | Move to a detailed FIV likelihood-of-failure assessment |

## Limitations

- No proprietary Energy Institute scoring tables, correction factors, or fatigue calculations are included.
- No mechanical, modal, acoustic, or support-stiffness analysis is performed.
- No transient, slug, or two-phase intermittency excitation is modelled.

## References

- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Skills Guide: https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
