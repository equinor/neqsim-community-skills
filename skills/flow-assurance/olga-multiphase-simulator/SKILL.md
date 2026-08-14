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
