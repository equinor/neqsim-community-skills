# Tie-in P&ID sketch

Conceptual P&ID sketches (SVG, no dependencies) of both ends of a new tie-in line, with a completeness check
(ESD valve, pigging, check valve, spectacle blind, tie-in marked).

```bash
python -m pip install -e skills/subsea/neqsim-tie-in-pid-sketch
python -m pytest skills/subsea/neqsim-tie-in-pid-sketch/tests
```

```python
from tie_in_pid_sketch import pair_sketch, render_svg
pair = pair_sketch("Martin Linge A", "Oseberg A")
open("source_end.svg", "w", encoding="utf-8").write(render_svg(pair["source"]))
```

Tags are proposals and carry an asterisk. A sketch is a discussion basis, not a controlled P&ID.

Version 1.1 adds `PidSheet` for full subsea sheets (trees, manifold, flowline, riser, topside landing, water injection, umbilical and
chemical supply) with a layout spec for `neqsim pfd-check`, isolation counts, data tables and profiles beside the drawing, and a
48-item tie-in considerations register (`considerations_register`). See SKILL.md.
