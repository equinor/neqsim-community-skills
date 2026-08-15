---
name: neqsim-olga-multiphase-simulator
version: "0.1.0"
description: "Run the OLGA transient multiphase flow simulator from Python: locate the installation, validate a genkey case with a rule check, launch the batch engine with the right flags, decode the engine exit code, and read .tpl trend and .ppl profile results. USE WHEN: a task must execute an OLGA case, batch or sweep OLGA runs, diagnose an OLGA failure or licence error, or turn OLGA output into engineering numbers that pair with NeqSim thermodynamics and pipeline screening."
last_verified: "2026-08-14"
requires:
  python_packages: []
  java_packages: []
  env:
    - "OLGA_HOME or OLGA_ENGINE (optional; overrides installation discovery)"
    - "LM_LICENSE_FILE or SLBSLS_LICENSE_FILE (licence source)"
  network:
    - "Reachable licence server if the licence is served rather than node-locked"
tags: [flow-assurance, olga, multiphase, transient, simulator, batch, slugging]
min_neqsim_version: "3.7.0"
---

# OLGA Multiphase Flow Simulator

OLGA (SLB) is a **transient one-dimensional three-phase pipe-flow simulator**. It
is the industry reference for slug tracking, terrain slugging, shut-in and
restart, blowdown, liquid surge to a receiving facility, hydrate and wax
management, well clean-up and drilling hydraulics.

This skill is the **execution and post-processing layer**: how to find the
installed OLGA, validate a case cheaply, launch the batch engine correctly,
understand why it stopped, and read its results into Python. It does not teach
you how to build a flow-assurance model from nothing, and it never replaces a
qualified flow-assurance review.

OLGA is licensed commercial software. This skill assumes the user already has a
valid installation and licence; it only drives what is installed locally.

## When to Use

- A task must run an existing OLGA case and extract numbers from the results.
- A parametric or sensitivity sweep must be run reproducibly rather than by hand
  in the GUI.
- An OLGA run failed and the exit code, log or licence state must be diagnosed.
- OLGA results must be compared against NeqSim screening or pipeline models.

Do **not** use this skill to invent a case from scratch, to guess PVT tables, or
to interpret a transient result without a flow-assurance engineer in the loop.

## Installed Layout (Windows)

A standard installation looks like this — several versions can coexist:

```
C:\Program Files\Schlumberger\
├── Olga 2025.1.0\                    <- the simulator
│   ├── OPGFramework.exe              <- graphical front end
│   ├── opi.exe                       <- launcher associated with .opi case files
│   ├── OlgaExecutables\
│   │   ├── Olga-2025.1.0.exe         <- the batch engine (what you run)
│   │   ├── OlgaOpc-2025.1.0.exe      <- OPC server build
│   │   └── exit_code_lookup.exe      <- decodes engine exit codes
│   ├── Data\OPG Files\               <- bundled sample-case library
│   ├── Tools\  (OLGAViewer, FluidDefTool, Multiflash, ProfileGenerator, Rocx, FEMThermViewer)
│   ├── Modules\RmoParameterStudy\    <- built-in parameter-study module (RMO)
│   └── Plugins\ (FEMTherm, O4W, PipelineEditor)
├── OLGA-S 2025.1.0\Win64\            <- OLGA-S steady-state point model (used by other hosts)
└── OLGA Namespace Explorer 7.3.x\
```

`OLGA-S` is **not** the transient simulator — it is the steady-state point model
that third-party process and nodal-analysis tools link against. The installer
exports its location as `OLGAS_SLB_x64`. Never point the batch runner at it.

User-level libraries live under `%USERPROFILE%\Documents\Schlumberger\`
(`PipelineLibrary\*.pml`, `WellLibrary\*.dml`); shared settings under
`%ProgramData%\Schlumberger\OLGA`.

## File Types

| Extension | Role |
| --- | --- |
| `.opi` | OLGA GUI project/case file — opened by the GUI, not by the engine |
| `.genkey` / `.key` | Keyword input file the batch engine actually reads |
| `.tab` | PVT table referenced by `FILES PVTFILE=` |
| `.rsw` | Restart/snapshot file (`RESTART READFILE=ON, FILE=...`) |
| `.out` | Human-readable run log: input echo, mass-error blocks, stop reason |
| `.tpl` | Trend (time-series) results at the positions given by `TRENDDATA` |
| `.ppl` | Profile (spatial) results for the variables given by `PROFILEDATA` |
| `.plt` | Binary plot file for OLGA Viewer |
| `.h5` | HDF5 result container |
| `.sil` | Event log that can be replayed with `-play` |

The GUI owns the `.opi` project and **generates** the `.genkey` the engine runs.
Automation therefore works on the generated `.genkey`, not on the `.opi`.

## Batch Command Line (verified, OLGA 2025.1.0)

```
Olga-<version>.exe [options] casefile.[key|genkey]
```

The case file must be **last**. The options that matter for automation:

| Option | Effect |
| --- | --- |
| `-exitRC` | Run only the input rule checks, then exit. Use before every long run. |
| `-exitID` | Rule checks plus input-object initialization, then exit. |
| `-nthreads N` | Use N threads for parallel execution. |
| `-outDir DIR` | Write output files to DIR (default: the current directory). |
| `-noout` `-notpl` `-noppl` `-noplt` `-noopc` | Suppress the corresponding output. |
| `-log FILE` / `-consoleLog` | Write engine messages / console output to a log file. |
| `-restorePolicy N` | Override the case `RESTOREPOLICY` for a restart. |
| `-keep` | Keep intermediate files for debugging. |
| `-version all` | Print engine, rules-engine and flow-model build information. |
| `-help` | Print the full option list. |

A successful run ends with `****  NORMAL STOP IN EXECUTION  ****` in the `.out`
file and console, and exit code `0`.

**Run with the working directory set to the case directory.** OLGA resolves
relative references such as `FILES PVTFILE=(./fluid.tab)` against the current
directory, not against the case file location. `OlgaRunner.run` does this for you.

## Exit Codes

OLGA reports the outcome through the process exit code, grouped by category. The
full table is embedded in `runner.EXIT_CODES` (transcribed from
`exit_code_lookup.exe list`), so it can be decoded offline. The ones you will
actually meet:

| Code | Name | Meaning and first action |
| --- | --- | --- |
| 0 | `OK` | Normal stop. |
| 17 | `CMDLINE_FAILED` | Illegal command line — check flag spelling and that the case is last. |
| 20 | `INIT_FAILED` | Initialization failed — read the `.out` header. |
| 21 | `RESTART_FAILED` | Restart file missing or inconsistent with the case. |
| 22 | `SSPP_FAILED` | Steady-state pre-processor failed — boundary conditions inconsistent. |
| 23 / 34 | `FLUID_FAILED` / `PVT_FAIL` | PVT table missing, unreachable, or outside its P/T range. |
| 26 | `LICENSE_FAIL` | Licence checkout failed — check `LM_LICENSE_FILE` and server reachability. |
| 35–40 | `WAX_/PLUGIN_/ROCX_/SLUG_/TRACER_/PROCEQ_FAIL` | The named submodel failed. |
| 65–73 | `PT_*`, `TM_*`, `H_*` | Pressure/temperature/enthalpy out of range or NaN — the solution diverged. |
| 97–101 | internal errors | Reproduce with `-keep` and escalate to the vendor. |

Codes 65–73 mean the *physics or numerics* failed, not the input. Reduce `MAXDT`,
check for a closed boundary, an unphysical source, or a `MASSFLOW` boundary that
cannot be met, and re-run with a shorter `INTEGRATION ENDTIME` to isolate the time
of failure.

## Result File Format

Both `.tpl` and `.ppl` are ASCII with the same header, then a `CATALOG` of
variables, then numbers:

```
'OLGA 2025.1.0.24773'
TIME PLOT                              (or PROFILE PLOT)
INPUT FILE / PVT FILES / DATE / PROJECT / TITLE / AUTHOR
NETWORK
<nbranches>
GEOMETRY ' (M)  '
BRANCH
'<BRANCH NAME>'
<nsections>                            <- boundary points = nsections + 1
<x coordinates> <y coordinates>
CATALOG
<nvariables>
PT 'BOUNDARY:' 'BRANCH:' 'PIPELINE' '(PA)' 'Pressure'
TIME SERIES  ' (S)  '
<numbers>
```

- In a `.tpl`, each data row is `time` then **one scalar per catalog entry**.
- In a `.ppl`, each time step is the `time` value then **one full profile per
  catalog entry**: `nsections + 1` values for a `BOUNDARY:` variable and
  `nsections` values for a `SECTION:` variable of that variable's branch.

Values wrap across lines freely, so parse the data block as one number stream and
consume it with the counts above — that is what `read_tpl` / `read_ppl` do.

The header also carries each branch's geometry: the distance along the branch and
the elevation at every section boundary. `OlgaBranch.x` / `.y` expose them, and
`ProfileData.positions(name)` returns the abscissa that matches a given profile
(boundaries for a `BOUNDARY:` variable, section centres for a `SECTION:` one).
Without it a profile is just a list of numbers — you cannot plot it, and you
cannot tell which end is the wellhead. Check the sign of `branch.y` rather than
assuming index 0 is the inlet.

**Units are per variable, and they are not one consistent system.** In the same
file OLGA reports `PT` in `PA` but `TM` in `C`. Always read `OlgaVariable.unit`
and convert from that; assuming SI throughout turns a 16.8 °C fluid into
−256 °C.

## Python Usage Pattern

```python
from olga_multiphase_simulator import (
    OlgaRunner, find_olga_installations, read_ppl, read_tpl, write_variant,
)

# 1. Which OLGA versions are installed?
for installation in find_olga_installations():
    print(installation.version, installation.engine)

# 2. Cheap input validation first (seconds, not hours).
runner = OlgaRunner(default_nthreads=4)          # newest version by default
check = runner.rule_check("case.genkey")
assert check.succeeded, check.stdout[-2000:]

# 3. Run, then decode the outcome.
result = runner.run("case.genkey", timeout=3600)
print(result.summary())                          # JSON-ready, for results.json
if not result.succeeded:
    print(result.category, result.code_name, result.description)

# 4. Post-process.
trend = read_tpl(result.outputs["tpl"])
print(trend.time_unit, trend.names())
print(trend.final("PT"), trend.variables[0].unit)

profile = read_ppl(result.outputs["ppl"])
pressure = profile.profile("PT", time_index=-1, branch="PIPELINE")
distance = profile.positions("PT", branch="PIPELINE")   # matching abscissa, m
```

Enable output on a case that has none. `TRENDDATA` / `PROFILEDATA` inside the
network components is not enough — without the global keywords OLGA writes no
`.tpl` / `.ppl` at all:

```python
from olga_multiphase_simulator import apply_parameters, ensure_statement

text = Path("case.genkey").read_text()
text = apply_parameters(text, {"INTEGRATION": {"ENDTIME": "120 s"}})
for statement in ("TREND DTPLOT=20 s", "PROFILE DTPLOT=60 s"):
    text = ensure_statement(text, statement, after_keyword="INTEGRATION")
```

Parametric sweep — write a variant **next to the original** so its relative `.tab`
references still resolve, then run each variant into its own output directory:

```python
for endtime in ("1 h", "6 h", "24 h"):
    variant = write_variant(
        "case.genkey",
        f"case_{endtime.replace(' ', '')}.genkey",
        {"INTEGRATION": {"ENDTIME": endtime}},
    )
    runner.run(variant, out_dir=f"runs/{variant.stem}")
```

`genkey.get_parameter` / `set_parameter` edit exactly one value and leave every
other byte untouched, handle `\`-continuation lines, skip `!` comments, and
support repeated keywords through `occurrence=`. `ensure_statement` adds a
missing global statement. None of them validate physics — always `rule_check`
the variant before running it.

The bundled sample library under `Data/OPG Files` is a good end-to-end test, but
most samples ship only as `.opi` GUI projects. `Well/Well-CleanUp_T` includes a
generated `.key`, so it is the one case that runs in batch without opening the
GUI first.

For large designed experiments, OLGA also ships its own parameter-study module
(`Modules/RmoParameterStudy`), which is the right tool when the study must be
reproduced inside the GUI.

## Authoring a Case From Scratch

A hand-written `genkey` must use OLGA's network structure. A flat list of
`NODE` / `BRANCH` / `PIPE` statements is rejected with *"No network components
found in the input file"*. The minimum viable single-line case is:

```
CASE AUTHOR="...", TITLE="..."
OPTIONS TEMPERATURE=WALL, COMPOSITIONAL=OFF, STEADYSTATE=ON
FILES PVTFILE="fluid.tab"
INTEGRATION ENDTIME=12 h, STARTTIME=0 s, MINDT=0.001 s, MAXDT=10 s, DTSTART=0.001 s
OUTPUT DTOUT=12 h
TREND DTPLOT=1800 s
PROFILE DTPLOT=1800 s
MATERIAL LABEL="STEEL", TYPE=SOLID, CAPACITY=500 J/kg-C, CONDUCTIVITY=45 W/m-C, DENSITY=7850 kg/m3
WALL LABEL="PIPEWALL", THICKNESS=(0.02) m, MATERIAL=("STEEL")

NETWORKCOMPONENT TYPE=FLOWPATH, TAG=FLOWPATH_1
 PARAMETERS LABEL="EXPORTLINE"
 BRANCH FLUID="NewFluid"
 GEOMETRY LABEL="ROUTE", XSTART=0 m, YSTART=-307 m, ZSTART=0 m
 PIPE LABEL=PIPE_01, ROUGHNESS=4.5e-05 m, DIAMETER=0.355 m, WALL="PIPEWALL", \
      NSEGMENT=5, LSEGMENT=(738.45, 738.45, 738.45, 738.45, 738.45) m, \
      XEND=3692.26 m, YEND=-294.8 m, ZEND=0 m
 HEATTRANSFER LABEL="SEABED", PIPE=ALL, HOUTEROPTION=HGIVEN, \
              HAMBIENT=3.2 W/m2-C, TAMBIENT=4 C, HMININNERWALL=10 W/m2-C
 SOURCE LABEL="FEED", PIPE=PIPE_01, SECTION=1, TIME=0 s, \
        MASSFLOW=101.1 kg/s, TEMPERATURE=40 C, GASFRACTION=1 -
 INITIALCONDITIONS PRESSURE=70 bara, TEMPERATURE=40 C, VOIDFRACTION=1 -
 OUTPUTDATA VARIABLE=(PT, TM, HOL, ID, USG, USL)
 PROFILEDATA VARIABLE=(PT, TM, HOL, ID, USG, USL, ROG, ROHL)
 TRENDDATA PIPE=PIPE_01, SECTION=5, VARIABLE=(PT, TM, HOL, USG, USL)
ENDNETWORKCOMPONENT

NETWORKCOMPONENT TYPE=NODE, TAG=NODE_INLET
 PARAMETERS LABEL="INLET", TYPE=CLOSED, X=0 m, Y=-307 m, Z=0 m
ENDNETWORKCOMPONENT

NETWORKCOMPONENT TYPE=NODE, TAG=NODE_OUTLET
 PARAMETERS LABEL="OUTLET", TYPE=PRESSURE, X=73845 m, Y=-300 m, Z=0 m, \
            PRESSURE=70 bara, TEMPERATURE=4 C, GASFRACTION=1 -, FLUID="NewFluid"
ENDNETWORKCOMPONENT

CONNECTION TERMINALS = (NODE_INLET FLOWTERM_1, FLOWPATH_1 INLET)
CONNECTION TERMINALS = (NODE_OUTLET FLOWTERM_1, FLOWPATH_1 OUTLET)

ENDCASE
```

Rules learned the hard way (each one was a rules-engine rejection):

- Keyword names are **singular** on `WALL`: `THICKNESS=`, `MATERIAL=` — not
  `THICKNESSES`/`MATERIALS`. `MATERIAL` needs `TYPE=SOLID` and `W/m-C`.
- `SOURCE` has no `FLUID=` key. The fluid comes from the `BRANCH FLUID=` label.
- `INTEGRATION` has no `NSLUG` key in 2025.1.
- Global statements (`OPTIONS`, `FILES`, `INTEGRATION`, `OUTPUT`, `TREND`,
  `PROFILE`, `MATERIAL`, `WALL`) go before the network components;
  `CONNECTION` statements go after them.
- **Iterate against `-exitRC`.** The rules engine names the offending key and its
  owner, e.g. `1019: Key not found. (FLUID for SOURCE EXPORTFEED in FLOWPATH
  EXPORTLINE)`. Treat it as the authority rather than guessing from documentation.

### Posing the boundary conditions

OLGA cannot fix inlet pressure, inlet temperature and flow rate at the same
boundary the way a steady-state marching model such as `PipeBeggsAndBrills` can.
To reproduce a NeqSim case that specifies all three, use a `SOURCE` for mass flow
and temperature plus a `TYPE=PRESSURE` outlet node, then iterate the outlet
pressure until OLGA's computed inlet pressure matches the NeqSim specification.
A secant iteration converges in three or four runs. Do not compare an OLGA run
against a NeqSim run at a different pressure level: gas friction scales roughly
as `G²/ρ`, so the pressure level materially changes the answer.

**The `SOURCE` phase split is an input, and it is easy to get wrong.**
`GASFRACTION` on a `SOURCE` is a **mass** fraction and it *overrides* the table
equilibrium. Writing `GASFRACTION=1` feeds OLGA dry gas. If the compositional
model flashes two phases at the inlet, the two cases are then not comparable —
a rich gas at 200 bara / 40 °C can be 99.5 % gas by mole but only 97.4 % by mass,
so `GASFRACTION=1` silently deletes 2.6 % of the mass as condensate. Always take
the gas **mass** fraction from a NeqSim flash at the source conditions:

```python
fluid.setTemperature(313.15); fluid.setPressure(200.0)
ThermodynamicOperations(fluid).TPflash(); fluid.initProperties()
total = sum(fluid.getPhase(i).getNumberOfMolesInPhase()
            * fluid.getPhase(i).getMolarMass()
            for i in range(fluid.getNumberOfPhases()))
gas_mass_fraction = (fluid.getPhase(0).getNumberOfMolesInPhase()
                     * fluid.getPhase(0).getMolarMass()) / total
```

### Proving the two models see the same input

Before reporting any OLGA-versus-other-simulator comparison, verify each item
below with a number rather than by inspection of the input files:

| Input | How to prove it |
| --- | --- |
| Composition | Same source file (hash it), and the PVT table reproduces a direct flash density at the inlet, mid-line and arrival states |
| Mass rate | `SOURCE MASSFLOW` equals the other model's mass rate, not just the same volumetric rate — a standard-volume rate depends on the molar mass |
| Inlet phase split | `GASFRACTION` equals the flashed gas **mass** fraction |
| Diameter and roughness | The set of `DIAMETER=` and `ROUGHNESS=` values in the genkey is a single value matching the other model |
| Length | Sum of pipe lengths equals the other model's total, including elevation |
| Pressure level | Inlet pressures agree after the outlet-pressure iteration |
| Ambient | `TAMBIENT` and the `U`-to-`HAMBIENT` mapping stated explicitly |

A 0.01 % density agreement between the table and a direct flash is the check that
turns "same fluid file" into "same fluid".

### Generating the PVT table from NeqSim

```python
generator = jneqsim.thermodynamicoperations.propertygenerator \
    .OLGApropertyTableGeneratorKeywordFormat(fluid)
generator.setPressureRange(5.0, 260.0, 41)          # bara
generator.setTemperatureRange(233.15, 353.15, 31)   # K
generator.run()
generator.writeOLGAinpFile("linnorm.tab")
```

- Use `OLGApropertyTableGeneratorKeywordFormat` (emits `PHASE = TWO`) for a dry
  line. `OLGApropertyTableGeneratorWaterKeywordFormat` emits `PHASE = THREE` and
  throws a `NullPointerException` unless the fluid contains a `water` component.
  It is the **only** water generator that works end to end with the plain
  `run()` + `writeOLGAinpFile()` sequence; `OLGApropertyTableGeneratorWaterEven`
  throws `NullPointerException` on `bubPLOG` unless `calcPhaseEnvelope()` is
  called first, and its `run()` then throws
  `IsNaNException: molarVolumeAnalytical - compressibility factor is NaN`.
- For a `PHASE = THREE` table set `OPTIONS COMPOSITIONAL=OFF` and give the source
  only `MASSFLOW=` and `TEMPERATURE=` — do **not** set `GASFRACTION`, the table
  supplies the phase split. The water profile variables are `HOLWT` (water
  holdup) and `HOLHL` (hydrocarbon-liquid holdup); `UHL` and `UWT` are not valid
  `PROFILEDATA` names and are silently dropped with a warning.
- Cover the whole P/T range the line will visit, including Joule-Thomson cooling
  at the arrival end; an out-of-table state gives exit 23/34.
- Always check the file exists and spot-check `ROG`/`ROHL`/`VISG` for NaNs before
  handing it to OLGA. At single-phase grid points the generator still reads
  `getPhase(1)`, so the "liquid" columns there are extrapolations.
- Requires NeqSim with the 2026-08 fixes to these generators (honouring the
  `filename` argument and writing paired `BUBBLEPRESSURES`/`BUBBLETEMPERATURES`).

### Discretising the geometry

**OLGA's batch engine does not discretise.** It consumes a `PIPE` list that already
carries `NSEGMENT` and `LSEGMENT`. OLGA's own "discretize geometry" lives in the
Geometry editor and `Tools/ProfileGenerator/ProfileGeneratorTool.exe`, both of
which are GUI-only — the tool has no command line and simply opens a window if you
pass it arguments. So an automated workflow has to produce the section list itself.

Use `discretize_route` rather than hand-picking `NSEGMENT`:

```python
from olga_multiphase_simulator.geometry import discretize_route

mesh = discretize_route(
    kp, elevation,                      # route waypoints, m
    target_section_length=500.0,
    boundary_section_length=100.0,      # grade toward inlet and outlet
    max_adjacent_ratio=1.5,             # limit the jump between neighbours
    refine_low_points=True,             # refine where liquid accumulates
)
print(mesh.summary())
genkey_pipes = mesh.to_genkey(diameter_m=0.355, roughness_m=4.5e-5,
                              wall_label="PIPEWALL")
```

`summary()` returns the numbers to record with the run: `total_sections`,
`min_section_length_m`, `max_section_length_m` and `max_adjacent_ratio`. The
ratio is enforced across pipe boundaries as well as inside a pipe, because a step
change in section length is a numerical error source, and pipe lengths follow the
route including elevation change, not the horizontal distance.

A uniform "N sections per leg" mesh is the usual shortcut and the usual mistake:
on a survey-derived route the legs are unequal, so a fixed count produces a
section-length jump at every leg boundary. Always report the mesh statistics, and
demonstrate grid independence by halving the target section length and confirming
the answer moves less than the accuracy being claimed.

## Working With NeqSim

OLGA and NeqSim are complementary; use each for what it is good at.

| Question | Tool |
| --- | --- |
| Transient liquid surge, terrain slugging, shut-in/restart, blowdown dynamics | OLGA |
| Steady-state pressure drop and holdup screening | NeqSim `PipeBeggsAndBrills`, `AdiabaticTwoPhasePipe` |
| Phase envelope, hydrate curve, wax appearance temperature, fluid properties | NeqSim thermodynamics |
| Topside process response to an arriving slug | NeqSim `ProcessSystem` / `runTransient` |

Typical composition: NeqSim characterises the fluid and produces the hydrate and
wax envelopes, OLGA transports it transiently, and the OLGA arrival trends
(`PT`, `TM`, liquid rates) become the boundary condition for the NeqSim topside
model. Screen first with the community flow-regime and slug skills; escalate to
OLGA only when the transient actually matters.

### When the two models disagree, audit the correlation term by term

A headline gap in ΔP or holdup is not evidence of a bug in either code, and it
is not evidence of a modelling limitation either — until the intermediate terms
have been compared. Do this before writing either conclusion:

1. Reimplement the steady-state correlation from the **published equations** in
   a few dozen lines of Python, driven from the *same* flashed NeqSim fluid
   object so composition and properties cannot differ.
2. Run the simulator on a **short, single-increment** pipe (1 m, one segment).
   A long segment lets the pressure change within the increment shift the state
   at which the correlation is evaluated; a 10% holdup deviation seen over a
   100 m segment vanished entirely at 1 m.
3. Compare every intermediate, not just the answer: no-slip liquid fraction,
   Froude number, the regime-boundary numbers, the horizontal holdup, the
   velocity number, the inclination factor, the two-phase friction multiplier,
   the no-slip friction factor, then ΔP.
4. Sweep the **inclination** as well as the horizontal case. Terms that only
   appear in the inclination correction are invisible in a horizontal test, and
   they are raised to powers as high as 3.8, so a small input error becomes a
   large output error.

This procedure found four real defects in `PipeBeggsAndBrills` that a
horizontal end-to-end comparison had hidden: a pipe angle converted from
degrees to radians twice, a distributed-regime boundary tested against the
wrong limit, gravity counted twice in the liquid velocity number, and a
volume-corrected density mixed with an uncorrected one inside a single formula.

Two residual differences are expected and are *not* defects:

- Beggs & Brill was calibrated on small-bore air/water loops, for no-slip liquid
  fractions down to roughly 0.01–0.02. A large-bore high-pressure gas line
  carrying a few mass per cent of condensate runs *below* that range, so the
  two-phase friction multiplier is being extrapolated. On a 74 km 14-inch line
  at a mean no-slip liquid fraction of 0.009 the multiplier reached 1.42, which
  accounted for the **entire** difference against the transient two-fluid model:
  removing it brought the correlation from 124 bar to 87 bar against OLGA's
  78 bar and a single-phase Darcy check of 84 bar.
- A mechanistic two-fluid code computes an interfacial friction close to
  single-phase in this regime, because the condensate rides as a thin film
  rather than loading the gas core.

Do **not** reach for the Payne et al. (1979) holdup correction to explain such a
gap without checking the numbers. The Beggs & Brill `S` factor is monotonically
*increasing* in `y = λ_L / H_L²` over this range, so reducing the holdup
*raises* the friction multiplier: 0.0795 gave 1.42, the Payne-corrected value
gave 1.51, and the two-fluid code's own holdup of 0.023 would give 2.43. The
defect is in the multiplier's applicability at low liquid loading, not in the
holdup value.

Always run an independent single-phase Darcy–Weisbach hand check at the same
pressure level as a third opinion; it tells you which of the two simulators the
discrepancy belongs to.

### Use NeqSim's own two-fluid model as the fourth opinion

`neqsim.process.equipment.pipeline.TwoFluidPipe` is a mechanistic two-fluid
model — the same modelling class as OLGA — so it discriminates between "the
correlation is being extrapolated" and "NeqSim has a bug" without leaving
NeqSim. On the 74 km line above:

| | OLGA | TwoFluidPipe | Beggs & Brill | Darcy check |
| --- | --- | --- | --- | --- |
| pressure drop, bar | 78.5 | **81.2 (+3.4%)** | 125.0 (+59.2%) | 77.7 |
| arrival temperature, °C | 8.4 | 6.8 | −6.7 | – |
| max liquid holdup | 0.023 | 0.064 | ~0 | – |

Two mechanistic codes and a hand calculation agree; the correlation is the
outlier. That settled the question.

```python
pipe = jneqsim.process.equipment.pipeline.TwoFluidPipe("line", inlet_stream)
pipe.setLength(length_m)
pipe.setDiameter(id_m)
pipe.setRoughness(4.5e-5)
pipe.setNumberOfSections(320)
pipe.setElevationProfile(elevations)          # needs numberOfSections + 1 values
pipe.setIncludeEnergyEquation(True)
pipe.setHeatTransferCoefficient(3.0)          # W/m2K
pipe.setSurfaceTemperature(4.0, "C")
pipe.run()
assert pipe.isSteadyStateConverged()          # ALWAYS check this
profile = pipe.getPressureProfile()           # Pa
dp_bar = (profile[0] - profile[-1]) / 1e5
```

- **Always assert `isSteadyStateConverged()`.** The steady-state refinement loop
  is an under-relaxed fixed-point sweep; if it runs out of iterations it returns
  the last iterate, which can be an order of magnitude wrong. Raise the budget
  with `setSteadyStateMaxIterations(int)` if needed. The default budget scales
  with the section count.
- **Demonstrate grid independence.** A 74 km line gave 80.39 / 80.93 / 81.20 bar
  at 80 / 160 / 320 sections — Richardson-extrapolates to about 81.5 bar. It
  solves in under a second, so there is no excuse for a single-mesh answer.
- Profiles available: `getPressureProfile()` (Pa), `getLiquidHoldupProfile()`,
  `getGasVelocityProfile()`, `getLiquidVelocityProfile()`,
  `getFlowRegimeProfile()`. There is no `getMixtureVelocityProfile()`. The model
  is correctly insensitive to the elevation datum, so absolute seabed depths may
  be passed directly.
- Arrival **temperature** agrees with OLGA to about 1.6 °C on this line (6.8 °C
  against 8.4 °C). If you see a much warmer arrival temperature, you are on an
  older NeqSim in which the Joule-Thomson term was silently dropped — check it
  with an adiabatic run (`setHeatTransferCoefficient(0)`) against an isenthalpic
  PH flash to the same outlet pressure, which is the exact reference.

## Validation Checklist

- [ ] The engine used is `OlgaExecutables/Olga-<version>.exe`, not an `OLGA-S` path.
- [ ] The case was rule-checked (`-exitRC`) before the full run.
- [ ] The working directory was the case directory, so relative `.tab` paths resolved.
- [ ] Exit code is 0 **and** the `.out` file ends with `NORMAL STOP IN EXECUTION`.
- [ ] The engine version and case file name are recorded with the results.
- [ ] Result units were read from the catalog, not assumed.
- [ ] Profiles were reported against `positions(...)`, and the shallow end was
      identified from `OlgaBranch.y` rather than assumed to be section 0.
- [ ] Reported values are at output times that exist in the file, not interpolated silently.
- [ ] The PVT table covers the full P/T range reached, and its density and
      viscosity columns were spot-checked for NaNs before the run.
- [ ] The mesh came from `discretize_route`, its `summary()` was recorded, and
      grid independence was demonstrated by halving the target section length.
- [ ] When benchmarking against another model, every row of the input-equivalence
      table was proved with a number: composition, mass rate, inlet phase split,
      diameter, roughness, length, pressure level and ambient conditions.
- [ ] Any headline disagreement was audited term by term against the published
      correlation on a short single-increment segment, over a range of
      inclinations, and cross-checked against a single-phase Darcy hand
      calculation before being attributed to either code.
- [ ] If a `TwoFluidPipe` result was used as a cross-check, `isSteadyStateConverged()`
      returned true and the answer was shown to be grid-independent over at least
      two mesh refinements.
- [ ] The comparison covers **more than one rate**, and the rate exponent `n` in
      `dP ~ rate^n` was compared as well as the level. A model that reproduces one
      operating point can still have the wrong sensitivity.
- [ ] A **single-phase** variant of the case was run first, so that friction and the
      energy equation were validated before any two-phase closure was judged.
- [ ] Any rate that failed to converge was shown to be a deliverability limit
      (a large change in the arrival boundary barely moves the inlet) rather than
      a solver problem.
- [ ] A qualified flow-assurance engineer reviewed the interpretation.

## Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Exit 26 `LICENSE_FAIL` | Licence server unset or unreachable | Check `LM_LICENSE_FILE`; use `license_environment()` to see what is set |
| Exit 23/34 fluid failure | PVT `.tab` not found, or state outside the table | Run from the case directory; widen the table P/T range |
| Exit 17 `CMDLINE_FAILED` | Case file not last, or a mistyped flag | Build the command with `OlgaRunner.build_command` |
| No `.tpl` or `.ppl` produced | No global `TREND` / `PROFILE` `DTPLOT` keyword in the case | Add them with `ensure_statement`; `TRENDDATA`/`PROFILEDATA` alone is not enough |
| Temperatures come out near −256 °C | `TM` is already in `C`, but the code subtracted 273.15 | Convert from `OlgaVariable.unit`; units differ per variable in one file |
| Profile plotted against index | The abscissa was never read | Use `ProfileData.positions(name)`; it matches the profile length |
| "Wellhead" pressure looks like a downhole one | Section 0 is not always the top | Check `OlgaBranch.y` to find which end is shallow |
| Exit 65–73 | Numerical divergence, not bad input | Reduce `MAXDT`, shorten `ENDTIME` to bracket the failure, check boundaries |
| Parser reports trailing values | The run was killed mid-write | Re-run to completion; a partial `.ppl` has an incomplete final time block |
| Editing the `.opi` has no effect | The engine reads the generated `.genkey` | Automate the `.genkey`; regenerate it from the GUI when the topology changes |
| Results changed after a version upgrade | Different flow-model build | Record `-version all` output alongside the results |
| `No network components found in the input file` | Flat `NODE`/`BRANCH`/`PIPE` list | Wrap them in `NETWORKCOMPONENT ... ENDNETWORKCOMPONENT` and add `CONNECTION` statements |
| `1019: Key not found` | Keyword name or owner is wrong for this OLGA version | Read the owner named in the message; fix and re-run `-exitRC` |
| `BUBBLETEMPERATURES and BUBBLEPRESSURES need to have the same size` | PVT table saturation arrays are not paired | Regenerate with a NeqSim build that writes equal-length paired arrays |
| NeqSim wrote no `.tab` and raised nothing | Older NeqSim ignored the `filename` argument and swallowed the write error | Verify the file exists after `writeOLGAinpFile`; upgrade NeqSim |
| OLGA and a steady-state model disagree on ΔP | Often a different pressure level, not a model difference | Match the inlet pressure by iterating the outlet boundary before comparing |
| OLGA carries far less liquid than the compositional model | `SOURCE GASFRACTION=1` fed dry gas and overrode the table equilibrium | Set `GASFRACTION` to the flashed gas **mass** fraction |
| Looking for a batch "discretize geometry" command | OLGA's discretiser is GUI-only | Build the section list with `discretize_route` |
| Section length jumps at every leg boundary | A fixed `NSEGMENT` per leg on unequal legs | Use a target section length and the neighbour-ratio limit |
| Steady-state holdup barely changes when the pipe is inclined | The correlation's inclination correction is being suppressed | Sweep the angle and compare against the published correction; a near-constant holdup means the term is broken, not small |
| A correlation audit shows a few per cent deviation that will not close | The reference was evaluated at the inlet but the simulator evaluated it after the pressure change across the increment | Shrink the test segment to ~1 m with one increment |
| Liquid-property terms disagree by ~20% for no visible reason | `phase.getDensity()` and `phase.getDensity("kg/m3")` differ when volume correction is on | Use the explicit-unit accessor everywhere; never mix the two in one formula |
| `TwoFluidPipe` ΔP is several times below a Darcy hand check on a long line | The steady-state loop ran out of iterations and returned the last iterate | Assert `isSteadyStateConverged()`; raise `setSteadyStateMaxIterations(int)` |
| `TwoFluidPipe` liquid holdup pins near 0.85, or ΔP jumps for a tiny elevation change | Fixed in NeqSim: the initializer and the refinement loop integrated different discrete momentum balances, so terrain hydrostatics stopped telescoping | Rebuild against current NeqSim; both call sites now share `marchPressure` |
| `TwoFluidPipe` arrival temperature is far warmer than OLGA | Fixed in NeqSim: the Joule-Thomson term was gated behind the heat-transfer coefficient and zeroed by a `1<Cp/Cv<2` guard that a two-phase mixture never satisfies | Rebuild against current NeqSim; verify with an adiabatic run against an isenthalpic PH flash |
| The outlet-pressure secant runs away and OLGA exits 68 `TM_BELOW` | The requested rate is beyond the line's deliverability, so no arrival pressure reproduces the target inlet; the secant then drives the arrival down until Joule-Thomson cooling leaves the PVT table | Bound the secant to a physically sensible arrival pressure and report the deliverability limit instead. The tell is that a large step in the arrival boundary moves the inlet only slightly (8 bar out, 2 bar in) |
| Two models agree at one rate and are compared no further | A single operating point cannot separate a friction-model error from a hold-up error | Run a rate sweep and compare the **exponent** `n` in `dP ~ rate^n`, not just the level. For a real gas line `n > 2`, because the density falls as the pressure drops along the line |
| A steady-state model's hold-up is several times OLGA's but the pressure drops agree | On a near-horizontal, friction-dominated line the hold-up barely enters the pressure balance | Do not treat pressure-drop agreement as hold-up validation. Report the slip ratio `u_g/u_l = ((1-lambda)/(1-H))*(H/lambda)` alongside; wet-gas values around 3 are typical, 10 indicates a closure problem |
| A hold-up maximum looks alarming but the mean is fine | One terrain-trap section, not a global bias | Compare mean, median and p90, and re-run with terrain tracking off; if the median is unchanged the maximum is a single trap |
| `SOURCE: The following keys must have equal list length` | A transient `SOURCE` was given `TIME=(0, t)` but scalar `TEMPERATURE`/`GASFRACTION` | Every list-valued key on that `SOURCE` must have the same length as `TIME`; repeat the constant ones, e.g. `TEMPERATURE=(40, 40) C` |
| A two-phase benchmark disagrees and every closure is suspect at once | The comparison mixes friction, hold-up, slip and the energy equation | Build a **single-phase** version of the same case first (strip the heavy ends so the fluid stays one phase over the whole P/T window, and set `SOURCE GASFRACTION=1`). Any deviation is then friction or energy alone. Confirm the table really is single phase by checking that the OLGA `HOL` profile is ~1e-16 |
| A steady-state model's deviation does not shrink with mesh refinement | It is a model or closure error, not truncation | Stop refining. Recompute the pressure drop from the model's OWN reported profile (pressure, temperature, velocity, with density from a flash at each section state). If that disagrees with what the model reports, the model's state and its pressure are mutually inconsistent |
| Need to know which property a marching solver actually used | Invert the reported step | `rho_used = f * G^2 * dx / (2 D dP_i)` for a single-phase gas line. A value that is constant along the pipe and equal to the inlet density means the properties were never fed back into the momentum balance |

## Limitations

- Windows-oriented discovery; on Linux clusters set `OLGA_ENGINE` explicitly.
- `genkey` editing is a targeted text rewrite, not a validating parser: it cannot
  add keywords, change topology, or check units.
- Only ASCII `.tpl`/`.ppl` are read; binary `.plt` and `.h5` are not parsed here
  (use OLGA Viewer or the vendor API).
- Result units are reported as declared; no unit system is imposed.
- No physics is interpreted, checked or corrected by this skill.
- Results depend on the OLGA version and licensed modules; both must be reported.

## References

- OLGA user documentation shipped with the installation
  (`Documentation/OLGAHelp.chm`, `OLGAGUIHelp.chm`, release notes).
- `Olga-<version>.exe -help` and `exit_code_lookup.exe list` for the authoritative,
  version-specific option and exit-code lists.
- NeqSim repository: https://github.com/equinor/neqsim
- NeqSim Skills Guide: https://github.com/equinor/neqsim/blob/master/docs/integration/skills_guide.md
