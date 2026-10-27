# Technology FMIRR

Dependency-free failure-mode identification and risk-ranking register for
technology qualification: separate item / mode / mechanism / cause fields,
5x5 risk ranking with a high-consequence floor, critical modes linked to
qualification tests, and re-rating history.

See `SKILL.md` for the method.

## Quick Start

```bash
cd skills/safety/neqsim-technology-fmirr
python -m pytest
python examples/basic_fmirr.py
```

## Layout

- `src/technology_fmirr/model.py` — register and ranking.
- `examples/example_fmirr.json` — synthetic example register.
- `examples/basic_fmirr.py` — minimal usage example.
- `tests/` — unit tests.

## License

Apache-2.0.
