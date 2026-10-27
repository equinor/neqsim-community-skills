# Near-Field Discoveries

Inventory of the discoveries, fields, evaluation-plan areas, hosts and pipelines around a target, for the
Norwegian Continental Shelf (Sodir) and Brazil (ANP): a common development-stage ladder, public volumes where
they exist, nearest hosts, joint-development clusters, CSV/JSON/GeoJSON exports and a near-field map.

## Install

```bash
python -m pip install -e skills/field-development/neqsim-near-field-discoveries[map]
python -m pip install -e skills/field-development/neqsim-anp-open-data   # Brazil reads and bathymetry
```

## Run

```bash
python skills/field-development/neqsim-near-field-discoveries/examples/near_field_study.py \
    --country BR --name "Santos target" --lat -25.0 --lon -42.5 --radius 150 --out task/step2_analysis --bathymetry
```

## Run Tests

```bash
python -m pytest skills/field-development/neqsim-near-field-discoveries/tests
```

## Public Scope

Contains no data. Sodir and ANP layers are read at run time with a log of every read; Sodir data are NLOD 2.0.
