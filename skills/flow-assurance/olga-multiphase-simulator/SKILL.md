---
name: neqsim-olga-multiphase-simulator
version: "0.1.0"
description: "Run the OLGA transient multiphase flow simulator from Python: locate the installation, generate its PVT table and hydrate equilibrium curve from a NeqSim fluid, validate a genkey case with a rule check, launch the batch engine with the right flags, decode the engine exit code, and read .tpl trend and .ppl profile results. USE WHEN: a task must execute an OLGA case, batch or sweep OLGA runs, build a two- or three-phase OLGA PVT table or a HYDRATECURVE for HYDRATECHECK, diagnose an OLGA failure or licence error, or benchmark OLGA against the NeqSim pipeline models (TwoFluidPipe, PipeBeggsAndBrills) so that a multiphase flow result can be quoted with a known accuracy."
last_verified: "2026-08-15"
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
- An OLGA case needs a PVT table or a hydrate equilibrium curve generated from a
  NeqSim fluid, so that OLGA and NeqSim share one fluid and one hydrate boundary.
- A parametric or sensitivity sweep must be run reproducibly rather than by hand
  in the GUI.
- An OLGA run failed and the exit code, log or licence state must be diagnosed.
- OLGA results must be compared against NeqSim screening or pipeline models.

Do **not** use this skill to invent a case from scratch, to guess PVT tables, or
to interpret a transient result without a flow-assurance engineer in the loop.

## Inputs

- `case`: path to the `.genkey` / `.key` keyword file the batch engine reads. The
  GUI `.opi` project is **not** an engine input — generate the `genkey` from it first.
- `pvt_file`: the `.tab` PVT table referenced by `FILES PVTFILE=`, resolved
  relative to the working directory. Generated from a NeqSim fluid (two- or
  three-phase) so OLGA and NeqSim share one fluid.
- `hydrate_curve`: optional hydrate equilibrium curve for `HYDRATECHECK`, also
  generated from the same NeqSim fluid.
- `restart_file`: optional `.rsw` snapshot for a restart (`RESTART READFILE=ON`).
- `parameters`: mapping of `{KEYWORD: {ATTRIBUTE: value}}` overrides applied by
  `apply_parameters` / `set_parameter` / `write_variant` for sweeps, e.g.
  `{"INTEGRATION": {"ENDTIME": "6 h"}}`.
- `out_dir`: output directory for the run (`-outDir`); defaults to the case directory.
- `nthreads`: thread count for parallel execution (`-nthreads`).
- `timeout`: wall-clock limit in seconds after which the run is terminated.
- `olga_home` / `olga_engine`: optional explicit installation or engine path;
  otherwise `OLGA_HOME` / `OLGA_ENGINE` or installation discovery is used.
- Licence environment: `LM_LICENSE_FILE` or `SLBSLS_LICENSE_FILE`, plus a
  reachable licence server when the licence is served rather than node-locked.

## Outputs

- `installations`: `OlgaInstallation` records from `find_olga_installations()` —
  version, root and batch-engine path for every OLGA found on the machine.
- `rule_check`: `OlgaRunResult` from the `-exitRC` input-rule pass, with
  `succeeded` and the engine stdout.
- `run_result`: `OlgaRunResult` with `case`, `out_dir`, `command`, `returncode`,
  `category`, `code_name`, `description`, `duration_s`, `stdout`, `timed_out`,
  and `outputs` (the `.out`, `.tpl`, `.ppl`, `.plt`, `.h5` files produced).
  `summary()` returns a JSON-ready dict for `results.json`.
- `trend`: `TrendData` from `read_tpl` — time vector, `time_unit`, and one
  `OlgaVariable` per catalog entry with its own `unit`; `final(name)` gives the
  end-of-run value.
- `profile`: `ProfileData` from `read_ppl` — spatial profiles per variable and
  time step, with `positions(name)` giving the matching abscissa in m.
- `branches`: `OlgaBranch` geometry (`x` distance along the branch, `y`
  elevation) read from the result header, needed to plot or orient a profile.
- `exit_code_decoding`: `describe_exit_code(code)` → `(category, name,
  description)`, resolved offline from the embedded `EXIT_CODES` table.

## Engineering Method

OLGA solves the transient one-dimensional two-fluid (three-phase) conservation
equations along a discretized pipe network. This skill does **not** reimplement
that physics — it drives the licensed engine and decodes what it produced:

- **Discovery.** Installations are located from `OLGA_HOME` / `OLGA_ENGINE`, then
  from the standard install roots, and the newest version is used by default. The
  `OLGA-S` point model (`OLGAS_SLB_x64`) is deliberately excluded: it is the
  steady-state model other hosts link against, not the transient engine.
- **Cheap validation before expensive runs.** Every case is first run with
  `-exitRC`, which parses keywords, units and topology in seconds. It does not
  open the PVT file and does not validate `TRENDDATA` / `PROFILEDATA` variable
  names, so the result-file `CATALOG` is read back afterwards to confirm every
  requested variable actually exists.
- **Execution.** The engine is launched with the working directory set to the
  case directory, so relative `FILES PVTFILE=` references resolve, with the case
  file last on the command line as the engine requires.
- **Outcome classification.** The process exit code is mapped through the table
  transcribed from `exit_code_lookup.exe` into a category, name and first action —
  separating input errors (17, 20–22), licence failures (26), PVT problems
  (23/34) and numerical divergence (65–73), which need different responses.
- **Discretization.** `discretize_route` turns a surveyed route into OLGA pipes
  and sections using a target section length with graded first-section lengths, a
  neighbour length-ratio limit, and refinement at local elevation minima where
  terrain slugging accumulates liquid.
- **Result decoding.** `.tpl` and `.ppl` share one ASCII header, geometry block
  and `CATALOG`; the data block is consumed as a single number stream using the
  catalog counts (`nsections + 1` values for a `BOUNDARY:` variable, `nsections`
  for a `SECTION:` one). Units are taken per variable from the catalog, because
  OLGA mixes systems in one file (`PT` in Pa, `TM` in °C).

The engine result is only as good as the case and its PVT table. This skill
gives a reproducible, decodable run — it is not a flow-assurance method and does
not replace a qualified flow-assurance review.

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

**What `-exitRC` does not check.** The rule check validates keywords, units and
topology — nothing else. Verified on OLGA 2025.1:

- It never opens the PVT file, so a broken or missing `.tab` still passes.
- It does not validate `PROFILEDATA` / `TRENDDATA` variable names at all. A
  deliberately invented name passes with `RuleCheck: OK`, exit 0 and **no
  message**, and is then silently dropped from the results. The only authority on
  which variables exist is the `CATALOG` block of the `.ppl` / `.tpl` after a real
  run — read it back and confirm every variable you asked for is there.
- It does not check that the physics is posed sensibly.

Treat a passing rule check as "the file parses", never as "the case is right".

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

Resolve the gas phase by **type** (`fluid.getPhaseOfType("gas")`) rather than by
index whenever the fluid may contain water — a flash returns only the phases that
exist, so index 0 is not reliably the gas.

**Three-phase sources: `GASFRACTION` and `WATERFRACTION` are on different bases.**
This is the single most expensive input error in this skill. When a `SOURCE`
carries both keys:

- `WATERFRACTION` is the aqueous mass fraction of the **total** stream;
- `GASFRACTION` is the gas mass fraction of the **hydrocarbon** part only, i.e.
  of what is left after the water is removed — *not* of the total.

Feeding the total-stream gas mass fraction alongside a `WATERFRACTION` runs
without any error or warning and produces a plausible-looking result. On a wet
gas line with 80.3 % water by mass, writing the total-basis 0.19147 next to
`WATERFRACTION=0.80333` gave `GAS 19.37 / OIL 81.79 kg/s` where the fluid should
have delivered `98.49 / 2.67` — a **30×** condensate error that still converged.

```python
# masses from a NeqSim TPflash at the source conditions
w_water = m_aqueous / m_total                       # -> WATERFRACTION
w_gas_hc = m_gas / (m_gas + m_oil)                  # -> GASFRACTION (HC basis)
```

**Always read the split back from the `.out` file before believing any
three-phase number.** OLGA echoes what it actually injected in a
`MASS SOURCE INFORMATION:` block giving `GAS / OIL / WATER` in kg/s per source;
check those three numbers against the NeqSim flash to within a per cent. A run
that passed `-exitRC` and exited 0 proves nothing about the phase split.

### Proving the two models see the same input

Before reporting any OLGA-versus-other-simulator comparison, verify each item
below with a number rather than by inspection of the input files:

| Input | How to prove it |
| --- | --- |
| Composition | Same source file (hash it), and the PVT table reproduces a direct flash density at the inlet, mid-line and arrival states |
| Mass rate | `SOURCE MASSFLOW` equals the other model's mass rate, not just the same volumetric rate — a standard-volume rate depends on the molar mass |
| Inlet phase split | `GASFRACTION` equals the flashed gas **mass** fraction (of the hydrocarbons only when `WATERFRACTION` is also set) |
| Injected phase rates | The `MASS SOURCE INFORMATION:` block in the `.out` file matches the NeqSim flash in kg/s for gas, oil and water |
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
generator.setFluidLabel("NewFluid")                 # must equal BRANCH FLUID=
generator.setPressureRange(5.0, 260.0, 41)          # bara
generator.setTemperatureRange(233.15, 353.15, 31)   # K
generator.run()
generator.writeOLGAinpFile("linnorm.tab")
```

- `OLGApropertyTableGeneratorKeywordFormat` emits `PHASE = TWO` and works for any
  fluid, with or without a water component.
  `OLGApropertyTableGeneratorWaterKeywordFormat` emits `PHASE = THREE` and
  requires a `water` component. It is the **only** water generator that works end
  to end with the plain `run()` + `writeOLGAinpFile()` sequence;
  `OLGApropertyTableGeneratorWaterEven` throws `NullPointerException` on
  `bubPLOG` unless `calcPhaseEnvelope()` is called first, and its `run()` then
  throws `IsNaNException: molarVolumeAnalytical - compressibility factor is NaN`.
- **`setFluidLabel` must match the genkey.** The label written into the table has
  to equal the `BRANCH FLUID=` (and outlet-node `FLUID=`) string, or OLGA cannot
  bind the table to the flowpath.
- For a `PHASE = THREE` table set `OPTIONS COMPOSITIONAL=OFF`. The water profile
  variables are `HOLWT` (water holdup) and `HOLHL` (hydrocarbon-liquid holdup);
  `UHL` and `UWT` are not valid `PROFILEDATA` names and are silently dropped with
  a warning.
- Cover the whole P/T range the line will visit, including Joule-Thomson cooling
  at the arrival end; an out-of-table state gives exit 23/34 (or 68 `TM_BELOW`
  when an iteration walks off the cold edge).
- Requires NeqSim with the 2026-08 generator fixes. Older builds ignored the
  `filename` argument (writing to a hardcoded path and swallowing the error),
  wrote `BUBBLEPRESSURES` and `BUBBLETEMPERATURES` with different lengths, and
  — the defect that made them unusable beyond a always-two-phase fluid — indexed
  phases by **array position** (0 = gas, 1 = oil, 2 = water) assuming all three
  existed. Because a flash returns only the phases that are present, every
  single-phase grid node wrote **zero** for the absent phase and OLGA refused the
  file with `ERROR IN THE INPUT FILE: OIL DENSITY IS ZERO AT: PRES.=... AND
  TEMP.=...`. Dry gas, dead oil and dense-phase CO₂ all failed to load, and a
  two-phase fluid failed at any grid corner outside its envelope. Current builds
  resolve phases by type, mark absent phases, and nearest-neighbour fill in
  grid-index space; mass fractions (`RS`, `RSW`) are deliberately left at zero
  where the phase is absent.

**A generated table is only validated when OLGA has actually loaded it.**
`-exitRC` does **not** read the PVT file, so a rule check passing says nothing
about the table. The two-stage harness that works:

1. Scan the written file for `NaN`, `Inf` and zero density/viscosity columns.
2. Run a throwaway minimal case — one flowpath, a `SOURCE`, a `TYPE=PRESSURE`
   outlet node, a few minutes of `ENDTIME` — against the table and require exit 0
   plus `NORMAL STOP IN EXECUTION`.

Exercise the fluid types the study will actually meet: dry gas, gas condensate,
black oil, dead oil, CO₂-rich, three-phase, gas+water without oil, oil+water
without gas, and a fluid with no water component at all.

#### Designing the P/T grid

The grid is the model. OLGA interpolates it, so a state the grid does not bracket
is either an extrapolation or a hard stop (exit 23/34 `FLUID_FAILED`/`PVT_FAIL`,
or 65–73 when an iteration walks off an edge).

- **Bracket the whole excursion, not the design point.** Include Joule-Thomson
  cooling at the arrival end, the seabed temperature, and any blowdown or
  shut-in the case will simulate. A line entering at 200 bara / 40 °C can arrive
  at 60 bara / −11 °C at high rate.
- **Give the pressure axis headroom above the inlet.** When the arrival boundary
  is iterated to match a target inlet, intermediate iterates overshoot; a table
  topping out at the design inlet aborts with `PRESSURE ABOVE TABLE VALUES`.
- **Use an asymmetric grid when testing a generator.** A square nP × nT grid
  hides transposed-index bugs.
- A 41 × 31 grid over 5–260 bara and 233–353 K is a workable starting point for a
  subsea gas export line.

### Hydrate input to OLGA

**OLGA does not compute hydrate thermodynamics.** It interpolates a tabulated
equilibrium curve that the case supplies, or falls back to the Hammerschmidt
correlation — a crude inhibitor shift. If the NeqSim side of a study uses a
rigorous CPA hydrate model and OLGA is left on its own default, the two halves of
the study disagree about where the hydrate boundary is, and the disagreement is
invisible in both sets of output.

Export the curve from the same fluid that produced the PVT table
(`neqsim.thermodynamicoperations.propertygenerator.OLGAhydrateCurveGenerator`):

```python
gen = jneqsim.thermodynamicoperations.propertygenerator \
    .OLGAhydrateCurveGenerator(fluid)          # fluid must contain water
gen.setCurveLabel("HYD")
gen.setPressureRange(10.0, 200.0, 21)          # bara, linear spacing
gen.run()
gen.writeOLGAinpFile("hydrate_curve.inp")
print(gen.getHydrateCheckKeyword())            # line to paste into the flowpath
```

It works on a clone, so the caller's fluid keeps its state, and it **drops**
pressures where the hydrate flash does not converge rather than writing a zero —
a zero temperature would silently move the boundary instead of failing. Check
`len(getCurvePressures())` against the number requested; a curve that lost points
has a chord across the gap.

The generated block goes at **library level**, before the first
`NETWORKCOMPONENT`, and the flowpath refers to it by label. Verified against the
OLGA 2025.1 rules engine (`-exitRC` → `RuleCheck: OK`):

```
HYDRATECURVE LABEL="HYD", PRESSURE=(10,30,60,100,150,200) bara, \
             TEMPERATURE=(4.5,12.1,17.3,20.6,23.1,24.9) C

NETWORKCOMPONENT TYPE=FLOWPATH, TAG=FLOWPATH_1
 ...
 HYDRATECHECK HYDRATECURVE="HYD"
ENDNETWORKCOMPONENT
```

**The output variable is `DTHYD`, and its sign is the opposite of a margin.**
It is a `SECTION` variable in `C`, described in the catalog as *"Difference
between hydrate and section temperature"*, and it is `T_hydrate(P) − T_fluid`:

| section | P, bara | `TM`, °C | curve `T_hyd`, °C | `DTHYD`, °C | meaning |
| --- | --- | --- | --- | --- | --- |
| inlet | 200.1 | 40.0 | 24.9 | **−15.1** | 15.1 K of margin, safe |
| mid | 161.6 | 22.6 | 23.5 | **+1.0** | 1.0 K *inside* the hydrate region |
| arrival | 121.5 | 8.4 | 21.7 | **+13.4** | 13.4 K of subcooling, hydrate risk |

So **positive `DTHYD` is subcooling into the hydrate region and negative is the
safe margin** — reading it as a margin inverts every conclusion. Those numbers
also reproduce a linear interpolation of the supplied curve to about 0.1 K, which
is the proof that OLGA is interpolating the exported curve and not modelling
hydrates itself.

Because the interpolation is linear, curve resolution is an accuracy choice, and
the error concentrates where the curve is steepest — the low-pressure end.
Measured against a 39-point reference for a wet gas over 10–200 bara:

| curve points | max error over 10–200 bara | max error within a 120–200 bara band |
| --- | --- | --- |
| 4 | 4.11 K | – |
| 6 | 2.55 K | 0.05 K |
| 10 | 1.31 K | – |
| 20 | 0.48 K | 0.01 K |
| 30 | 0.17 K | – |

A steady high-pressure line is nearly straight on this curve, so six points are
enough. A case that depressurises — blowdown, shut-in, restart, or a rate sweep
that walks the arrival down — spends its time in the steep part, where four
points cost 4 K of hydrate temperature. Span the pressures the case will actually
visit and use **at least 20 points whenever the range extends below about
50 bara**.

Two further rules:

- **Inhibited curves must be exported, not assumed.** OLGA's Hammerschmidt
  fallback is a correlation shift; a MEG or methanol curve from the NeqSim fluid
  with the inhibitor present is the whole point of exporting.
- **State the curve on every hydrate result.** The label, the pressure range, the
  point count and the fluid it came from. A `DTHYD` number without them is not
  reproducible.

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
| Steady-state ΔP and holdup on a **gas-dominated** line | NeqSim `TwoFluidPipe` (mechanistic; ΔP within ~3 % of OLGA) |
| Steady-state ΔP screening, single-phase or moderately liquid-loaded | NeqSim `PipeBeggsAndBrills` (single-phase within 0.1–0.3 % of OLGA) |
| Line pack, rate ramp, shut-in on a **gas-dominated** line | NeqSim `TwoFluidPipe.runTransient` (within 0.13 % of OLGA on a line-pack step) |
| Transport delay / arrival lag inside a flowsheet | NeqSim `PipeBeggsAndBrills.runTransient` — a relaxation lag only, **no mass storage** |
| Valve slam, surge | NeqSim `WaterHammerPipe` |
| Phase envelope, hydrate curve, wax appearance temperature, fluid properties | NeqSim thermodynamics |
| Topside process response to an arriving slug | NeqSim `ProcessSystem` / `runTransient` |

**Choose the NeqSim model against the liquid loading, not by habit.** Beggs &
Brill is calibrated for no-slip liquid fractions down to about 0.01–0.02; below
that its two-phase friction multiplier is extrapolated and ΔP is over-predicted
by 30–60 % on a large-bore high-pressure gas line. Above that it is a reasonable
conservative bound. `TwoFluidPipe` is mechanistic and matches OLGA on ΔP for
gas-dominated flow, but its holdup runs 2–4× OLGA and its transient is not usable
for liquid-rich lines. The authority on which NeqSim model applies, and on its
current measured accuracy and open defects, is the `neqsim-flow-assurance`
skill — read it before quoting a NeqSim pipeline number.

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
pipe.setNumberOfSections(160)                 # ~450 m sections on a long line
pipe.setElevationProfile(elevations)          # needs numberOfSections + 1 values
pipe.setIncludeEnergyEquation(True)
pipe.setHeatTransferCoefficient(3.0)          # W/m2K
pipe.setSurfaceTemperature(4.0, "C")
pipe.run()

assert pipe.isSteadyStateConverged()                    # ALWAYS
assert pipe.getSteadyStateIterationsUsed() > 1          # ALWAYS
assert not pipe.isSteadyStatePressureFloorLimited()     # ALWAYS
profile = pipe.getPressureProfile()           # Pa
dp_bar = (profile[0] - profile[-1]) / 1e5
```

Three gates, not one — each catches a different silent failure:

- **`isSteadyStateConverged()`.** The refinement loop is an under-relaxed
  fixed-point sweep; out of iterations it returns the last iterate, which can be
  an order of magnitude wrong. Raise the budget with
  `setSteadyStateMaxIterations(int)` (default scales with the section count) or
  `setSteadyStateMaxWallClockTime(...)` (default 300 s) and check
  `isSteadyStateWallClockLimited()` before blaming the model.
- **`getSteadyStateIterationsUsed() > 1`.** A profile reported after a single
  sweep still carries the densities the sections were *initialised* with, and
  understates the pressure drop of a gas line by roughly ten per cent. A real
  solve on a 74 km line takes a few hundred sweeps.
- **`isSteadyStatePressureFloorLimited()`.** Section pressures are clamped at a
  1 bara floor, and that clamp is a fixed point of itself, so a line with no
  deliverability would otherwise report success on a profile that does not exist.
  When it is true, discard the profile and report a deliverability limit.
  `PipeBeggsAndBrills` throws `Outlet pressure is negative` and OLGA aborts with
  `PRESSURE ABOVE TABLE VALUES` on the same case — three independent confirmations
  that the infeasibility is physical.

Further usage notes:

- **Demonstrate grid independence.** A 74 km line gave 80.39 / 80.93 / 81.20 bar
  at 80 / 160 / 320 sections. Budget for it: an honest solve costs roughly 16 s
  at 160 sections and 48 s at 320, not the sub-second the model used to return
  when it converged prematurely.
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
- **Do not quote its holdup or inventory as a design number.** Holdup runs 2–4×
  OLGA (0.064 vs 0.023 dry; 0.119 vs 0.034 with 15 m³/hr free water), with a slip
  ratio near 10 against OLGA's ~3. The phase bookkeeping is clean — gas, oil and
  water sum to the liquid holdup exactly — so this is a slip-closure gap, not an
  accounting error.
- **Its ΔP can be blind to the temperature field.** Adding 10 MW of DEH raised
  arrival temperature 22 K and left ΔP unchanged to five figures, where OLGA moved
  +12.3 % and Beggs & Brill +23.4 %. Warmer gas at fixed mass rate is less dense
  and ΔP ~ G²/ρ, so ΔP *must* rise — an unchanged ΔP is the signature of a
  pressure march that is not seeing the updated densities. Treat ΔP from any case
  whose temperature field changes as indicative until it moves in the right
  direction.
- **The transient is not usable on liquid-rich lines**, including severe slugging:
  with every boundary held constant it leaves its own steady state, and the liquid
  outlet flux collapses to zero because the phase momentum equations develop
  sustained backflow. Gas-dominated lines are unaffected (0.00 bar null-test
  drift). Use OLGA for liquid-rich transients.

### Reference benchmark — what "good accuracy" looks like

Measured on a 73.8 km × ID 0.355 m wet-gas export line, matched fluid, rate,
phase split, roughness, U and ambient, with OLGA's arrival boundary
secant-iterated to a 200 bara inlet. Use it to sanity-check a new comparison:
a deviation far outside these bands means the *inputs* differ, not the models.

| Case | OLGA ΔP, bar | `TwoFluidPipe` | `PipeBeggsAndBrills` | Darcy hand check |
| --- | --- | --- | --- | --- |
| dry, 10 MSm³/d | 78.51 | 81.20 (+3.4 %) | 125.00 (+59 %) | 77.72 |
| dry, 4 MSm³/d | 10.15 | 13.52 (+33 %) | 13.59 (+34 %) | 10.61 |
| dry, 7 MSm³/d | 33.60 | 40.23 (+20 %) | 43.87 (+31 %) | 34.45 |
| + 10 MW DEH | 88.19 | 81.20 (ΔP blind) | 154.19 | – |
| + 15 m³/hr free water | 104.06 | 91.31 (−12 %) | 143.94 (+38 %) | – |

Compare the **rate exponent** `n` in `ΔP ~ rate^n`, not just the level at one
point: OLGA gives 2.14 / 2.38 / 3.12 across the sweep and Darcy 2.10 / 2.28 /
2.41. `n` must exceed 2 because the gas density falls along the line. A model
returning a flat `n` ≈ 2 reproduces one operating point while having the wrong
sensitivity — which a single-rate benchmark cannot detect.

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
- [ ] A **generated** PVT table was validated by an actual OLGA run, not by
      `-exitRC` — the rule check never opens the table — and its fluid label
      matches the `BRANCH FLUID=` string.
- [ ] For a three-phase case, `GASFRACTION` was given on the **hydrocarbon**
      basis and the `MASS SOURCE INFORMATION:` block in the `.out` file was read
      back and reconciled against the NeqSim flash in kg/s.
- [ ] Every requested `PROFILEDATA` / `TRENDDATA` variable was confirmed present
      in the result `CATALOG`, because the rule check does not validate variable
      names and silently drops unknown ones.
- [ ] If hydrates matter, a `HYDRATECURVE` was exported from the same fluid as
      the PVT table and referenced with `HYDRATECHECK` — OLGA was not left on its
      Hammerschmidt fallback — and the curve spans the pressures the case
      actually visits with enough points for its steep low-pressure end.
- [ ] `DTHYD` was interpreted with the right sign: **positive is inside the
      hydrate region**, negative is the safe margin.
- [ ] The mesh came from `discretize_route`, its `summary()` was recorded, and
      grid independence was demonstrated by halving the target section length.
- [ ] When benchmarking against another model, every row of the input-equivalence
      table was proved with a number: composition, mass rate, inlet phase split,
      diameter, roughness, length, pressure level and ambient conditions.
- [ ] Any headline disagreement was audited term by term against the published
      correlation on a short single-increment segment, over a range of
      inclinations, and cross-checked against a single-phase Darcy hand
      calculation before being attributed to either code.
- [ ] If a `TwoFluidPipe` result was used as a cross-check, all three gates
      passed — `isSteadyStateConverged()` true, `getSteadyStateIterationsUsed() > 1`,
      `isSteadyStatePressureFloorLimited()` false — and the answer was shown to be
      grid-independent over at least two mesh refinements.
- [ ] No `TwoFluidPipe` holdup, slip ratio or liquid inventory was quoted as a
      design number (it runs 2–4× OLGA), and any ΔP from a case whose temperature
      field changed was checked to move in the right direction.
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
| A three-phase run gives condensate an order of magnitude wrong, but converges and looks plausible | `GASFRACTION` was given on the total-stream basis while `WATERFRACTION` was also set. With water present, `GASFRACTION` is the gas mass fraction of the **hydrocarbons only** | Recompute as `m_gas / (m_gas + m_oil)`, and reconcile the `MASS SOURCE INFORMATION:` GAS/OIL/WATER kg/s in the `.out` against the NeqSim flash before believing any number |
| `ERROR IN THE INPUT FILE: OIL DENSITY IS ZERO AT: PRES.=... AND TEMP.=...` | A NeqSim-generated table indexed phases by array position, so single-phase grid nodes wrote zero for the absent phase | Regenerate with a NeqSim build that resolves phases by type and fills absent-phase columns; dry gas, dead oil and dense-phase CO₂ all failed on the old generator |
| OLGA cannot bind a generated table to the flowpath | The table's fluid label does not equal the `BRANCH FLUID=` string | Call `setFluidLabel(...)` with the same label used in the genkey |
| A generated PVT table passed `-exitRC` and then failed the real run | `-exitRC` does not open the PVT file at all | Validate every generated table with a throwaway minimal run (source + pressure node) and require exit 0 |
| A requested output variable is missing from the results | The rule check does not validate variable names — an unknown one passes silently and is dropped | Read the `CATALOG` block of the `.ppl`/`.tpl` back and confirm every variable is present. `UHL` and `UWT` are not valid names; the water and hydrocarbon-liquid holdups are `HOLWT` and `HOLHL` |
| OLGA and NeqSim disagree about where hydrates form | No `HYDRATECURVE` in the case, so OLGA used its Hammerschmidt fallback instead of the NeqSim hydrate model | Export the curve with `OLGAhydrateCurveGenerator` from the same fluid as the PVT table and reference it with `HYDRATECHECK HYDRATECURVE="..."` |
| A hydrate conclusion is exactly inverted | `DTHYD` is `T_hydrate − T_fluid`, so **positive means inside the hydrate region**, not safe margin | Re-read the sign; cross-check one section against the curve by hand |
| Hydrate margin is a few kelvin out at low pressure | OLGA interpolates the supplied curve **linearly**, and the curve is steepest below ~50 bara | Export at least 20 points when the case visits low pressure; 4 points over 10–200 bara costs 4.1 K |
| The hydrate curve has fewer points than requested | The generator drops pressures where the hydrate flash did not converge rather than writing a zero | Check the returned point count; a dropped point leaves a straight chord across the gap |
| Looking for a batch "discretize geometry" command | OLGA's discretiser is GUI-only | Build the section list with `discretize_route` |
| Section length jumps at every leg boundary | A fixed `NSEGMENT` per leg on unequal legs | Use a target section length and the neighbour-ratio limit |
| Steady-state holdup barely changes when the pipe is inclined | The correlation's inclination correction is being suppressed | Sweep the angle and compare against the published correction; a near-constant holdup means the term is broken, not small |
| A correlation audit shows a few per cent deviation that will not close | The reference was evaluated at the inlet but the simulator evaluated it after the pressure change across the increment | Shrink the test segment to ~1 m with one increment |
| Liquid-property terms disagree by ~20% for no visible reason | `phase.getDensity()` and `phase.getDensity("kg/m3")` differ when volume correction is on | Use the explicit-unit accessor everywhere; never mix the two in one formula |
| `TwoFluidPipe` ΔP is several times below a Darcy hand check on a long line | The steady-state loop ran out of iterations and returned the last iterate | Assert `isSteadyStateConverged()`; raise `setSteadyStateMaxIterations(int)` |
| `TwoFluidPipe` returns instantly, claims convergence, and understates ΔP by ~10 % | It converged after a single sweep, so the pressure march still carries the densities the sections were initialised with | Also assert `getSteadyStateIterationsUsed() > 1`. An honest solve on a 74 km line takes a few hundred sweeps and tens of seconds |
| `TwoFluidPipe` reports "converged" with the arrival pinned at exactly 1.000 bara | Every section hit the 1 bara pressure-floor clamp, which is a fixed point of itself, so the per-section change fell below tolerance | Check `isSteadyStatePressureFloorLimited()`; the line has no deliverability at that rate — report the limit rather than the profile |
| `TwoFluidPipe` ΔP does not move when heating or cooling is added | The pressure march is not seeing the updated densities | ΔP ~ G²/ρ must rise with temperature at fixed mass rate; an unchanged ΔP invalidates that case, not just the heating term |
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
