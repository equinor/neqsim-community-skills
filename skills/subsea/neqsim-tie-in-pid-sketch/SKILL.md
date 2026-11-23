---
name: neqsim-tie-in-pid-sketch
calculation_basis: "screening"
version: "1.1.0"
description: "Conceptual P&IDs of a tie-in: one-line oil-export sketches of both line ends, and full subsea sheets (trees, manifold, flowline, riser, topside landing, water injection, umbilical and chemical supply) with symbols, isolation counts, a layout-checker spec and a 48-item tie-in considerations register. USE WHEN: a tie-in or tie-back needs a drawing of isolation, pigging, chemical injection, metering and a checklist of design considerations before a controlled P&ID exists."
last_verified: "2026-11-22"
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

## Subsea sheets (version 1.1)

`PidSheet` draws a full sheet: you place symbols on a canvas, connect them in flow order, and get an SVG, a layout spec for
`neqsim pfd-check` and completeness findings. Use it for a subsea tie-back with several trees, chemical injection, water
injection and an umbilical; the one-line sketch above stays the tool for an oil-export line.

```python
from tie_in_pid_sketch import PidSheet

s = PidSheet("PID-001", "Template, production side", revision="A", date="2026-11-22")
s.add("tree", "XT-P1", 290, 170, w=90, h=110, label="Production\ntree 1", fill="#e8eef6")
s.add("gate_valve", "PMV-P1", 390, 170)
s.add("esdv", "PWV-P1", 490, 170, label="Wing")
s.add("choke", "CH-P1", 590, 170)
s.add("manifold", "MF-P", 760, 170, w=70, h=200, label="Production\nmanifold")
s.chain(["XT-P1", "PMV-P1", "PWV-P1", "CH-P1", "MF-P"], "production")        # arrows in flow order
s.add("instrument", "PT-101", 440, 80, label="THP"); s.add("junction", "J1", 440, 170)  # a junction on the line takes the tap
s.note("Tags are proposals (*).")
findings = s.validate(required_kinds=["tree", "choke"], min_isolation={("XT-P1", "MF-P"): 2})
paths = s.write("figures/PID-001")                    # .svg and .layout.json; then: neqsim pfd-check figures/PID-001.layout.json
```

Symbols: gate, ball, check, ESDV, SSIV, choke, control and chemical injection valves; transmitters; tree, manifold, PLET,
box, vessel, pump, pig launcher and receiver, hub connector, spectacle blind, junction, system boundary. Status `existing`
is thin and dark, `new` bold and green, `decision` dashed orange (an option or an open decision, listed in the legend).
Services: production, gas, injection water, service line (MEG or methanol), chemical, hydraulic, power and signal, vent.
`add_table` and `add_profile` put data (an operating-state table, a seabed profile) beside the drawing as decoration.
`isolation_count(a, b)` counts the isolating valves in series between two tags, so a barrier rule ("two between the tree
and the manifold") is a test, not a claim. Every process line gets a flow arrow; draw lines in the flow direction.

The layout spec is what `neqsim pfd-check` reads: overlaps, labels on lines, missing arrowheads, crossings and
unconnected nodes are checked on real geometry. Waive a finding with `s.waive(code, reason)` only with a stated reason.
View the picture after the check: a pass is structural, not a reading of the drawing.

## Considerations register

`subsea_tie_in_considerations()` returns 48 generic items in ten categories (wells, subsea system, flowline and riser, host
interface, flow assurance, operations and safety, installation, integrity, environment, interfaces and evidence), each with the
question, why it matters, the evidence normally needed and a standards pointer. `considerations_register(statuses)` merges a
project's statuses (`ADDRESSED`, `SCREENED`, `OPEN`, `NOT_APPLICABLE`, with finding, evidence, action, owner); an item nobody
answered stays `OPEN` with "Not addressed in this study", never "not needed". `register_summary(rows)` counts by status and
category. Run it on every tie-in study: in the Grimsnes tie-back it found 27 of 48 items open, among them the shut-in pressure
against the host slot's seal rating, SSIV, pigging, metering and water quality.

## Validation Checklist

- [ ] `sketch.validate()` returns an empty list, or each finding is explained in the report.
- [ ] Every tag read from the controlled P&ID is passed as `existing_tag` / `header_tag`; all other tags keep the `*`.
- [ ] The old route has a blind or isolation when it stays in place.
- [ ] Open choices from `options` are listed as questions to the facility owners.
- [ ] A subsea sheet: `validate` is empty, `neqsim pfd-check` passes, waivers have reasons, and the picture was viewed.
- [ ] Every option or open decision on a sheet is drawn `decision` and appears in the decision list of the report.
- [ ] The considerations register is in the report with its open items, owners and actions.

## Common Mistakes

- Inventing tags as if they came from the controlled P&ID. Use `proposed=True` (default) and keep the asterisk.
- Showing the landing as a single point. Keep the ESDV, pig receiver and spectacle blind: they are what makes the
  tie-in operable and isolable.
- Forgetting the old route. A blind towards the old export (FSO or tanker) is needed to isolate it safely.
- Drawing a vertical line through a horizontally drawn valve: use `rot=90` for a valve on a vertical line.
- Using a transmitter as a marker for something that is not an instrument. Use text or a junction.
- Treating a considerations register full of `OPEN` as a failure of the register. It is the finding.

## Limitations

Conceptual drawings only: no line numbers, no instrument loops beyond the transmitters drawn, no relief or control philosophy, and
no check that an existing header, riser slot or utility can accept the new line. The pressure and sizing numbers on a sheet come from
the caller. The considerations list is generic; it does not replace the project's own requirements.

## References

- ISO 10628, Diagrams for the chemical and petrochemical industry.
- ISO 13628-1 and ISO 13628-4/5/6, API RP 17A, DNV-ST-F101, ISO 10418: pointers only; check the edition and the project
  requirements before citing one.
- Controlled P&IDs of the existing facilities: the only source for real tags.

## Related

`neqsim-tie-in-pipeline-concept`, `neqsim-pid-process-operations`, `neqsim-subsea-equipment-placement` (siting limits),
`neqsim-surf-field-layout-design`, `neqsim-pfd-layout-review` (the layout check every sheet must pass). For company-controlled
P&IDs, use the matching enterprise overlay skill (enterprise repositories only).

