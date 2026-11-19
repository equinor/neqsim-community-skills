---
name: neqsim-well-trajectory-anticollision
calculation_basis: "screening"
version: "1.0.0"
description: "Educational 3D well path and anti-collision screening: minimum curvature, curve-hold from kick-off or sidetrack tie-in, reduced MWD uncertainty, ISCWSA separation factor against offsets, parent exit, slot check and target pull-back. USE WHEN: a task needs a concept well path, whether it clears existing wellbores, the governing offset, how far to move a target, or if a slot is free before an official anti-collision run."
last_verified: "2026-10-15"
requires:
  python_packages: ["numpy"]
  java_packages: []
  env: []
  network: []
---

# Well Trajectory and Anti-Collision Screening

Use this skill to build a concept well path in 3D and screen it against existing wellbores before the well
is entered into an official directional-planning system. It plans a vertical-kick-off or sidetrack
curve-hold path to a target, attaches position uncertainty, and computes the ISCWSA separation factor (SF)
against every offset segment. It reports the governing offset, the exit depth from a sidetrack parent and
the target pull-back needed to clear a limit.

The result is a screening answer. It is **not** an anti-collision approval: operator rules, certified
tool error models and the official planning system govern the well.

## When to Use

- A concept or prospect well needs a first 3D path from a template slot or a sidetrack of an existing bore.
- You need to check a planned path against existing wells and find the governing offset and its SF.
- A target sits close to an exploration or production well and you want to know how far to move it.
- You need to know whether a template slot is free, or whether the plan must be a slot-recovery sidetrack.
- You are deciding whether a sidetrack exits its parent bore cleanly and at what depth.

For reach and torque-and-drag limits on a 2D build-and-hold path, use `neqsim-erd-reach-screening`. Use
this skill for 3D geometry, uncertainty and anti-collision. The two are complementary.

## Inputs

| Input | Unit | Note |
| --- | --- | --- |
| Slot surface position (E, N, V) or parent survey | m | V is depth below one common datum for all wells (e.g. TVDSS). |
| Kick-off depth or tie-in MD | m | The tie-in must coincide with a parent survey station. |
| Target (E, N, V) | m | Same CRS and datum as the offsets. |
| Build/turn rate (DLS) | deg/30 m | Constant on the curve. |
| Offset surveys | MD, inc, az or E, N, V | Definitive surveys; covariances (m², E-N-V) when available. |
| SF rule | – | k = 3.5, Sm = 0.3 m, σpa = 0.5 m, STOP < 1.0 and CAUTION < 1.5 by default; replace with operator rules. |
| Hole radii | m | Default 0.156 m (12¼ in) for both wells; use actual hole or casing radii. |
| Geomagnetic field | nT, deg | Total field and dip for the reduced MWD model. |

## Outputs

- A planned `Wellpath`: MD, E, N, V, inclination, azimuth, DLS and 3×3 covariance per station.
- A plan summary: TD MD/V, hold inclination and azimuth, arc and hold lengths, max DLS, horizontal
  displacement, step-out ratio and target miss.
- A scan result with:
  - the SF table per offset (SF, centre-to-centre distance, reference and offset MD at the closest
    approach, ellipse sum, STOP/CAUTION/OK, parent flag);
  - an SF-versus-MD profile;
  - warnings.
- For parent bores: the last MD below STOP and below CAUTION, and the minimum SF after exit.
- A pull-back sweep with the first target position that meets the required SF.
- A slot-occupancy result per slot: FREE, OCCUPIED, RESERVED (planned bore) or RECOVERABLE.

## Engineering Method

1. **Survey positions.** Use minimum curvature with ratio factor RF = (2/β)·tan(β/2), where β is the
   dogleg between stations.
2. **Curve-hold.** Run a constant-curvature arc, radius R = 30 / (DLS·π/180), in the plane of the tie-in
   tangent t₀ and the target vector d. The arc angle θ solves the tangency condition
   `cos θ (b − R(1−cos θ)) − sin θ (a − R sin θ) = 0`, where a = d·t₀ and b = |d − a t₀|. It is solved by
   bisection. A target inside the turning circle (a² + (b − R)² < R²) is reported as unreachable.
3. **Uncertainty.** Run a reduced, systematic-only MWD model in the ISCWSA style:
   - Terms: depth scale and depth reference, misalignment, sag, declination, crustal/BH and axial
     interference.
   - Each term is propagated along the hole as fully correlated, and Cov = Σ eₖeₖᵀ.
   - A sidetrack inherits the parent's covariance at the tie-in.
   - Offsets keep their own definitive-survey covariance. The model is used only when that is missing,
     and a warning is raised.
4. **Separation factor** (Sawaryn et al. 2019):
   `SF = (D − Rr − Ro − Sm) / (k·√(nᵀ(Cr + Co)n + σpa²))`. D is the centre-to-centre distance from each
   reference station to the closest point on each offset segment, and n is its unit vector. The offset
   covariance is interpolated along the segment.
5. **Parent handling.** Skip parent segments above the tie-in. Track the parent SF below the tie-in and
   report where it last falls below the STOP and CAUTION limits (the exit depth).
6. **Pull-back.** Move the target towards the slot along the approach azimuth until the governing
   non-parent SF meets the required limit.

## Python Usage Pattern

```python
import numpy as np
from well_trajectory_anticollision import (ErrorModel, SFRule, Wellpath, add_model_covariance,
                                           plan_sidetrack, scan, governing, summarize)

model = ErrorModel(b_total_nt=50000.0, dip_deg=72.0)
parent = Wellpath.from_survey("P-1 H", md, inc_deg, az_deg, xyz=xyz_tvdss, cov=cov_enV)
offsets = [Wellpath.from_survey(n, *s) for n, s in offset_surveys.items()]

plan = add_model_covariance(plan_sidetrack(parent, tie_md=900.0, target=(1450.0, 2620.0, 2100.0),
                                           dls_deg30=3.0, name="P-1 AH plan"), model)
result = scan(plan, offsets + [parent], SFRule(), model=model)
print(summarize(plan), governing(result))
```

`examples/synthetic_template_example.py` runs the full synthetic workflow: slot check, sidetrack plan,
scan, pull-back and error-model check.

## Validation Checklist

- [ ] All wells share one CRS and one vertical datum. Converting each rig's RKB to MSL/TVDSS is the most
      common silent error.
- [ ] The tie-in MD is a parent survey station, and the tie-in inclination and azimuth match the parent.
- [ ] Target miss < 0.1 m and max DLS equals the requested DLS.
- [ ] Offsets carry definitive-survey covariances. Every "no survey covariance" warning is explained.
- [ ] `compare_growth` shows the reduced model is at least as conservative as a reference survey
      program (ratio ≥ 1). Otherwise scale the terms.
- [ ] The slot was checked with `group_by_surface` / `check_slot` against wellbore headers or the
      template register.
- [ ] Parent-bore STOP/CAUTION is expected only down to the exit depth. A parent SF that stays low below
      the exit means the sidetrack does not leave the parent.
- [ ] SF thresholds, k, hole radii and the error model are replaced with the operator's rule before any
      result is quoted.

## Common Mistakes

- **Mixing RKB datums.** Offsets drilled from different rigs have different RKB elevations. Use TVDSS
  (or another single datum) for every well, and keep MD only as each well's own measure.
- **Planning from an occupied slot.** Check slot occupancy first. A slot holding only closed bores
  means a slot-recovery sidetrack, not a new well.
- **Treating the parent as a collision risk above the tie-in.** Pass the parent names, or let the plan
  carry `parent`, so shared hole is skipped.
- **Reading the governing SF as minimum distance.** The SF uses the uncertainty projected on the
  separation vector. A diagonal separation with large vertical uncertainty can govern over a shorter
  horizontal one. That is expected.
- **Using the reduced model for offsets that already have survey covariances.** Use the definitive
  covariances.
- **Quoting the screening SF as approval.** The official planning-system anti-collision run governs.

## Limitations

- Reduced systematic MWD model only. It is not a certified ISCWSA/OWSG tool code and has no random,
  gyro, multi-station or IFR corrections. Uncertainty is the operator's to confirm.
- Closest-point (3D) scanning on survey segments only; no travelling-cylinder or normal-plane plots.
- One curve-hold per plan. S-shapes, multi-target and geosteering paths need several calls or a
  planning tool.
- No torque and drag, casing design or hydraulics. Use `neqsim-erd-reach-screening` for reach.
- Grid convergence, scale factor and magnetic reference are taken as already applied to the inputs.

## Related NeqSim Functionality

- `neqsim-erd-reach-screening`: 2D build-and-hold reach and Johancsik torque and drag.
- `neqsim-subsea-layout-geometry`, `neqsim-surf-field-layout-design`: template and slot geometry.
- `neqsim-uncertainty-quantification`: Monte Carlo over targets and error-model terms.
- `neqsim.process.equipment.reservoir.WellFlow` / well performance classes downstream of the path.

## References

- Sawaryn, S.J., Wilson, H., Bang, J., et al. (2019). *Well-Collision Avoidance Separation Rule.*
  SPE-194090-PA.
- Williamson, H.S. (2000). *Accuracy Prediction for Directional Measurement While Drilling.*
  SPE-67616-PA (ISCWSA error model).
- ISCWSA / SPE Wellbore Positioning Technical Section: error-model and collision-avoidance publications.
- Sawaryn, S.J., Thorogood, J.L. (2005). *A Compendium of Directional Calculations Based on the Minimum
  Curvature Method.* SPE-84246-PA.
