# Bathymetry Profile Screening

Educational bathymetry profile screening skill for public examples and agent guidance.

This skill provides a simple Python `BathymetryProfileModel` that sorts seabed soundings, linearly interpolates depth along a route, computes seabed slopes, and flags candidate steep sections. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/subsea/bathymetry-profile-screening
```

## Run Example

```bash
python skills/subsea/bathymetry-profile-screening/examples/basic_bathymetry_profile_screening.py
```

## Run Tests

```bash
python -m pytest skills/subsea/bathymetry-profile-screening/tests
```

## Public Scope

The model does not contain proprietary bathymetry, survey data, free-span analysis, or company-specific seabed rules. Soundings must be public or synthetic. Profiles and slope flags are screening indicators only. For real work, use validated free-span and on-bottom-stability analyses and qualified subsea engineering review.
