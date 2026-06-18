# Pipe Wall Thickness Screening

Educational process-pipe wall-thickness screening skill for public examples and agent guidance.

This skill provides a simple Python `PipeWallThicknessModel` with placeholder indicators for the ASME B31.3 pressure-design thickness, a required thickness with corrosion allowance, a margin ratio against a nominal wall, and an operating warning. It is intended for learning and workflow scaffolding only.

## Install

```bash
python -m pip install -e skills/process/pipe-wall-thickness-screening
```

## Run Example

```bash
python skills/process/pipe-wall-thickness-screening/examples/basic_pipe_wall_thickness_screening.py
```

## Run Tests

```bash
python -m pytest skills/process/pipe-wall-thickness-screening/tests
```

## Public Scope

The model does not contain proprietary piping classes, confidential material certificates, vendor data, or company-specific piping specifications. For real calculations, use validated mechanical-design methods (ASME B31.3, ISO 13703), validated NeqSim mechanical-design classes, and qualified piping engineering review.
