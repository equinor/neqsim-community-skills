# H2S Phase Partitioning

Educational skill that uses NeqSim (SRK-CPA) to split H2S between gas, oil and water in a separator train, and to back-calculate wellstream H2S from a measured separator-gas H2S.

## Install

```bash
python -m pip install -e skills/subsurface/neqsim-h2s-phase-partitioning
```

## Run Tests

```bash
python -m pytest skills/subsurface/neqsim-h2s-phase-partitioning/tests
```

The NeqSim tests are skipped when the `neqsim` package is not importable. pytest on Windows may print a JPype "access violation" fault-handler trace during JVM start; it is harmless when the tests pass.

## Public Scope

The default composition is a demonstration fluid. No field composition, measurement or company data is included. Aqueous H2S ionisation is not modelled; use measured distributions and qualified review for real work.
