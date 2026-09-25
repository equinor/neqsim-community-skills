# Continuous Improvement Toolkit

Generic, public helpers for NeqSim living tasks: a tagreader historian adapter,
Gaussian-process Bayesian optimisation with expected improvement, an ensemble
Kalman parameter update, and an identifiability check. See `SKILL.md`.

## Install

```bash
python -m pip install -e skills/process/neqsim-continuous-improvement-toolkit
python -m pip install tagreader   # optional, for the historian adapter
```

## Test

```bash
python -m pytest skills/process/neqsim-continuous-improvement-toolkit/tests
```

The tests use a fake tagreader client and synthetic functions; no network,
no Java, no company data.
