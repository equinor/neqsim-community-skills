---
name: neqsim-flare-helideck-dispersion
calculation_basis: "hybrid"
version: "1.0.0"
description: "Screening dispersion of unignited flare-tip gas to a helideck and its flight paths: choked tip and notional jet, Briggs rise with stable-air caps, Gaussian plume, wind-weighted conditional exceedance of 10 and 20 % LFL, tilt scan, tornado, Monte Carlo, house-style figures, results.json. USE WHEN: asking whether PSV or blowdown gas from a flare tip can reach a helideck or helicopter approach and departure paths."
last_verified: "2026-11-20"
tags: [safety, dispersion, flare, helideck, flight-path, unignited-gas, lfl, psv, api520, screening, sensitivity, reporting]
min_neqsim_version: "3.7.0"
requires:
  python_packages: [numpy, matplotlib]
  java_packages: []
  env: []
  network: []
---

# Flare-tip Gas Dispersion to a Helideck and Flight Paths

An unignited release from a flare tip (a PSV lift or a blowdown that has lost its pilot or
flame) puts a flammable cloud into the air next to the platform. The questions are
concrete: can the cloud reach the helideck, and can it cross the approach and departure
paths? This skill answers them at screening level, with the numbers weighted by the wind
climate and every figure and `results.json` entry produced from the same run.

It is an orchestration of known, public methods - choked flow at the tip, a notional
nozzle, Briggs plume rise, a Gaussian plume - arranged so that the result is
reproducible, honest about what it cannot do, and easy to hand to a CFD tool for the
conditions that matter.

## When to Use

- A task asks whether unignited flare gas (rated PSV flow, blowdown peak, several valves
  together) can reach a helideck or its flight paths, and in which winds.
- A helideck or flight-path study needs a wind-weighted exceedance with explicit 10 % and
  20 % LFL thresholds and a tip-inclination sensitivity.
- Worst-case wind conditions must be selected for a CFD run, with the source terms and
  receptors written out as a hand-off.
- A professional set of figures (layout, wind climate, footprints, sections, heat maps,
  exceedance, benchmark, sensitivity) and a `results.json` fragment are needed from one run.

## When *Not* to Use

- As a QRA or an annual frequency. Exceedance values are **conditional on an unignited
  release being ongoing**; they carry no flame-out frequency (see Limitations).
- For ignited releases (jet fire, radiation) - use `neqsim-flare-radiation-screening` and
  `neqsim-jet-fire-radiation-screening`. For a ground-level continuous release distance
  use `neqsim-gas-dispersion-distance-screening`.
- To approve a design against a helideck standard. The model has no platform wake, so a
  result near a criterion needs CFD.
- With confidential layouts, flight paths or wind records in a public workspace.

## Inputs

| Input | Meaning |
|---|---|
| `PlatformGeometry` | Flare-tip height ASL, helideck height ASL, horizontal distance and azimuth tip to helideck, helicopter reference height above deck, deck radius, obstacle-free sector start and end (deg true), flight-path settings |
| `FlightPathSettings` | Path length (m), point spacing (m), climb gradient (deg), bearing step (deg, use 5 or finer) |
| `ReleaseCase` | Mass flow (kg/s), molar mass (kg/mol), gamma, stagnation temperature (K), LFL of the fuel part (volume fraction), fuel mole fraction, tip diameter (m); optional `tip_override` (velocity, diameter, density) and ambient gas density |
| `ModelParameters` | Tip inclination (deg), `sigma0` divisor, wind exponent, ambient temperature, stable-air potential-temperature gradients |
| `WindTable` | Joint direction x speed share of all hours (%), sector names/centres, speed bins and representative speeds; built from JSON or from an hourly CSV (`WindTable.from_hourly_csv`) |
| `StudySettings` | Plume modes (`briggs`, `none`), thresholds (% LFL), sub-sector offsets, Pasquill scheme (`conservative_stable`, `neutral`, `night_stable`, `day_moderate` or custom) |
| Flame-out frequency, duration | Optional; only then an annual figure is produced |
| Image, anchor pixel, px per metre | Optional, for the schematic overlay |

`flare_helideck_dispersion.sources` converts a composition to molar mass, fuel
fraction and Le Chatelier LFL, computes the rated flow of an API 526 orifice with the
public API 520 critical-flow equation, and (only if NeqSim is importable) sizes a gas PSV
with `ReliefValveSizing`. Without NeqSim, supply the rated mass flow directly.

## Outputs

| Output | Contents |
|---|---|
| `StudyResult.summaries` | Per case and mode: peak % LFL at the helideck, into-wind path and any flight path; exceedance (% of wind hours **given a release**) at each threshold for the three receptors and by speed bin; worst condition; free-jet cross-check |
| `study_results.json`, `study_arrays.npz` | Summaries and the `[sector, sub-offset, speed bin]` arrays |
| `uncertainty.json` | Tilt scan (20-70 deg), tornado, seeded Monte Carlo |
| Figures (`figures.make_all_figures`) | Layout plan and elevation, wind climate, source terms, plan footprints, vertical sections, direction x speed heat maps, polar, exceedance, benchmark, tornado, tilt scan |
| `overlay` | Schematic section on a user image, and a composite with to-scale section and plan |
| `results_fragment.json` | `key_results`, `conclusions` (a string), captions, figure discussion, tables, assumptions, data gaps, uncertainty, risk, contributor ranking, ruled out, robustness, conservatism, discriminating test, evidence against, `benchmark_validation = {points: [...]}`, `cfd_handoff` |

## Engineering Method

**Source.** Mass flow through the tip exit area fixes the stagnation pressure by the
choked-flow mass flux. If that pressure exceeds the critical ratio the flow is choked at
the exit; the Birch notional nozzle expands it to ambient pressure with momentum and mass
conserved, giving an effective diameter, velocity and density. A real-gas tip result can
replace this through `tip_override`.

**Rise.** Only the vertical momentum component `v sin(tilt)` of the inclined tip lifts the
plume (Briggs 1975 transitional and final rise, `3 d v / u` in neutral air). In stable
classes E and F the Briggs stable-air limits cap the momentum rise and the sinking of a
dense plume. A neutral rise applied in light stable wind grows as `1/u` and was found to
lift the plume 100-300 m above where it stays: applying the caps changed the
exceedance of 20 % LFL on the flight paths from zero to several percent of hours.

**Dispersion.** Gaussian plume with Briggs open-country sigmas, sea-surface reflection
and a virtual-source spread `sigma0 = |dh| / 3.5`. Wind at release height follows a
power law (exponent 0.11). The free-jet decay of Chen and Rodi gives an independent
axial distance to a LFL fraction; `jet_consistency_check` flags cases in which the
Gaussian distance is shorter than the free-jet distance (virtual-source over-dilution of
a momentum jet) so the value can be read as non-conservative.

**Wind sweep.** For every sector, five sub-sector offsets and speed bin the model
evaluates the helideck points, every radial flight-path bearing across the
obstacle-free sector (5 degrees or finer - 15 degrees under-samples the plume width and
under-states exceedance hours by up to a factor two) and the into-wind path. Wind direction
is the direction the wind blows **from**; the plume travels toward `from + 180`.

**Exceedance semantics.** `exceed_pct_hours` is the share of all wind hours, weighted by
the joint table, in which the threshold is exceeded somewhere on the receptor, *given
that an unignited release of that rate is ongoing*. It is not an annual frequency. Use
`annualise_exposure` with an explicit flame-out frequency and release duration; there is
no default.

**Stability.** The default `conservative_stable` scheme (F below 2 m/s, E 2-4 m/s, D above)
keeps a lifted plume near release height. Exposure then exists only in light stable wind;
neutral or unstable schemes remove most of it. Always state the dependence and run an
alternative scheme as a sensitivity.

**Sensitivity.** Tip-inclination scan (20-70 deg: a flat tip leaves cold dense gas low and
can reach the deck even when the base case is clean), one-at-a-time tornado and a seeded
Monte Carlo over inclination, `sigma0` divisor, wind exponent and release rate.

## Python Usage Pattern

```python
from flare_helideck_dispersion import (
    PlatformGeometry, ReleaseCase, StudySettings, WindTable, ModelParameters,
    run_study, run_sensitivity, release_case_from_composition,
    api520_rated_mass_flow_kg_s,
)
from flare_helideck_dispersion.figures import make_all_figures
from flare_helideck_dispersion.results import build_results, write_results_json

wind = WindTable.from_hourly_csv("hourly_wind.csv")          # speed + direction columns
geometry = PlatformGeometry()                                # 124 m tip, 76 m deck, 240 m apart
cases = [
    release_case_from_composition("Blowdown cold", 150.0,
                                  {"methane": 0.7, "ethane": 0.2, "propane": 0.1},
                                  gamma=1.25, t0_k=190.0),
]
settings = StudySettings(params=ModelParameters(tilt_deg=45.0))
study = run_study(cases, wind, geometry, settings)
sens = run_sensitivity(cases, wind, study.receptors, settings, n_samples=100, seed=42)
records = make_all_figures(study, "figures", sens)
write_results_json("results.json", build_results(study, records, sens))
```

Command line (relative paths resolve against the configuration file):

```text
<python> -m flare_helideck_dispersion run config.json
<python> -m flare_helideck_dispersion figures config.json
<python> -m flare_helideck_dispersion overlay config.json
```

`examples/generic_platform_example.py` runs the whole chain on a synthetic platform and
wind record. NeqSim is optional: `size_psv_api520_gas(...)` returns `None` when it is not
importable.

### Report quality rules

House style (`flare_helideck_dispersion.style`, enforced by tests):

1. Figures are designed at report text width, **7.2 in**, with 7-9 pt text; never
   13-19 in wide figures that print at 3-4 pt.
2. One shared LFL colour scheme and **one legend at the bottom centre** on every
   concentration figure: the LFL bands plus the 10 % dashed and 20 % solid contour lines.
3. Plan views: true north up, north arrow top-right, wind box top-left (`Wind from NNN
   deg, u m/s, class X`), km axes, identical extent across panels; tip = orange star,
   helideck = blue hexagon, flight paths = green, obstacle-free sector shaded.
4. Titles state the finding (bold, at most two lines); a grey sub-line states case and
   conditions; title and legend margins are reserved so nothing overlaps
   (`style.layout_problems` is run on every saved figure).
5. Peaks written on figures are the peaks **on the flight paths**, not the near-tip core
   value, capped at `> 100 % LFL`.
6. Sections state the vertical exaggeration (x3).
7. Tornado and sensitivity axes start at zero and are shared between panels.
8. No duplicate figures (a table is never repeated as a figure), no empty or default
   pictures; a panel without cloud says so.
9. The benchmark figure shows the peak helideck % LFL on a log axis against the 20 %
   criterion with numeric labels. Benchmark numbers are computed, never typed into text.
10. The overlay composite keeps the mandatory **"schematic, not registered to the
    camera"** disclaimer, a scale bar and to-scale side panels.

Content rules:

- Headline numbers come from `results.json` (generated from the run), not from memory.
- Every figure gets observation, mechanism, implication and recommendation
  (`figure_discussion`).
- State the acceptance criteria with their source, and report **both** 10 % and 20 % LFL.
  The defaults in `results.DEFAULT_CRITERIA` are screening thresholds; the governing value
  and its source (for example the NORSOK S-001 requirement on unignited flare gas at the
  helideck, UK CAP 437 or ICAO helicopter guidance) must be taken from the project design
  basis.
- Hand the worst conditions (`cfd_handoff`) to CFD tools; never present the screening
  numbers as a CFD result.
- Any overlay on a user image carries the disclaimer; an overlay that shows no cloud is an
  error (`EmptyViewError`), not a picture.

## Validation Checklist

- The wind table sums to 100 % and its source, period, height and resolution are stated;
  low-wind bins are checked against an anemometer or high-resolution hindcast.
- The representative speed of the lowest bin (default 1.5 m/s) was also run at 1.0 m/s.
- Flight-path bearing step is 5 degrees or finer, and the paths are the approved ones or
  declared assumptions.
- Both 10 % and 20 % LFL results are reported, with the criterion and its source.
- The tilt scan (20-70 deg) is in the report; the tip angle is confirmed from drawings.
- Passive (`none`) and Briggs-rise results are compared; where the Gaussian distance is
  shorter than the free-jet distance the result is treated as non-conservative.
- An alternative Pasquill scheme (`neutral`) was run and the dependence is stated.
- The rated flow of each orifice matches the relief study; unverified source data are
  flagged for human review.
- `benchmark_validation` passes, and a comparison with an independent (CFD) study is
  reported with its source.
- No annual figure appears without a flame-out frequency and duration.
- `layout_problems` is empty for every figure; the overlay carries the disclaimer.

## Common Mistakes

- Quoting exceedance hours as an annual frequency or probability of exposure.
- Applying the neutral momentum rise `3 d v / u` in stable light wind.
- Using 15-degree flight-path bearings against a plume a few hundred metres wide.
- Reading the near-tip core concentration as the exposure of a flight path.
- Leaving out the tip-inclination scan: the deck result for cold dense gas depends on it.
- Treating the plume model as validated for the lee of the platform; it has no wake.
- Reporting only one of the 10 % and 20 % thresholds, or an unsourced criterion.
- Presenting a schematic overlay as registered to the camera image.
- Typing benchmark or headline numbers into text instead of taking them from the run.
- Mixing wind-from and plume-travel directions (the plume goes toward `from + 180`).

## Limitations

- Screening only: no platform wake, downwash, mechanical turbulence, building effects or
  CFD; a Gaussian plume is not valid much below 1 m/s and meander is ignored.
- Exceedance values are conditional on a release, not annual frequencies; flame-out
  frequency, duration and ignition/operational controls are outside the skill.
- Re-analysis wind has coarse resolution (tens of km, hourly means, no gusts or
  sub-hourly lulls) and tends to under-state offshore calms - exactly where the exposure is.
- Results depend on the stability assumption: exposure exists in stable low-wind
  conditions and mostly vanishes for neutral or unstable schemes.
- The dense-gas sinking term reuses the Briggs rise law with its own cap; it is a
  screening trajectory, not a validated dense-gas model, and should be replaced by a
  jet-in-crossflow model or CFD before a value is quoted for approval.
- With a `tip_override` the jet momentum is fixed; scaling the mass flow in a sensitivity
  then changes only the concentration source term.
- Flight paths are radial assumptions unless the approved paths are supplied.
- The optional NeqSim PSV sizing returns the orifice from `ReliefValveSizing`; the rated
  flow is taken from the API 520 equation, and a build whose capacity function disagrees
  is reported in `warnings`.
- Overlays are schematic and never registered to the camera.
- Human review by a qualified safety engineer is required for any decision.

## Related NeqSim Functionality

- `neqsim.process.util.fire.ReliefValveSizing` (API 520 gas sizing, API 526 orifice
  letters), reached with `from neqsim import jneqsim`; used only by
  `size_psv_api520_gas` when NeqSim is importable.
- `neqsim.process.safety.dispersion.GasDispersionAnalyzer` and `GaussianPlume` for ground
  or passive Gaussian distances to a flammable endpoint; they have no plume rise,
  virtual-source spread or wind-height scaling, so they cannot represent an inclined
  high-momentum tip jet. They are suitable as a cross-check of the passive bound.
- NeqSim flash and EOS calculations (`SystemSrkEos`, `ThermodynamicOperations`) can
  supply composition, molar mass, gamma and real-gas tip conditions for `ReleaseCase`.
- Companion skills: `neqsim-gas-dispersion-distance-screening`,
  `neqsim-psv-orifice-screening`, `neqsim-relief-load-screening`,
  `neqsim-depressurization-screening`, `neqsim-flare-radiation-screening`,
  `neqsim-weather-data`.

## References

- Briggs, G. A. (1969) Plume Rise, USAEC Critical Review Series.
- Briggs, G. A. (1973) Diffusion estimation for small emissions, ATDL-106.
- Briggs, G. A. (1975) Plume rise predictions, in Lectures on Air Pollution and
  Environmental Impact Analyses, American Meteorological Society.
- Birch, A. D., Brown, D. R., Dodson, M. G. and Swaffield, F. (1984) The structure and
  concentration decay of high pressure jets of natural gas, Combust. Sci. Technol. 36,
  249-261.
- Chen, C. J. and Rodi, W. (1980) Vertical Turbulent Buoyant Jets: A Review of
  Experimental Data, Pergamon.
- API Standard 520 Parts I and II and API Standard 521 / ISO 23251 (relief sizing,
  pressure-relieving and depressuring systems); API Standard 526 (orifice designations).
- NORSOK S-001 Technical safety (unignited flare gas at the helideck; confirm the clause
  in the edition in force).
- UK CAA CAP 437, Offshore Helicopter Landing Areas: Guidance on Standards; ICAO Annex 14
  Volume II, Heliports (named for the helideck and obstacle-free-sector context; the
  governing criteria come from the project design basis).
