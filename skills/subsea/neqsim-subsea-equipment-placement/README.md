# Subsea Equipment Placement

Constraint-based screening and ranking of sites for drill centres, templates, manifolds, PLETs and tie-in points, and screening of the routes that connect them. Limits always carry a value, unit, source and basis; a limit that is assumed or missing gives `NEEDS_REVIEW`, never `PASS`.

```bash
python -m pip install -e skills/subsea/neqsim-subsea-equipment-placement[test]
python -m pytest skills/subsea/neqsim-subsea-equipment-placement
```

See `SKILL.md` for the method, the siting checklist and the standards clauses to read before setting limits.
