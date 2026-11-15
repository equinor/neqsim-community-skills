# neqsim-seismic-structure-to-reservoir

Turns seismic or interpreted surfaces into a screening reservoir model:
- finds structural data in task folders;
- reads IRAP, ZMAP+ or XYZ surfaces, or tracks a horizon in a SEG-Y cube from a seed at a well;
- converts time to depth with a velocity model calibrated on well ties;
- locates the crest, spill point and closure, and computes area, relief and gross rock volume per contact;
- hands the results to `neqsim-reservoir-model-builder` and can write a layered OPM Flow grid.

```bash
pip install -e .[test]
pytest
python -m seismic_structure discover <folder> --out inventory.json
python -m seismic_structure run config.json
```

See [SKILL.md](SKILL.md) for the method, configuration, validation and limitations.
