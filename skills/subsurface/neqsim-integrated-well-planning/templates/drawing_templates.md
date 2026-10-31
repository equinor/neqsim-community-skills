# Drawing templates

All sheets are A3 landscape (420 x 297 mm) from `iwp_style.a3_sheet`: border, title block (project, title, drawing number, scale/sheet), revision block, status line, SYNTHETIC stamp when the study is synthetic, optional north arrow and scale bar.

| Drawing no. | Content | Function |
|---|---|---|
| `<study>-DWG-001` | Well schematic: casing/liner shoes with sizes and grades, cement hatching, tubing, packer, safety valve, mandrels, perforations, tree, formation tops and contacts, MD/TVD/TVDSS scales, pore/fracture/mud tracks, inclination and DLS on a shared depth axis | `iwp_drawings.well_schematic_sheet` |
| `<study>-DWG-002` | Barrier schematics per well state with primary (blue) and secondary (red) envelopes, element list and verification status | `iwp_drawings.barrier_schematic_sheet` |
| figures F03-F20 | Nodal analysis, profiles, envelope chart/table, alternatives, sensitivities, deliverability bands, Gantt, time-depth, risk, decision tree, trajectory | `iwp_graphics.render` |

Export: `iwp_drawings.render_sheet` writes 300 dpi PNG, vector PDF (TrueType embedded) and SVG plus `<name>.provenance.json`. Charts use `iwp_graphics.render` (PNG 300 dpi plus sidecar). Revision control: pass `revisions=[(rev, date, description), ...]`.
