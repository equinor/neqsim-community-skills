# neqsim-integrated-well-planning

Integrated well planning for NeqSim: planning basis with provenance, a reservoir-well-facility chain for oil, gas-condensate, water-injection and gas-injection wells (onshore, platform, subsea), operating envelopes, barrier schematics, alternatives, A3 drawings, versioned hand-off schemas and a well-planning report with an honest capability ledger.

- Skill definition: [`SKILL.md`](SKILL.md) (method, ledger, schemas, visual design system, validation checklist).
- Package: `src/integrated_well_planning` - `basis`, `registers`, `datums`, `standards`, `runtime`, `model_chain`, `nodal`, `producers`, `injectors`, `integrity`, `barriers`, `envelope`, `flow_assurance`, `alternatives`, `drilling_interfaces`, `handoff`, `ledger`, `iwp_style`, `iwp_graphics`, `iwp_drawings`, `drawings_run`, `planning_extras`, `report`, `study`, `cli`.
- CLI: `<python> -m integrated_well_planning init-study | validate-basis | run-model | envelope | alternatives | drawings | report | all | ledger | runtime | list-cases`.
- Schemas: [`schemas/`](schemas) (`iwp_*.v1.json`). Templates: [`templates/`](templates). Examples: [`examples/`](examples) (four synthetic cases).
- Tests: `<python> -m pytest -q -p no:cacheprovider` from this folder. NeqSim-backed tests run when the `neqsim.process.fielddevelopment.wellplanning` classes are on the classpath (`IWP_NEQSIM_CLASSPATH`, `NEQSIM_PROJECT_ROOT`, a sibling `neqsim` checkout or the installed package) and skip with an explicit reason otherwise.
- Requires the drilling/casing module [`neqsim-well-design-study`](../neqsim-well-design-study).

Human review is required; the skill does not replace detailed well design, well control, geomechanics, cementing, anti-collision or specialist integrity work and makes no compliance statement.
