# neqsim-well-design-study

Screening-level well design study toolkit: pressure window, casing seats and kick tolerance, casing and tubing design (API TR 5C3), completion screening, torque and drag, ECD, offset-well calibration, time and cost Monte Carlo, validation checks and a Word report.

```text
pip install -e .[test]
pytest
```

See `SKILL.md` for inputs, method, validation checklist and limitations. Educational / screening only; not for final well design.

Modules: `pressure`, `casing_seats`, `casing_design`, `tubing`, `torque_drag`, `hydraulics`, `offsets`, `normalise`, `study`, `figures`, `report`. Example: `examples/example_study.py`.
