---
name: neqsim-flare-helideck-dispersion
calculation_basis: "hybrid"
version: "1.1.0"
description: "Screening dispersion of unignited release gas (flare tip, cold vent, PSV tail pipe, vent) from any source on a facility to any receptor - helideck and flight paths, air intakes, accommodation, muster areas, escape routes, crane cabs, ignition sources - with Briggs rise, Gaussian plume, wind-weighted conditional exceedance of 10 and 20 % LFL, tilt scan, figures and results.json. USE WHEN: asking whether gas from a release point can reach a place on a facility."
last_verified: "2026-11-20"
tags: [safety, dispersion, flare, vent, helideck, flight-path, air-intake, muster-area, escape-route, receptor, facility, unignited-gas, lfl, psv, api520, screening, sensitivity, reporting]
min_neqsim_version: "3.7.0"
requires:
  python_packages: [numpy, matplotlib]
  java_packages: []
  env: []
  network: []
---

# Unignited Release Gas Dispersion to Any Place on a Facility (helideck preset included)

An unignited release from a flare tip (a PSV lift or a blowdown that has lost its pilot or
flame), a cold vent or a PSV tail pipe puts a flammable cloud into the air next to the
installation. The questions are concrete: can the cloud reach a given place - the
helideck and its flight paths, an air intake, the accommodation, a muster area, an escape
route, a crane cab, an ignition source - and in which winds? This skill answers them at
screening level, with the numbers weighted by the wind climate and every figure and
`results.json` entry produced from the same run.

Two entry points share one plume model:

- **Facility study** (`flare_helideck_dispersion.facility`, CLI `facility`): any number of
  release **sources** and named **receptors** of any shape (point, disc, rectangle,
  polyline, fan of radial paths, path that follows the wind) in one coordinate frame.
- **Helideck preset** (`run_study`, CLI `run`, and `helideck_facility(...)` which turns the
  same geometry into facility receptors): the original flare-tip, helideck and
  flight-path study. The package name is kept for compatibility.

It is an orchestration of known, public methods - choked flow at the tip, a notional
nozzle, Briggs plume rise, a Gaussian plume - arranged so that the result is
reproducible, honest about what it cannot do, and easy to hand to a CFD tool for the
conditions that matter.

## When to Use

- A task asks whether unignited gas from a flare tip, cold vent, PSV tail pipe or other
  vent (rated PSV flow, blowdown peak, several valves together) can reach a place on the
  facility, and in which winds: helideck and flight paths, HVAC or combustion-air intakes,
  accommodation doors and windows, control room, muster area, lifeboat station, escape
  route, crane cab, laydown or work area, turbine exhaust or hot-work area, a neighbouring
  installation.
- Several release points and several receptors must be ranked in one run
  (`FacilityStudyResult.ranking`), each receptor with its own thresholds and criterion
  source.
- A helideck or flight-path study needs a wind-weighted exceedance with explicit 10 % and
  20 % LFL thresholds and a tip-inclination sensitivity.
- Worst-case wind conditions must be selected for a CFD run, with the source terms and
  receptors written out as a hand-off.
- A professional set of figures and a `results.json` fragment are needed from one run.

## When *Not* to Use

- As a QRA or an annual frequency. Exceedance values are **conditional on an unignited
  release being ongoing**; they carry no flame-out frequency (see Limitations).
- For ignited releases (jet fire, radiation) - use `neqsim-flare-radiation-screening` and
  `neqsim-jet-fire-radiation-screening`. For a ground-level continuous release distance
  use `neqsim-gas-dispersion-distance-screening`.
- To approve a design against a helideck, air-intake or other standard. The model has no
  platform wake and no building effects, so a result near a criterion needs CFD.
- For toxic gas against a toxic limit unless the limit is entered as `lfl_vol_frac` (the
  result then reads "% of limit"); toxic dose, probit and shelter effects are not modelled.
- With confidential layouts, flight paths or wind records in a public workspace.

## Inputs

| Input | Meaning |
|---|---|
| `Source` | Release point: name, east/north (m), height ASL (m), kind (`flare_tip`, `cold_vent`, `psv_tailpipe`, ...), optional inclination (a vertical vent is 90 deg) |
| `Receptor` | Named place: kind and shape - `point`, `disc`, `rectangle` (grid at one or several heights), `polyline` (route), `fan` (radial paths), `into_wind_path`, `points`; optional own `thresholds_pct_lfl` and `criterion_source` |
| `FacilityRelease` | A `ReleaseCase` together with the `Source` it comes from |
| `PlatformGeometry` | (helideck preset) Flare-tip height ASL, helideck height ASL, horizontal distance and azimuth tip to helideck, helicopter reference height above deck, deck radius, obstacle-free sector start and end (deg true), flight-path settings |
| `FlightPathSettings` | Path length (m), point spacing (m), climb gradient (deg), bearing step (deg, use 5 or finer) |
| `ReleaseCase` | Mass flow (kg/s), molar mass (kg/mol), gamma, stagnation temperature (K), LFL of the fuel part (volume fraction), fuel mole fraction, tip diameter (m); optional `tip_override` (velocity, diameter, density) and ambient gas density |
| `ModelParameters` | Tip inclination (deg), `sigma0` divisor, wind exponent, ambient temperature, stable-air potential-temperature gradients |
| `WindTable` | Joint direction x speed share of all hours (%), sector names/centres, speed bins and representative speeds; built from JSON or from an hourly CSV (`WindTable.from_hourly_csv`) |
| `StudySettings` | Plume modes (`briggs`, `none`), thresholds (% LFL), sub-sector offsets, Pasquill scheme (`conservative_stable`, `neutral`, `night_stable`, `day_moderate` or custom) |
| Flame-out frequency, duration | Optional; only then an annual figure is produced |
| Image, anchor pixel, px per metre | Optional, for the schematic overlay (helideck preset) |

All coordinates of a facility study are east/north/up metres in one frame with true-north
axes and height above sea level; the origin is free (plant grid converted with
`receptors.grid_to_true`). Wind directions are the direction the wind blows **from**.

`flare_helideck_dispersion.sources` converts a composition to molar mass, fuel
fraction and Le Chatelier LFL, computes the rated flow of an API 526 orifice with the
public API 520 critical-flow equation, and (only if NeqSim is importable) sizes a gas PSV
with `ReliefValveSizing`. Without NeqSim, supply the rated mass flow directly.

## Outputs

| Output | Contents |
|---|---|
| `FacilityStudyResult.summaries` | Per case, mode and receptor: peak % LFL, exceedance (% of wind hours **given a release**) at each threshold and by speed bin, and the worst condition (wind, speed, Pasquill class, position, distance and bearing from the source, height relative to the source, path bearing and distance for routes and fans) |
| `FacilityStudyResult.ranking(threshold)` | Case-receptor pairs ranked by exceedance, then peak |
| `facility_results.json`, `facility_arrays.npz` | Summaries and the `[sector, sub-offset, speed bin]` arrays per receptor |
| `facility_sensitivity.json` | Inclination scan per case and receptor (`facility_tilt_scan`); `facility_tornado` ranks parameters for one receptor |
| `facility_layout.png`, `facility_exceedance.png` | Plan of sources and receptors with the worst-condition footprint; exceedance (or peak, when nothing exceeds) per receptor and case |
| `section.json` (`facility_section`, CLI `section`) | Vertical section of the plume through a source along any azimuth: `s`, `z`, `values` (% LFL), levels, and the receptors in the plane as marks (`s`, `z`, label, peak there) for a schematic overlay on a picture of the facility |
| `facility_fragment.json` | `key_results`, `conclusions` (a string), tables (sources, receptor register, exceedance, worst condition, criteria, tilt scan), figure discussion, assumptions, data gaps, contributor ranking, ruled out, robustness, conservatism, evidence against, discriminating test, internal-consistency `benchmark_validation`, `cfd_handoff` |
| `StudyResult.summaries` (helideck preset) | Per case and mode: peak % LFL at the helideck, into-wind path and any flight path; exceedance for the three receptors and by speed bin; worst condition; free-jet cross-check |
| `study_results.json`, `uncertainty.json`, figures, `overlay`, `results_fragment.json` | As before for the helideck preset (layout, wind climate, footprints, sections, heat maps, exceedance, benchmark, tornado, tilt scan, Monte Carlo) |

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
A vertical vent (tilt 90 deg) has the full momentum rise; an inclined or horizontal
release lifts less and leaves cold dense gas low.

**Dispersion.** Gaussian plume with Briggs open-country sigmas, sea-surface reflection
and a virtual-source spread `sigma0 = |dh| / 3.5`. Wind at release height follows a
power law (exponent 0.11). The free-jet decay of Chen and Rodi gives an independent
axial distance to a LFL fraction; `jet_consistency_check` flags cases in which the
Gaussian distance is shorter than the free-jet distance (virtual-source over-dilution of
a momentum jet) so the value can be read as non-conservative.

**Wind sweep.** For every sector, five sub-sector offsets and speed bin the model
evaluates every receptor and keeps the maximum over its points: fixed points, areas and
routes are assessed together in one plume evaluation per wind condition; a path that
follows the wind (`into_wind_path`) is re-pointed per wind direction. Flight-path fans use
a 5 degree bearing step or finer - 15 degrees under-samples the plume width and
under-states exceedance hours by up to a factor two. Wind direction is the direction the
wind blows **from**; the plume travels toward `from + 180`.

**Exceedance semantics.** `exceed_pct_hours` is the share of all wind hours, weighted by
the joint table, in which the threshold is exceeded somewhere on the receptor, *given
that an unignited release of that rate is ongoing*. It is not an annual frequency. Use
`annualise_exposure` with an explicit flame-out frequency and release duration; there is
no default.

**Receptor height matters.** Gas lifted above an air intake or a deck does not reach it;
cold dense gas that sinks reaches a low receptor. Always give the true height of the
receptor, report the height relative to the source of the worst condition and run the
inclination scan.

**Stability.** The default `conservative_stable` scheme (F below 2 m/s, E 2-4 m/s, D above)
keeps a lifted plume near release height. Exposure then exists only in light stable wind;
neutral or unstable schemes remove most of it. Always state the dependence and run an
alternative scheme as a sensitivity.

**Sensitivity.** Inclination scan (a flat tip leaves cold dense gas low and can reach a
low receptor even when the base case is clean; a vertical vent lifts it), one-at-a-time
tornado and, for the helideck preset, a seeded Monte Carlo over inclination, `sigma0`
divisor, wind exponent and release rate.

## Python Usage Pattern

Any sources and receptors:

```python
from flare_helideck_dispersion import (
    FacilityRelease, Receptor, Source, StudySettings, WindTable, ReleaseCase,
    run_facility_study, facility_tilt_scan, build_facility_results,
)
from flare_helideck_dispersion.facility_figures import make_facility_figures
from flare_helideck_dispersion.results import write_results_json

wind = WindTable.from_hourly_csv("hourly_wind.csv")
flare = Source("HP flare", 0.0, 0.0, 85.0, "flare_tip", tilt_deg=30.0)
vent = Source("Cold vent", 140.0, 35.0, 60.0, "cold_vent", tilt_deg=90.0)
cold = ReleaseCase("Cold blowdown", 60.0, 0.0215, 1.25, 190.0, 0.04, 0.96, 0.4)
receptors = [
    Receptor.point("Combustion-air intake", "air_intake", 55.0, -30.0, 40.0,
                   criterion_source="design basis clause"),
    Receptor.rectangle("Muster area", "muster_area", 60, -90, 90, -60, 12.0, spacing_m=5.0),
    Receptor.polyline("Escape route", "escape_route", [(0, -60, 20), (80, -60, 20)], 5.0),
    Receptor.from_dict({"name": "Crane cab", "kind": "crane_cab", "shape": "point",
                        "east_m": -40, "north_m": 20, "height_asl_m": 55}),
]
study = run_facility_study(
    [FacilityRelease(cold, flare), FacilityRelease(cold, vent)], wind, receptors, StudySettings())
for row in study.ranking(20.0):                     # worst first
    print(row["case"], row["receptor"], row["peak_pct_lfl"], row["exceed_pct_hours"])
scans = {fr.case.name: facility_tilt_scan(fr, wind, receptors, study.settings) for fr in study.freleases[:1]}
records = make_facility_figures(study, "figures")
write_results_json("results.json", build_facility_results(study, records, scans))
```

The helideck, any flight path and the into-wind path as receptors of a facility study:

```python
from flare_helideck_dispersion import PlatformGeometry, helideck_facility
source, deck_receptors = helideck_facility(PlatformGeometry(), "HP flare", origin_en=(0.0, 0.0))
```

Original helideck workflow:

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
<python> -m flare_helideck_dispersion facility config.json --figures
<python> -m flare_helideck_dispersion section config.json
<python> -m flare_helideck_dispersion run config.json
<python> -m flare_helideck_dispersion figures config.json
<python> -m flare_helideck_dispersion overlay config.json
```

A facility configuration has `wind`, `releases` (each with a `source` name), `sources`,
`receptors` (mappings with `shape`; see `Receptor.from_dict`), optional `helideck` (platform
geometry fields plus `source`, adds the helideck, any flight path and into-wind path),
`settings`, `sensitivity` (`tilts`), `criteria`, `flameout` and, for `section`, a `section`
mapping (`case`, `wind_from_deg`, `speed_m_s`, optional `azimuth_deg`, `s_range_m`,
`z_range_m`, `tolerance_m`, `out`). The section file feeds any tool that draws a
schematic result overlay on a picture; its marks are positions in the plane, not
registered picture positions. See `examples/facility_example.json`.

`examples/generic_platform_example.py` runs the helideck chain on a synthetic platform and
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
- Facility study: every receptor has a stated criterion source, a true height and a
  surveyed or declared-approximate position; the source inclination matches the hardware
  (a vertical vent is 90 deg); the inclination scan is reported for every low receptor;
  routes and fans are sampled finely enough (5 m for routes near the source, 5 degrees for
  fans); several simultaneous releases are one combined mass flow, not superposed cases.

## Common Mistakes

- Quoting exceedance hours as an annual frequency or probability of exposure.
- Judging an air intake or enclosed space by the outside concentration alone: ventilation,
  dilution and detection inside the building are not modelled.
- Giving a receptor the height of the deck or of the source instead of its own height.
- Leaving the default flare-tip inclination on a vertical vent (set `tilt_deg=90`).
- Ranking receptors by peak concentration when the criterion is an exceedance (or the
  reverse): `ranking` sorts by exceedance first, then peak; read both.
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
- Receptor positions, heights and shapes are inputs; a receptor is judged by the maximum
  over its points. Simultaneous releases from different sources are not superposed.
- Concentrations are percent of the `lfl_vol_frac` of the case; there is no toxic dose,
  probit or shelter model.
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
