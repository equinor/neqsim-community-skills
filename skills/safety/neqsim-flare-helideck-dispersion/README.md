# Unignited Release Gas Dispersion to Any Place on a Facility

Screening-level dispersion of unignited gas (flare tip, cold vent, PSV tail pipe or other
vent; rated PSV flow or blowdown peak) from any release source to any receptor on a
facility: helideck and flight paths, air intakes, accommodation, muster areas, escape
routes, crane cabs, ignition sources and so on. It combines a choked tip with a
notional jet, Briggs plume rise with stable-air limits, and a Gaussian plume, sweeps the
wind climate, and reports the share of wind hours in which 10 % and 20 % of the lower
flammability limit (LFL) are exceeded **given that a release is ongoing**.

The helideck study (flare tip, helideck, flight paths) is a preset of the same model; the
package name `flare_helideck_dispersion` is kept for compatibility.

It also produces the report material from the same run: house-style figures (7.2 in
wide), a schematic overlay on a user-supplied image, and a `results.json` fragment with
captions, discussion, tables, assumptions, data gaps, uncertainty, risk and a CFD
hand-off.

This skill supports screening only. It has no platform wake or CFD, its exceedance values
are conditional (not annual frequencies), and a qualified safety engineer must review any
decision. See `SKILL.md` for the method, report quality rules and limitations.

## Install

```bash
pip install -e .[test]
```

`numpy` is required; `matplotlib` is needed for the figures and overlay. NeqSim is
optional (PSV sizing only).

## Run the tests

```bash
python -m pytest
```

## Example

```bash
python examples/generic_platform_example.py [output_dir]
```

The example uses a hypothetical platform (flare tip 124 m ASL, helideck 76 m ASL, 240 m
apart, obstacle-free sector 135-345 deg) and a synthetic wind record.

## Command line

```bash
python -m flare_helideck_dispersion facility config.json --figures
python -m flare_helideck_dispersion section config.json
python -m flare_helideck_dispersion run config.json
python -m flare_helideck_dispersion figures config.json
python -m flare_helideck_dispersion overlay config.json
```

`facility` takes any number of `sources` and `receptors` (see
`examples/facility_example.json`); `run`, `figures` and `overlay` are the helideck preset.
A receptor `shape` is `point`, `disc`, `rectangle`, `polyline`, `fan`, `into_wind_path` or
`points`; each receptor can carry its own `thresholds_pct_lfl` and `criterion_source`.
Coordinates are east/north/up metres in one true-north frame, height above sea level.

Minimal helideck `config.json` (paths are relative to this file):

```json
{
  "output_dir": "out",
  "geometry": {"tip_height_asl_m": 124.0, "helideck_height_asl_m": 76.0,
               "helideck_distance_m": 240.0, "helideck_azimuth_from_tip_deg": 240.0,
               "ofs_start_deg": 135.0, "ofs_end_deg": 345.0},
  "wind": {"hourly_csv": "hourly_wind.csv"},
  "releases": [
    {"name": "Blowdown cold", "mass_flow_kg_s": 150.0,
     "composition": {"methane": 0.7, "ethane": 0.2, "propane": 0.1},
     "gamma": 1.25, "t0_k": 190.0}
  ],
  "settings": {"params": {"tilt_deg": 45.0}},
  "sensitivity": {"n_samples": 100, "seed": 42},
  "flameout": {"frequency_per_year": null, "hours_per_release": null},
  "overlay": {"image": "view.png", "anchor_px": [960, 572], "px_per_m": 0.75,
              "case": "Blowdown cold", "wind_from_deg": 60.0, "speed_m_s": 3.3}
}
```

`wind` may also be `{"table_json": "wind.json"}` or an inline `{"table": {...}}`.
`flameout` stays empty unless a flame-out frequency is known; no annual figure is written
without it.

## Package layout

| Module | Purpose |
|---|---|
| `model.py` | choked tip, notional jet, Briggs rise, Gaussian plume, free-jet cross-check |
| `wind.py` | joint wind table, hourly CSV binning, Pasquill schemes |
| `receptors.py` | geometry, helideck points, flight paths, obstacle-free sector, into-wind logic |
| `facility.py` | sources, receptors of any shape, facility study, ranking, tilt scan, tornado, helideck preset |
| `facility_results.py`, `facility_figures.py` | facility `results.json` fragment and figures |
| `study.py` | wind sweep, conditional exceedance, annualisation helper, benchmark helper |
| `sensitivity.py` | tilt scan, tornado, seeded Monte Carlo |
| `sources.py` | composition to LFL and molar mass, API 520 rated flow, optional NeqSim PSV sizing |
| `style.py`, `figures.py` | house style and the figures |
| `overlay.py` | schematic overlay and composite |
| `results.py` | `results.json` fragments and validation |
| `cli.py` | command line |

All inputs are explicit; nothing is downloaded or installed at run time.
