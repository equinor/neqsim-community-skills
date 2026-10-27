# Technology Assessment Report

Builds a technology assessment report for any technology from the results of
`neqsim-technology-assessment` and `neqsim-technology-fmirr`. Markdown output
needs no dependency; Word output needs `python-docx`.

See `SKILL.md` for the chapter structure and authoring workflow.

## Quick Start

```bash
cd skills/reporting/neqsim-technology-assessment-report
python -m pytest
python examples/build_example_report.py ./out
```

## Layout

- `src/technology_assessment_report/model.py` — report builder and renderers.
- `examples/build_example_report.py` — builds the synthetic example report.
- `tests/` — unit tests (they load the sibling skills' examples).

## License

Apache-2.0.
