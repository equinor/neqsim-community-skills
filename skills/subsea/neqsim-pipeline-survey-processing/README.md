# Pipeline Survey Processing

Educational as-built pipeline survey processing. Turns raw survey rows (KP, depth
to top of pipe, seabed depth, coordinates) into a cleaned, sign-normalised,
resolution-filtered pipeline profile with flagged erroneous points, free-span and
cover candidates, a repeat-survey change comparison, and a traceable processing
log.

This skill supports screening only. It does not perform free-span, stability,
pipe-soil or integrity assessment, and it is not a positioning or datum authority.
A qualified human review is always required.

## Install

```bash
pip install -e .[test]
```

## Run the tests

```bash
python -m pytest
```

## Example

```bash
python examples/basic_pipeline_survey_processing.py
```

See `SKILL.md` for inputs, outputs, engineering method, validation checklist and
limitations.
