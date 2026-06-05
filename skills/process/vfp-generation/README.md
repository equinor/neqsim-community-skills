# neqsim-vfp-generation

Generate, post-process, import, and compare Eclipse VFPPROD lift-curve tables from a
constraint-based compressor model. Includes the diagnostic visualization conventions
used for compressor-map and driver plots.

See [SKILL.md](SKILL.md) for the full method, diagnostic style guide, and references.

## Install

```bash
pip install -e .[test]
```

## Run Example

```bash
python examples/vfp_demo.py
```

## Run Tests

```bash
pytest
```

## Public Scope

All code and examples use synthetic, public data only. No plant tags, facility names,
document references, or proprietary acceptance criteria are included. `DEFAULT_THRESHOLDS`
are generic public defaults, not project-specific limits. The constraint-solving loop that
needs a calibrated process model is documented in SKILL.md but not bundled here.
