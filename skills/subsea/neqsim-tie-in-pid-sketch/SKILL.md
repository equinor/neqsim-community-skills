---
name: neqsim-tie-in-pid-sketch
calculation_basis: "screening"
version: "0.1.0"
description: "Conceptual P&ID sketches (SVG) of both ends of a new tie-in line - source platform end with pump, metering, pig launcher, ESDV and riser; landing end with riser, ESDV, pig receiver, sampling, pressure control, spectacle blind and tie-in to an existing header - plus a completeness check. USE WHEN: a tie-in or export concept needs a drawing of possible connection points and the isolation, pigging and metering philosophy before a controlled P&ID is made."
last_verified: "2026-10-20"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: []
---

# Tie-in P&ID sketch

Draws a one-line conceptual P&ID for each end of a line. Existing plant is thin and dark, new scope is bold
and green, invented tags carry `*`. Built for the Martin Linge A to Oseberg A oil export concept.

## When to Use

- After `neqsim-tie-in-pipeline-concept` has chosen candidate landing points and a line size.
- To show where the line ties in, which isolation, pigging, metering and sampling it needs, and which options
  remain open (existing pump or new pump, which header, which riser slot).

Not for controlled P&IDs, HAZOP, or anything that is built from.

## Inputs

- Source and landing facility names.
- Options for the templates: `new_export_pump`, `with_booster`, `keep_old_route`.
- Tags read from the controlled P&ID for existing equipment (`existing_tag`, `header_tag`); leave blank when not read.

## Outputs

A `TieInEndSketch` per end (elements, `options` block of open choices, `validate()` findings) and an SVG string
from `render_svg`. Existing plant is drawn thin and dark, new scope bold and green, invented tags with `*`.

## Engineering Method

The templates encode the isolation, pigging, metering and sampling philosophy of an oil export tie-in: pump,
metering, pig launcher, ESDV and riser at the source end; riser, ESDV, pig receiver, sampling, pressure control,
spectacle blind and tie-in to an existing header at the landing end. `validate()` checks completeness against that
list. Nothing is sized here; line size and pressure come from `neqsim-tie-in-pipeline-concept`.

## Workflow

1. Read the controlled P&ID for the existing equipment at each end: name the export header, pump and battery
   limit valve. Pass the tag to the template (`existing_tag`, `header_tag`) and the element becomes
   `proposed=False`; leave it blank if you did not read it.
2. `pair_sketch(source, landing)` or call `source_end_oil_export` / `landing_end_oil_header` with options
   (`new_export_pump`, `with_booster`, `keep_old_route`). Build a custom `TieInEndSketch` for other layouts.
3. `sketch.validate()` must return an empty list or each finding must be explained in the report.
4. `render_svg(sketch)`, save to `figures/`, and convert to PNG for Word (for example with Edge or Inkscape).
5. List the open choices (the `options` block) as questions to the facility owners.

## Always state

Tags are proposals; routes of the main line are conceptual; capacity of the existing header, riser slot and
quality acceptance are not verified; the sketch is not a controlled document.

## Python Usage Pattern

```python
from tie_in_pid_sketch import pair_sketch, render_svg

pair = pair_sketch("Source A", "Landing B")
for end, sketch in pair.items():
    assert sketch.validate() == []
    with open("figures/tie_in_{}.svg".format(end), "w", encoding="utf-8") as handle:
        handle.write(render_svg(sketch))
```

## Validation Checklist

- [ ] `sketch.validate()` returns an empty list, or each finding is explained in the report.
- [ ] Every tag read from the controlled P&ID is passed as `existing_tag` / `header_tag`; all other tags keep the `*`.
- [ ] The old route has a blind or isolation when it stays in place.
- [ ] Open choices from `options` are listed as questions to the facility owners.

## Common Mistakes

- Inventing tags as if they came from the controlled P&ID. Use `proposed=True` (default) and keep the asterisk.
- Showing the landing as a single point. Keep the ESDV, pig receiver and spectacle blind: they are what makes the
  tie-in operable and isolable.
- Forgetting the old route. A blind towards the old export (FSO or tanker) is needed to isolate it safely.

## Limitations

One-line conceptual drawings of an oil export tie-in only; no instrument loops, line numbers, relief or control
philosophy, and no check that the existing header or riser slot can accept the line.

## References

- ISO 10628, Diagrams for the chemical and petrochemical industry.
- Controlled P&IDs of the existing facilities: the only source for real tags.

## Related

`neqsim-tie-in-pipeline-concept`, `neqsim-pid-process-operations`. For company-controlled P&IDs, use the matching
enterprise overlay skill (enterprise repositories only).

