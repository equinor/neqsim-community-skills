# OLGA Multiphase Simulator (NeqSim Community Skill)

Drive the OLGA transient multiphase flow simulator (SLB) from Python: locate the
installed engine, rule-check a case, run it in batch, decode the exit code, and
read `.tpl` trend and `.ppl` profile results.

OLGA is licensed commercial software. This skill contains **no** OLGA code, data
or documentation — it only drives an installation that the user already has, and
reads the plain-ASCII result files that installation produces.

## Install

```bash
python -m pip install -e skills/flow-assurance/olga-multiphase-simulator
```

No third-party Python dependencies. The library imports and its tests run on a
machine without OLGA installed; only the actual `run` calls need the simulator.

## Configure

Discovery scans the standard Windows install locations. Override it with either:

- `OLGA_HOME` — an installation root, e.g. `C:\Program Files\Schlumberger\Olga 2025.1.0`
- `OLGA_ENGINE` — the batch solver, e.g. `...\OlgaExecutables\Olga-2025.1.0.exe`

Licensing is unchanged: OLGA reads `LM_LICENSE_FILE` / `SLBSLS_LICENSE_FILE`.
This skill never stores, prints or ships a licence server address.

## Run Example

```bash
python skills/flow-assurance/olga-multiphase-simulator/examples/run_olga_case.py \
    path/to/case.genkey --endtime "600 s" --nthreads 4
```

## Run Tests

```bash
python -m pytest skills/flow-assurance/olga-multiphase-simulator/tests
```

## Public Scope

The command-line options, exit-code table and result-file layout documented here
were read back from a local OLGA 2025.1.0 installation using its own
`-help`, `-version all` and `exit_code_lookup.exe list` outputs. The skill holds
no confidential pipeline geometry, project flow-assurance report, PVT table or
company guideline. Interpretation of any OLGA result still requires a qualified
flow-assurance review.
