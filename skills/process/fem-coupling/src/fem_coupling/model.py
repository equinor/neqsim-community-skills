"""Gate a finite-element study, and convert it into something a NeqSim model uses.

A finite-element temperature field is not, by itself, an engineering answer. Two
things have to happen to it. It has to survive a quality gate - discretisation,
mesh independence, energy balance, boundary placement - because a plausible-looking
field on an inadequate mesh is the normal failure mode. And it has to be reduced to
the small number of quantities a one-dimensional model actually consumes: an
overall U-value, a multiplier on that U-value, a hot-spot factor, a cooldown time.

That reduction is the point of the whole exercise. NeqSim's pipeline and cooldown
models work with a single U-value per section. A finite-element model exists to
tell them what that number should be when a hand calculation cannot - because the
insulation is damaged over part of the length, because a support or a clamp
short-circuits it, because the surrounding soil is not one-dimensional.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite

# Element counts through the layer that controls the answer. With linear elements
# a straight line is all one element can represent, so a curved profile needs
# three; quadratic elements carry the curvature themselves.
_MIN_LINEAR_ELEMENTS = 3
_MIN_QUADRATIC_ELEMENTS = 2

_MAX_ASPECT_RATIO = 20.0

# A finite-element energy balance should close far tighter than a CFD continuity
# error, because there is no turbulence model and no transport scheme in it.
_ENERGY_BALANCE_LIMIT_PERCENT = 1.0

# A far-field boundary closer than this many penetration depths is felt by the
# solution, so the boundary condition becomes an input to the answer.
_MIN_FAR_FIELD_RATIO = 3.0

# Below this Biot number the solid is nearly isothermal and a lumped model answers
# the question without a mesh.
_LUMPED_BIOT_LIMIT = 0.1


@dataclass(frozen=True)
class FemQualityResult:
    """Verdict on whether a finite-element study is fit to feed an engineering model."""

    verdict: str
    findings: tuple[str, ...]
    discretisation_ok: bool
    mesh_independence_ok: bool
    energy_balance_ok: bool
    boundary_placement_ok: bool
    time_resolution_ok: bool
    assumptions: tuple[str, ...]


@dataclass(frozen=True)
class FemThermalHandoff:
    """Finite-element result reduced to what a one-dimensional model consumes."""

    location: str
    overall_u_w_per_m2k: float
    reference_area_m2: float
    heat_flow_w: float
    one_dimensional_u_w_per_m2k: float | None
    u_multiplier: float | None
    hot_spot_factor: float | None
    source: str
    assumptions: tuple[str, ...]


@dataclass(frozen=True)
class FemResolutionPlan:
    """Element counts and time step implied by the physics of the problem."""

    layer_thickness_m: float
    element_size_m: float
    elements_across_layer: int
    element_order: int
    time_step_s: float | None
    assumptions: tuple[str, ...]


class FemCouplingModel:
    """Bridges finite-element results and one-dimensional engineering models.

    Three jobs, matching what the CFD-coupling model does for flow:

    1. Size the discretisation from the physics, so a mesh is chosen rather than
       inherited.
    2. Gate the study on the checks that decide whether its numbers mean anything -
       discretisation, mesh independence, energy balance, boundary placement.
    3. Reduce the field to an overall U-value, a U-multiplier and a hot-spot
       factor, which is the form a NeqSim pipeline or cooldown model can use.
    """

    def __init__(self, caution_multiplier: float = 3.0) -> None:
        _require_positive("caution_multiplier", caution_multiplier)
        self.caution_multiplier = caution_multiplier

    def plan_resolution(
        self,
        *,
        layer_thickness_m: float,
        max_element_size_m: float,
        element_order: int = 1,
        thermal_diffusivity_m2_per_s: float | None = None,
        mesh_fourier_target: float = 0.5,
    ) -> FemResolutionPlan:
        """Turn an element-size target into an element count and a time step.

        ``max_element_size_m`` normally comes from
        :func:`fem_coupling.thermal.derive_thermal_conditions`, which derives it
        from the thermal penetration depth, so the mesh follows the physics rather
        than a habit.
        """
        _require_positive("layer_thickness_m", layer_thickness_m)
        _require_positive("max_element_size_m", max_element_size_m)
        if element_order not in (1, 2):
            raise ValueError("element_order must be 1 or 2")

        minimum = _MIN_LINEAR_ELEMENTS if element_order == 1 else _MIN_QUADRATIC_ELEMENTS
        # The tolerance keeps an exact division such as 0.05 / 0.002 from rounding up
        # to an extra element on the floating-point representation alone.
        count = max(minimum, ceil(layer_thickness_m / max_element_size_m - 1.0e-9))
        size = layer_thickness_m / count

        time_step = None
        assumptions = [
            f"At least {minimum} element(s) across the layer, because order "
            f"{element_order} elements cannot represent curvature with fewer.",
        ]
        if thermal_diffusivity_m2_per_s is not None:
            _require_positive("thermal_diffusivity_m2_per_s", thermal_diffusivity_m2_per_s)
            _require_positive("mesh_fourier_target", mesh_fourier_target)
            time_step = mesh_fourier_target * size**2 / thermal_diffusivity_m2_per_s
            assumptions.append(
                f"Time step targets a mesh Fourier number of {mesh_fourier_target:g}; "
                "an implicit scheme is stable at any step but smears the front above it."
            )

        return FemResolutionPlan(
            layer_thickness_m=layer_thickness_m,
            element_size_m=size,
            elements_across_layer=count,
            element_order=element_order,
            time_step_s=time_step,
            assumptions=tuple(assumptions),
        )

    def assess_quality(
        self,
        *,
        element_order: int,
        elements_across_critical_layer: int,
        mesh_levels: int = 1,
        convergence_percent: float | None = None,
        max_aspect_ratio: float | None = None,
        energy_balance_error_percent: float | None = None,
        far_field_ratio: float | None = None,
        steady_state: bool = True,
        time_steps: int | None = None,
        mesh_fourier_number: float | None = None,
        biot: float | None = None,
        temperature_dependent_properties: bool = False,
    ) -> FemQualityResult:
        """Decide whether a finite-element study is fit to feed an engineering model.

        ``elements_across_critical_layer`` is the count across the layer that
        controls the answer - normally the metal wall for a stress question and the
        insulation for a heat-loss question, and they are not the same layer.
        """
        if element_order not in (1, 2):
            raise ValueError("element_order must be 1 or 2")
        if elements_across_critical_layer < 1:
            raise ValueError("elements_across_critical_layer must be at least 1")

        findings: list[str] = []

        minimum = _MIN_LINEAR_ELEMENTS if element_order == 1 else _MIN_QUADRATIC_ELEMENTS
        discretisation_ok = elements_across_critical_layer >= minimum
        if not discretisation_ok:
            findings.append(
                f"Only {elements_across_critical_layer} order-{element_order} element(s) "
                f"across the controlling layer; at least {minimum} are needed before the "
                "temperature drop across it means anything."
            )
        if max_aspect_ratio is not None:
            _require_positive("max_aspect_ratio", max_aspect_ratio)
            if max_aspect_ratio > _MAX_ASPECT_RATIO:
                discretisation_ok = False
                findings.append(
                    f"Worst element aspect ratio {max_aspect_ratio:.0f} exceeds "
                    f"{_MAX_ASPECT_RATIO:.0f}; gradients across the short edge are "
                    "poorly represented."
                )

        mesh_independence_ok = True
        if mesh_levels < 2:
            mesh_independence_ok = False
            findings.append(
                "Only one mesh reported, so mesh independence has not been "
                "demonstrated. A refined run is cheap for conduction - there is no "
                "excuse for skipping it."
            )
        if convergence_percent is not None:
            _require_finite("convergence_percent", convergence_percent)
            if abs(convergence_percent) > 5.0:
                mesh_independence_ok = False
                findings.append(
                    f"The quantity of interest moved {convergence_percent:.1f} % on "
                    "refinement; the solution is not mesh converged."
                )
            elif abs(convergence_percent) > 2.0:
                findings.append(
                    f"The quantity of interest moved {convergence_percent:.1f} % on "
                    "refinement; carry that as an uncertainty band."
                )

        energy_balance_ok = True
        if energy_balance_error_percent is None:
            energy_balance_ok = False
            findings.append(
                "No boundary energy balance was reported. For conduction it should "
                "close to a small fraction of a percent, so an unreported balance "
                "usually means it was never checked."
            )
        else:
            _require_finite("energy_balance_error_percent", energy_balance_error_percent)
            if abs(energy_balance_error_percent) > _ENERGY_BALANCE_LIMIT_PERCENT:
                energy_balance_ok = False
                findings.append(
                    f"Boundary energy balance closes to only "
                    f"{energy_balance_error_percent:.2f} %; a boundary condition is "
                    "probably missing or a material group is unassigned."
                )

        boundary_placement_ok = True
        if far_field_ratio is not None:
            _require_positive("far_field_ratio", far_field_ratio)
            if far_field_ratio < _MIN_FAR_FIELD_RATIO:
                boundary_placement_ok = False
                findings.append(
                    f"The far-field boundary sits {far_field_ratio:.1f} penetration "
                    f"depths away, below {_MIN_FAR_FIELD_RATIO:.0f}; the boundary "
                    "condition is now an input to the answer rather than a formality."
                )

        time_resolution_ok = True
        if not steady_state:
            if time_steps is not None and time_steps < 20:
                time_resolution_ok = False
                findings.append(
                    f"Only {time_steps} time steps cover the transient; an intermediate "
                    "time cannot be read off it."
                )
            if mesh_fourier_number is not None:
                _require_positive("mesh_fourier_number", mesh_fourier_number)
                if mesh_fourier_number > 5.0:
                    time_resolution_ok = False
                    findings.append(
                        f"Mesh Fourier number {mesh_fourier_number:.1f} is far above one; "
                        "an implicit scheme stays stable but the front is smeared, which "
                        "flatters a cooldown time and understates a thermal shock."
                    )

        if biot is not None and biot < _LUMPED_BIOT_LIMIT:
            findings.append(
                f"Biot number {biot:.3f} is below {_LUMPED_BIOT_LIMIT}; the solid is "
                "nearly isothermal and a lumped model would have answered this without "
                "a mesh."
            )
        if temperature_dependent_properties:
            findings.append(
                "Temperature-dependent properties make the problem nonlinear; confirm "
                "the iteration converged rather than stopping at the iteration limit."
            )

        blocking = [discretisation_ok, energy_balance_ok, boundary_placement_ok]
        if not any(blocking):
            verdict = "not_usable"
        elif all(
            [
                discretisation_ok,
                mesh_independence_ok,
                energy_balance_ok,
                boundary_placement_ok,
                time_resolution_ok,
            ]
        ):
            verdict = "usable"
        elif not energy_balance_ok and not discretisation_ok:
            verdict = "not_usable"
        else:
            verdict = "usable_with_caution"

        return FemQualityResult(
            verdict=verdict,
            findings=tuple(findings),
            discretisation_ok=discretisation_ok,
            mesh_independence_ok=mesh_independence_ok,
            energy_balance_ok=energy_balance_ok,
            boundary_placement_ok=boundary_placement_ok,
            time_resolution_ok=time_resolution_ok,
            assumptions=(
                "Screening quality gate for reusing a finite-element study, not a "
                "verification and validation review.",
                "A 'usable_with_caution' verdict means derived factors must carry an "
                "explicit uncertainty band in the receiving engineering model.",
                "The gate checks numerics, not physics: a converged solve of the wrong "
                "boundary condition passes every one of these checks.",
            ),
        )

    def evaluate_thermal_handoff(
        self,
        *,
        location: str,
        heat_flow_w: float,
        reference_area_m2: float,
        inner_bulk_temperature_c: float,
        outer_bulk_temperature_c: float,
        one_dimensional_heat_flow_w: float | None = None,
        peak_local_flux_w_per_m2: float | None = None,
    ) -> FemThermalHandoff:
        """Reduce a finite-element result to the U-value a one-dimensional model needs.

        ``one_dimensional_heat_flow_w`` is the heat flow the equivalent
        one-dimensional model predicts over the same length. The ratio is the
        multiplier a NeqSim pipeline or cooldown model should apply to its U-value:
        it is the number that carries a local insulation defect, a support
        short-circuit or a non-radial soil path into a model that cannot represent
        them.
        """
        if not location or not location.strip():
            raise ValueError("location must be a non-empty label")
        _require_positive("reference_area_m2", reference_area_m2)
        _require_finite("heat_flow_w", heat_flow_w)

        driving = inner_bulk_temperature_c - outer_bulk_temperature_c
        if abs(driving) < 1.0e-9:
            raise ValueError(
                "the inner and outer bulk temperatures are equal, so no U-value exists"
            )

        overall_u = heat_flow_w / (reference_area_m2 * driving)

        multiplier = None
        one_dimensional_u = None
        if one_dimensional_heat_flow_w is not None:
            _require_finite("one_dimensional_heat_flow_w", one_dimensional_heat_flow_w)
            if abs(one_dimensional_heat_flow_w) < 1.0e-12:
                raise ValueError("one_dimensional_heat_flow_w must be non-zero")
            one_dimensional_u = one_dimensional_heat_flow_w / (
                reference_area_m2 * driving
            )
            multiplier = heat_flow_w / one_dimensional_heat_flow_w

        hot_spot = None
        if peak_local_flux_w_per_m2 is not None:
            _require_finite("peak_local_flux_w_per_m2", peak_local_flux_w_per_m2)
            mean_flux = heat_flow_w / reference_area_m2
            if abs(mean_flux) > 1.0e-12:
                hot_spot = peak_local_flux_w_per_m2 / mean_flux

        assumptions = [
            "The U-value is referred to the area supplied; a U-value quoted on the "
            "outside diameter is not the same number as one quoted on the inside.",
            "The finite-element heat flow is for the modelled length only; extending "
            "it along a line assumes the geometry and the boundary conditions repeat.",
        ]
        if multiplier is not None:
            assumptions.append(
                "The multiplier is the ratio of the finite-element heat flow to the "
                "one-dimensional heat flow over the same length; it is specific to "
                "this geometry and this operating case."
            )
            if multiplier > self.caution_multiplier:
                assumptions.append(
                    f"Multiplier {multiplier:.1f} is large; confirm it is a real "
                    "short-circuit and not an over-specified boundary condition."
                )
        if hot_spot is not None:
            assumptions.append(
                "The hot-spot factor is a local peak. Use it for a stress or a "
                "deposition question, not for an overall heat balance."
            )

        return FemThermalHandoff(
            location=location.strip(),
            overall_u_w_per_m2k=overall_u,
            reference_area_m2=reference_area_m2,
            heat_flow_w=heat_flow_w,
            one_dimensional_u_w_per_m2k=one_dimensional_u,
            u_multiplier=None if multiplier is None else round(multiplier, 4),
            hot_spot_factor=None if hot_spot is None else round(hot_spot, 4),
            source="finite_element_field",
            assumptions=tuple(assumptions),
        )


def _require_positive(name: str, value: float | None) -> None:
    if value is None or not isfinite(float(value)) or float(value) <= 0.0:
        raise ValueError(f"{name} must be a finite positive number")


def _require_finite(name: str, value: float | None) -> None:
    if value is None or not isfinite(float(value)):
        raise ValueError(f"{name} must be a finite number")
