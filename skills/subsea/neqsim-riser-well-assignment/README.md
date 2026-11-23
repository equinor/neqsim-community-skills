# neqsim-riser-well-assignment

Mixed-integer optimiser for the well-to-riser pairing problem on a floating host.
See [SKILL.md](SKILL.md) for the model, inputs, limits and handoffs.

```powershell
pip install -e .[test]
python -m riser_well_assignment --synthetic --pareto --out result.json
python -m pytest
```

The built-in synthetic instance is invented and is not data from any field.
