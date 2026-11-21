# neqsim-fluid-commingling-compatibility

Blend-sweep compatibility screening of two commingled fluids with NeqSim.
It finds the problems that appear only in the mixture: asphaltene
destabilisation by dilution, gas breakout on mixing, a hydrate temperature
above both end members, and separator-gas H2S/CO2 over a limit.

See [SKILL.md](SKILL.md) for inputs, method, limitations and references.

## Run

```bash
python -m pip install -e ".[neqsim]"
python examples/heavy_oil_condensate_tie_in.py
python -m pytest tests
```

The screening logic is tested without Java through an analytic stand-in
evaluator; `tests/test_neqsim_integration.py` runs the real NeqSim backend and
is skipped when `neqsim` is not installed.
