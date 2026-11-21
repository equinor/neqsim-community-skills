# neqsim-active-learning-surrogate

Active-learning Gaussian-process surrogates of NeqSim flowsheets. The learner
chooses where to run NeqSim next, so a Monte Carlo study, an operating-envelope
map or a "where does this limit bind?" question needs tens of NeqSim runs
instead of thousands.

See [SKILL.md](SKILL.md) for inputs, method, limitations and references.

## Run

```bash
python -m pip install -e ".[neqsim]"
python examples/host_compressor_capacity_boundary.py
python -m pytest tests
```

The learner and Gaussian process are tested on analytic functions without
Java; `tests/test_neqsim_integration.py` learns a real NeqSim flowsheet
boundary and is skipped when `neqsim` is not installed.
