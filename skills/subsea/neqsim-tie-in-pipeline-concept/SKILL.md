---
name: neqsim-tie-in-pipeline-concept
calculation_basis: "screening"
version: "0.1.0"
description: "Screening of a new export or tie-in pipeline between two facilities: ranked landing points on neighbouring hosts, seabed profile from open EMODnet bathymetry, pressure drop, thermal decay, DNV-ST-F101 wall thickness and a recommended nominal size per rate case. USE WHEN: a task asks where an oil or gas line can be tied in, what size and wall thickness it needs, what inlet pressure a pump must deliver, or wants a pipe profile before a NeqSim pipeline study."
last_verified: "2026-10-20"
requires:
  python_packages: []
  java_packages: []
  env: []
  network: ["rest.emodnet-bathymetry.eu (only when no depth cache exists)"]
---

# Tie-in pipeline concept

Turns "can we connect A to B, with what pipe?" into numbers in minutes: candidate landing points, seabed
profile, hydraulics, thermal decay and wall thickness. Built from the Martin Linge to Oseberg oil export screening
(12 in x 9.5 mm X65, 44.5 km, 14 barg inlet at 2 600 Sm3/d, 26 barg at 6 000 Sm3/d).

## When to Use

- A host is being disconnected from its current export (tanker, FSO) or a new export route is wanted.
- A study needs a profile figure, an inlet-pressure requirement and a size for a line of tens of km.
- Several landing points are possible and the choice must be explained, not just picked.

Do not use for multiphase lines, gas export with hydrate or hydraulic stability issues, surge or pigging
studies, or any design-grade basis.

## Inputs

- Source and landing facility: name, `lat`, `lon` (WGS84). Sodir facility coordinates are in the
  `neqsim-ncs-infrastructure-network` snapshot (`hosts`).
- Oil properties (`OilProperties`): standard density, viscosity at inlet and sea temperature. Take them from the
  stabilised cargo or export stream of a NeqSim process model; flash at line conditions with water removed.
- Rate cases in Sm3/d, a design case and a turndown case. Cite where each number comes from (measured production, forecast).
- Design-basis overrides (`basis_overrides`): arrival pressure, design pressure, inlet temperature, steel grade,
  corrosion allowance, riser height. Every default is an assumption: list the ones you did not confirm.

## Workflow

1. `rank_candidates(source, hosts, feeds_into, terminal_hosts, spare_capacity_fraction)`. Pass existing feeders
   from the network graph; the rationale string of every score term goes into the report.
2. Choose the landing point with the user (or take rank 1 and say so).
3. `run_concept(...)` or call `build_profile`, `profile_statistics`, `size_pipeline` separately. Cache EMODnet
   responses in `references/emodnet/` of the task.
4. Check: end-point depths against the reported facility water depth (a few metres), velocity window, inlet
   pressure against the design pressure, D/t limit, steep intervals in `statistics['steep_intervals']`.
5. Cross-check the chosen size with NeqSim `PipeBeggsAndBrills` (segments of about 1 km, `setElevation` per
   segment, `setConstantSurfaceTemperature` plus `setHeatTransferCoefficient`). Keep the dry-oil fluid; do not
   pass water-containing cargo oil (a trace of water gave a second phase and a convergence failure in testing).
6. Hand off to `neqsim-tie-in-pid-sketch` for the end connections and to an enterprise overlay skill for 3D views.

## Engineering Method

- Corridor: great-circle line sampled every `spacing_km` (default 0.5 km) with EMODnet bathymetry depths; the
  profile gives 3D length, net elevation and steep intervals.
- Hydraulics: single-phase liquid, Haaland friction, constant overall heat-transfer coefficient, density and
  viscosity corrected for temperature along the line.
- Wall thickness: pressure containment and collapse limit states of DNV-ST-F101 plus a D/t handling limit, evaluated
  per nominal size; the smallest size that passes velocity, pressure and D/t checks is recommended.
- Landing candidates: ranked by distance, existing feeders, terminal status and spare capacity; each score term
  carries a rationale string.

## Outputs

`candidates` with score rationale, `profile`, `statistics`, `sizing` (wall per size, cases, recommended size and
the rejection reason for each smaller size), `basis` and `assumptions`. Add them to `results.json` with the
assumptions and data gaps below.

## Always state

Arrival pressure at the landing point, steel and design pressure, that the corridor is a straight line, that
upstream water handling and stabilisation are outside the line, and that free span, stability, buckling, surge,
wax and pigging are not assessed.

**Read the landing pressure from the host P&ID, do not assume it.** The Martin Linge screening used 10 barg
arrival; the Oseberg A P&ID of the export oil booster pumps (11-1A-KE-T01-21-EC-00211) shows 45 barg pump
discharge and 43.2 bar differential, so the booster suction is only about 2 barg. A tie-in upstream of the boosters
needs a few barg at arrival; a tie-in downstream needs the full header pressure at the source and a higher design
pressure. Run both landing options through `size_pipeline` with `arrival_pressure_barg` set from the sheet, and say
which sheet and revision the pressure came from.

## Python Usage Pattern

```python
from tie_in_pipeline_concept import OilProperties, run_concept

# props: OilProperties(...) from the stabilised export stream of a NeqSim model (see OilProperties fields)
result = run_concept(
    {"name": "Source A", "lat": 60.5, "lon": 2.0},
    {"name": "Landing B", "lat": 60.5, "lon": 2.8},
    props,
    {"turndown": 2600.0, "design": 6000.0},  # Sm3/d per case
    "design",
    "turndown",
    hosts=[{"name": "Landing B", "lat": 60.5, "lon": 2.8}],
    basis_overrides={"arrival_pressure_barg": 12.0},
)
print(result["sizing"]["recommended"], result["statistics"]["route_3d_length_km"])
```

## Validation Checklist

- [ ] End-point depths agree with the reported facility water depths.
- [ ] Velocity is inside the allowed window for both the design and the turndown case.
- [ ] Inlet pressure is below the design pressure, and the arrival pressure comes from a cited host document.
- [ ] D/t is within the handling limit and the governing wall-thickness limit state is named.
- [ ] Every default in `basis` that was not confirmed is listed under assumptions.
- [ ] Recommended size is cross-checked against a NeqSim `PipeBeggsAndBrills` run on dry oil.

## Common Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Inlet pressure far too high | Riser elevation or arrival pressure forgotten | Check `net_elevation_m` and `arrival_pressure_barg` |
| NeqSim pipe run fails with negative outlet pressure | Start pressure too low for the line | Start at 150 bara and iterate down |
| `D/t` governs the wall, not pressure | Low design pressure on a large diameter | Normal; D/t <= 35 is a handling limit, state it |
| Wrong depth sign | EMODnet returns elevation, negative down | `fetch_emodnet_depth` already negates |

## Limitations

Single-phase, constant U, Haaland friction, hand implementation of two DNV-ST-F101 limit states, DTM resolution
of several hundred metres. Use `DnvStF101PipelineDesignCalculator` in NeqSim for the full limit-state set.

## References

- DNV-ST-F101, Submarine pipeline systems.
- EMODnet Bathymetry (https://emodnet.ec.europa.eu/en/bathymetry), open digital terrain model.
- Haaland, S.E. (1983), Simple and explicit formulas for the friction factor in turbulent pipe flow, J. Fluids Eng.

## Related

`neqsim-pipe-route-profile`, `neqsim-bathymetry-profile-screening`, `neqsim-ncs-infrastructure-network`,
`neqsim-pressure-drop-screening`, `neqsim-pipe-wall-thickness-screening`, `neqsim-tie-in-pid-sketch`.
