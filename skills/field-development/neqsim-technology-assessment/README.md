# Technology Assessment

Dependency-free, educational structuring of a technology assessment: technology
decomposition, novelty categorisation (1-4), TRL (0-7) roll-up, enabling versus
enhancing classification, step-out definition, benefits and risks,
standardisation potential and a preliminary qualification outline.

It structures expert judgement and flags inconsistencies; it does not create
qualification evidence. See `SKILL.md` for the method and the hand-off to
`neqsim-technology-fmirr` and `neqsim-technology-assessment-report`.

## Quick Start

```bash
cd skills/field-development/neqsim-technology-assessment
python -m pytest
python examples/basic_technology_assessment.py
```

## Layout

- `src/technology_assessment/model.py` — assessment model.
- `examples/example_novel_technology.json` — synthetic example input.
- `examples/basic_technology_assessment.py` — minimal usage example.
- `tests/` — unit tests (run from inside this folder).

## License

Apache-2.0.
