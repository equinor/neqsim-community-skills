# neqsim-seismic-segy-reading

Reads SEG-Y seismic with [equinor/segyio](https://github.com/equinor/segyio). It reports geometry, scaled trace coordinates, bin spacing, CRS hints from the text header and amplitude QA. It also cuts inline, crossline, slice and polyline-fence sections, finds the trace nearest a well, saves PNG sections, writes small cubes and produces `seismic_dataset_evidence.v1` records.

```bash
pip install -e .[test]
pytest
python -m segy_seismic_reading path/to/volume.sgy --out evidence.json
```

See [SKILL.md](SKILL.md) for usage, validation and limitations.
