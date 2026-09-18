"""A dependency-free one-dimensional multilayer conduction finite-element solver.

This is the layer that makes the skill useful before any external finite-element
package is installed. It assembles and solves linear P1 finite elements through a
composite wall - steel, coating, insulation, cement, formation - in cylindrical or
planar coordinates, with Robin (convective film) conditions on both surfaces.

One dimension covers a surprising amount of real work: an insulated pipe wall, a
vessel shell, a wellbore-to-cement-to-formation stack, a plate through-thickness
profile. Two and three dimensions - a local insulation defect, a nozzle, a buried
pipeline with a seabed - are delegated to scikit-fem or FEniCSx through
:mod:`fem_coupling.solver`, but they should not be reached for until the
one-dimensional answer is understood, because that answer can be checked against a
closed-form thermal resistance and the two- and three-dimensional ones cannot.

The steady solve is verified against the analytic composite-cylinder resistance,
which is what turns a finite-element result from a plot into a number that can be
defended.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, log, pi
from typing import Sequence

from .materials import SolidMaterial

# Picard sweeps for temperature-dependent conductivity. Conductivity varies weakly
# and almost linearly over an engineering temperature band, so this converges in a
# few sweeps or not at all - a large iteration budget would hide a bad property fit.
_MAX_NONLINEAR_SWEEPS = 12
_NONLINEAR_TOLERANCE_K = 1.0e-4


@dataclass(frozen=True)
class ConductionLayer:
    """One material layer in the conduction stack."""

    name: str
    material: SolidMaterial
    thickness_m: float
    elements: int = 8

    def __post_init__(self) -> None:
        _require_positive("thickness_m", self.thickness_m)
        if self.elements < 1:
            raise ValueError(f"layer '{self.name}' needs at least one element")


@dataclass(frozen=True)
class SteadyConductionResult:
    """Steady temperature profile and the engineering quantities derived from it."""

    coordinates_m: tuple[float, ...]
    temperatures_c: tuple[float, ...]
    inner_surface_temperature_c: float
    outer_surface_temperature_c: float
    interface_temperatures_c: tuple[tuple[str, float], ...]
    heat_flux_inner_w_per_m2: float
    heat_flow_per_length_w_per_m: float | None
    overall_u_inner_w_per_m2k: float
    thermal_resistance_m2k_per_w: float
    analytic_heat_flux_inner_w_per_m2: float
    analytic_deviation_percent: float
    nonlinear_sweeps: int
    nonlinear_converged: bool
    warnings: tuple[str, ...]
    assumptions: tuple[str, ...]


@dataclass(frozen=True)
class TransientConductionResult:
    """Transient temperature history through the wall."""

    coordinates_m: tuple[float, ...]
    times_s: tuple[float, ...]
    temperatures_c: tuple[tuple[float, ...], ...]
    inner_surface_history_c: tuple[float, ...]
    outer_surface_history_c: tuple[float, ...]
    inner_fluid_history_c: tuple[float, ...]
    time_step_s: float
    steps: int
    warnings: tuple[str, ...]
    assumptions: tuple[str, ...]

    def time_to_reach(
        self, target_temperature_c: float, *, location: str = "inner_fluid"
    ) -> float | None:
        """Time at which a location first crosses a target temperature, or ``None``.

        This is the cooldown question: how long before the fluid reaches the hydrate
        or wax temperature. ``location`` is ``inner_fluid`` (only meaningful when the
        bore fluid was given a thermal capacity), ``inner_surface`` or
        ``outer_surface``. Linear interpolation between stored samples is used, so
        the answer is only as fine as the sampling interval.
        """
        key = (location or "").strip().lower()
        if key == "inner_fluid":
            history = self.inner_fluid_history_c or self.inner_surface_history_c
        elif key == "inner_surface":
            history = self.inner_surface_history_c
        elif key == "outer_surface":
            history = self.outer_surface_history_c
        else:
            raise ValueError(
                "location must be 'inner_fluid', 'inner_surface' or 'outer_surface'"
            )

        if not history:
            return None
        falling = history[-1] < history[0]
        for index in range(1, len(history)):
            previous, current = history[index - 1], history[index]
            crossed = (
                (previous > target_temperature_c >= current)
                if falling
                else (previous < target_temperature_c <= current)
            )
            if crossed:
                span = current - previous
                if abs(span) < 1.0e-12:
                    return self.times_s[index]
                fraction = (target_temperature_c - previous) / span
                return self.times_s[index - 1] + fraction * (
                    self.times_s[index] - self.times_s[index - 1]
                )
        return None


class RadialConductionModel:
    """Composite-wall conduction on a one-dimensional finite-element mesh.

    ``geometry`` is ``cylindrical`` (a pipe, a shell, a wellbore) or ``planar``
    (a plate, a flat wall). For a cylindrical model ``inner_radius_m`` is the bore
    radius; for a planar model the coordinate simply starts at zero.
    """

    def __init__(
        self,
        layers: Sequence[ConductionLayer],
        *,
        inner_radius_m: float | None = None,
        geometry: str = "cylindrical",
    ) -> None:
        if not layers:
            raise ValueError("at least one conduction layer is required")
        self.geometry = (geometry or "").strip().lower()
        if self.geometry not in {"cylindrical", "planar"}:
            raise ValueError("geometry must be 'cylindrical' or 'planar'")
        if self.geometry == "cylindrical":
            _require_positive("inner_radius_m", inner_radius_m)
            self.inner_coordinate = float(inner_radius_m)
        else:
            self.inner_coordinate = 0.0

        self.layers = tuple(layers)
        self.coordinates, self.element_layers = _build_mesh(
            self.layers, self.inner_coordinate
        )
        self.total_thickness_m = self.coordinates[-1] - self.coordinates[0]

    # ------------------------------------------------------------------ steady

    def solve_steady(
        self,
        *,
        inner_film_coefficient_w_per_m2k: float,
        inner_bulk_temperature_c: float,
        outer_film_coefficient_w_per_m2k: float,
        outer_bulk_temperature_c: float,
    ) -> SteadyConductionResult:
        """Solve the steady profile and cross-check it against the analytic resistance."""
        _require_positive(
            "inner_film_coefficient_w_per_m2k", inner_film_coefficient_w_per_m2k
        )
        _require_positive(
            "outer_film_coefficient_w_per_m2k", outer_film_coefficient_w_per_m2k
        )

        node_count = len(self.coordinates)
        guess = [
            inner_bulk_temperature_c
            + (outer_bulk_temperature_c - inner_bulk_temperature_c)
            * (index / (node_count - 1))
            for index in range(node_count)
        ]

        temperatures = guess
        sweeps = 0
        converged = False
        for sweeps in range(1, _MAX_NONLINEAR_SWEEPS + 1):
            conductivities = self._layer_conductivities(temperatures)
            diagonal, lower, upper, rhs = self._assemble_stiffness(conductivities)

            inner_weight = self._weight(self.coordinates[0])
            outer_weight = self._weight(self.coordinates[-1])
            diagonal[0] += inner_film_coefficient_w_per_m2k * inner_weight
            rhs[0] += inner_film_coefficient_w_per_m2k * inner_weight * inner_bulk_temperature_c
            diagonal[-1] += outer_film_coefficient_w_per_m2k * outer_weight
            rhs[-1] += (
                outer_film_coefficient_w_per_m2k * outer_weight * outer_bulk_temperature_c
            )

            updated = _solve_tridiagonal(lower, diagonal, upper, rhs)
            change = max(abs(a - b) for a, b in zip(updated, temperatures))
            temperatures = updated
            if change < _NONLINEAR_TOLERANCE_K:
                converged = True
                break

        inner_surface = temperatures[0]
        outer_surface = temperatures[-1]
        flux_inner = inner_film_coefficient_w_per_m2k * (
            inner_bulk_temperature_c - inner_surface
        )
        driving = inner_bulk_temperature_c - outer_bulk_temperature_c

        heat_per_length = None
        if self.geometry == "cylindrical":
            heat_per_length = flux_inner * 2.0 * pi * self.coordinates[0]

        analytic_flux, analytic_resistance = self._analytic_flux(
            inner_film_coefficient_w_per_m2k,
            inner_bulk_temperature_c,
            outer_film_coefficient_w_per_m2k,
            outer_bulk_temperature_c,
            self._layer_conductivities(temperatures),
        )
        deviation = (
            100.0 * abs(flux_inner - analytic_flux) / abs(analytic_flux)
            if abs(analytic_flux) > 1.0e-12
            else 0.0
        )

        warnings: list[str] = []
        if not converged:
            warnings.append(
                "Temperature-dependent conductivity did not converge within "
                f"{_MAX_NONLINEAR_SWEEPS} sweeps; check the conductivity coefficients."
            )
        if deviation > 1.0:
            warnings.append(
                f"Finite-element flux deviates {deviation:.2f} % from the closed-form "
                "resistance; refine the mesh before quoting the profile."
            )
        for layer in self.layers:
            if layer.elements < 3:
                warnings.append(
                    f"Layer '{layer.name}' has only {layer.elements} elements; a "
                    "curved profile through it cannot be resolved."
                )
        warnings.extend(self._service_warnings(temperatures))

        return SteadyConductionResult(
            coordinates_m=tuple(self.coordinates),
            temperatures_c=tuple(temperatures),
            inner_surface_temperature_c=inner_surface,
            outer_surface_temperature_c=outer_surface,
            interface_temperatures_c=self._interface_temperatures(temperatures),
            heat_flux_inner_w_per_m2=flux_inner,
            heat_flow_per_length_w_per_m=heat_per_length,
            overall_u_inner_w_per_m2k=flux_inner / driving if abs(driving) > 1.0e-12 else 0.0,
            thermal_resistance_m2k_per_w=analytic_resistance,
            analytic_heat_flux_inner_w_per_m2=analytic_flux,
            analytic_deviation_percent=deviation,
            nonlinear_sweeps=sweeps,
            nonlinear_converged=converged,
            warnings=tuple(warnings),
            assumptions=(
                "Linear P1 elements on a one-dimensional mesh; the profile is "
                "piecewise linear within each element.",
                "Perfect thermal contact between layers - no contact resistance, no "
                "annulus gap, no water ingress into the insulation.",
                "Conductivity is evaluated at each layer's mean temperature and "
                "iterated to convergence.",
                "Axial conduction is neglected, which is valid while the geometry and "
                "the boundary conditions do not change along the axis.",
            ),
        )

    # ------------------------------------------------------------- calibration

    def calibrate_outer_bulk_temperature(
        self,
        *,
        target_inner_surface_temperature_c: float,
        inner_film_coefficient_w_per_m2k: float,
        inner_bulk_temperature_c: float,
        outer_film_coefficient_w_per_m2k: float,
        tolerance_k: float = 1.0e-6,
        max_iterations: int = 12,
    ) -> float:
        """Outer bulk temperature that produces a known inner-surface temperature.

        The far-side condition is often the one nobody measured - the flue gas
        outside a tube, the soil around a buried line, the ambient behind a wall -
        while the near-side metal or film temperature is stated on a data sheet.
        This inverts the steady solve so the unmeasured boundary is calibrated to
        the number that *is* known, rather than assumed and then found to disagree.

        The relationship is linear for constant conductivity, so two solves are
        exact there; the iteration only earns its keep when conductivity depends on
        temperature. Sanity-check the result: an implied far-side temperature that
        is not physically credible means the assumed outer film coefficient, not
        the calibration, is wrong.
        """
        _require_positive(
            "inner_film_coefficient_w_per_m2k", inner_film_coefficient_w_per_m2k
        )
        _require_positive(
            "outer_film_coefficient_w_per_m2k", outer_film_coefficient_w_per_m2k
        )

        def inner_surface(outer_bulk_c: float) -> float:
            return self.solve_steady(
                inner_film_coefficient_w_per_m2k=inner_film_coefficient_w_per_m2k,
                inner_bulk_temperature_c=inner_bulk_temperature_c,
                outer_film_coefficient_w_per_m2k=outer_film_coefficient_w_per_m2k,
                outer_bulk_temperature_c=outer_bulk_c,
            ).inner_surface_temperature_c

        low = inner_bulk_temperature_c
        high = inner_bulk_temperature_c + 100.0
        surface_low, surface_high = inner_surface(low), inner_surface(high)

        for _ in range(max_iterations):
            slope = surface_high - surface_low
            if abs(slope) < 1.0e-12:
                raise ValueError(
                    "the inner surface temperature does not respond to the outer "
                    "bulk temperature; check the film coefficients"
                )
            guess = low + (high - low) * (
                target_inner_surface_temperature_c - surface_low
            ) / slope
            surface = inner_surface(guess)
            if abs(surface - target_inner_surface_temperature_c) < tolerance_k:
                return guess
            low, surface_low = high, surface_high
            high, surface_high = guess, surface

        raise ValueError(
            "outer bulk temperature calibration did not converge; check that the "
            "target inner surface temperature is reachable with these coefficients"
        )

    # --------------------------------------------------------------- transient
    def solve_transient(
        self,
        *,
        initial_temperature_c: float | Sequence[float],
        duration_s: float,
        time_step_s: float,
        inner_film_coefficient_w_per_m2k: float,
        inner_bulk_temperature_c: float,
        outer_film_coefficient_w_per_m2k: float,
        outer_bulk_temperature_c: float,
        inner_fluid_capacity: float | None = None,
        sample_count: int = 50,
    ) -> TransientConductionResult:
        """Integrate the transient profile with backward Euler.

        Backward Euler is unconditionally stable, so the time step is chosen to
        resolve the front rather than to keep the solve from diverging. It is
        first-order and numerically damped, which is conservative for a cooldown
        question and non-conservative for a thermal-shock stress question - use a
        step from :func:`fem_coupling.thermal.derive_thermal_conditions` rather
        than a convenient round number.

        Leaving ``inner_fluid_capacity`` as ``None`` holds the bore fluid at
        ``inner_bulk_temperature_c`` for the whole window, which answers a
        thermal-shock question but not a cooldown one: a shut-in line has no source
        holding the fluid warm. Supplying the capacity of the trapped fluid instead
        makes the bulk temperature a state variable coupled to the wall through the
        inner film, which is the cooldown model. Units are ``rho cp A_bore`` in
        J/(m.K) for a cylindrical model and ``rho cp t`` in J/(m^2.K) for a planar
        one; NeqSim supplies the density and heat capacity of the shut-in fluid.
        """
        _require_positive("duration_s", duration_s)
        _require_positive("time_step_s", time_step_s)
        _require_positive(
            "inner_film_coefficient_w_per_m2k", inner_film_coefficient_w_per_m2k
        )
        _require_positive(
            "outer_film_coefficient_w_per_m2k", outer_film_coefficient_w_per_m2k
        )
        if sample_count < 2:
            raise ValueError("sample_count must be at least 2")

        node_count = len(self.coordinates)
        if isinstance(initial_temperature_c, (int, float)):
            wall_initial = [float(initial_temperature_c)] * node_count
        else:
            wall_initial = [float(value) for value in initial_temperature_c]
            if len(wall_initial) != node_count:
                raise ValueError(
                    f"initial temperature vector has {len(wall_initial)} entries but the "
                    f"mesh has {node_count} nodes"
                )

        conductivities = self._layer_conductivities(wall_initial)
        wall_k_diag, wall_k_lower, wall_k_upper, _ = self._assemble_stiffness(conductivities)
        wall_m_diag, wall_m_lower, wall_m_upper = self._assemble_mass()

        # A bore fluid with its own capacity becomes one extra node ahead of the
        # wall. It couples only to the inner surface, so the system stays tridiagonal.
        track_fluid = inner_fluid_capacity is not None
        offset = 1 if track_fluid else 0
        size = node_count + offset

        k_diag = [0.0] * size
        k_lower = [0.0] * (size - 1)
        k_upper = [0.0] * (size - 1)
        m_diag = [0.0] * size
        m_lower = [0.0] * (size - 1)
        m_upper = [0.0] * (size - 1)
        load = [0.0] * size

        for index in range(node_count):
            k_diag[index + offset] += wall_k_diag[index]
            m_diag[index + offset] += wall_m_diag[index]
        for index in range(node_count - 1):
            k_lower[index + offset] += wall_k_lower[index]
            k_upper[index + offset] += wall_k_upper[index]
            m_lower[index + offset] += wall_m_lower[index]
            m_upper[index + offset] += wall_m_upper[index]

        inner_weight = self._weight(self.coordinates[0])
        outer_weight = self._weight(self.coordinates[-1])
        inner_coupling = inner_film_coefficient_w_per_m2k * inner_weight

        if track_fluid:
            _require_positive("inner_fluid_capacity", inner_fluid_capacity)
            # The Robin terms carry the geometric weight without the 2*pi factor, so
            # the fluid capacity is scaled the same way to stay consistent.
            scale = 1.0 / (2.0 * pi) if self.geometry == "cylindrical" else 1.0
            m_diag[0] += float(inner_fluid_capacity) * scale
            k_diag[0] += inner_coupling
            k_diag[1] += inner_coupling
            k_lower[0] -= inner_coupling
            k_upper[0] -= inner_coupling
        else:
            k_diag[0] += inner_coupling
            load[0] += inner_coupling * inner_bulk_temperature_c

        k_diag[-1] += outer_film_coefficient_w_per_m2k * outer_weight
        load[-1] += (
            outer_film_coefficient_w_per_m2k * outer_weight * outer_bulk_temperature_c
        )

        temperatures = ([float(inner_bulk_temperature_c)] if track_fluid else []) + wall_initial

        steps = max(1, int(round(duration_s / time_step_s)))
        dt = duration_s / steps

        system_diag = [m / dt + k for m, k in zip(m_diag, k_diag)]
        system_lower = [m / dt + k for m, k in zip(m_lower, k_lower)]
        system_upper = [m / dt + k for m, k in zip(m_upper, k_upper)]

        sample_every = max(1, steps // (sample_count - 1))
        times = [0.0]
        history = [tuple(temperatures)]

        for step in range(1, steps + 1):
            rhs = _tridiagonal_multiply(m_lower, m_diag, m_upper, temperatures)
            rhs = [value / dt + source for value, source in zip(rhs, load)]
            temperatures = _solve_tridiagonal(system_lower, system_diag, system_upper, rhs)
            if step % sample_every == 0 or step == steps:
                times.append(step * dt)
                history.append(tuple(temperatures))

        warnings: list[str] = []
        if steps < 20:
            warnings.append(
                f"Only {steps} time steps cover the window; the response is resolved by "
                "too few points to read an intermediate time off the history."
            )
        slowest = min(
            layer.material.thermal_diffusivity_at(wall_initial[0]) for layer in self.layers
        )
        wall_response_s = self.total_thickness_m**2 / slowest
        if dt > wall_response_s / 50.0:
            warnings.append(
                f"Time step {dt:.3g} s is coarse against the wall diffusion time "
                f"{wall_response_s:.3g} s; backward Euler stays stable but the thermal "
                "front will be numerically smeared."
            )
        if not track_fluid:
            warnings.append(
                "The bore fluid was held at a fixed bulk temperature, so this is not a "
                "cooldown model; supply inner_fluid_capacity to let it cool."
            )

        assumptions = [
            "Backward Euler time integration with a consistent mass matrix: "
            "unconditionally stable, first order, numerically damped.",
            "The outer film coefficient and ambient temperature are constant over "
            "the window.",
            "No phase change, no latent heat and no wax or hydrate deposition.",
        ]
        if track_fluid:
            assumptions.append(
                "The bore fluid is one well-mixed lumped mass at a single temperature; "
                "stratification and natural convection inside the bore are neglected, "
                "and the internal film coefficient is held at its supplied value even "
                "though it falls once forced flow stops."
            )

        return TransientConductionResult(
            coordinates_m=tuple(self.coordinates),
            times_s=tuple(times),
            temperatures_c=tuple(row[offset:] for row in history),
            inner_surface_history_c=tuple(row[offset] for row in history),
            outer_surface_history_c=tuple(row[-1] for row in history),
            inner_fluid_history_c=tuple(row[0] for row in history) if track_fluid else (),
            time_step_s=dt,
            steps=steps,
            warnings=tuple(warnings),
            assumptions=tuple(assumptions),
        )

    # ----------------------------------------------------------------- helpers

    def _weight(self, coordinate: float) -> float:
        return coordinate if self.geometry == "cylindrical" else 1.0

    def _layer_conductivities(self, temperatures: Sequence[float]) -> list[float]:
        """Conductivity per element, evaluated at that element's mean temperature."""
        values: list[float] = []
        for index, layer_index in enumerate(self.element_layers):
            mean = 0.5 * (temperatures[index] + temperatures[index + 1])
            values.append(self.layers[layer_index].material.conductivity_at(mean))
        return values

    def _assemble_stiffness(
        self, conductivities: Sequence[float]
    ) -> tuple[list[float], list[float], list[float], list[float]]:
        node_count = len(self.coordinates)
        diagonal = [0.0] * node_count
        lower = [0.0] * (node_count - 1)
        upper = [0.0] * (node_count - 1)
        rhs = [0.0] * node_count

        for element, conductivity in enumerate(conductivities):
            left = self.coordinates[element]
            right = self.coordinates[element + 1]
            length = right - left
            # Integral of the geometric weight over the element.
            integral = length * 0.5 * (left + right) if self.geometry == "cylindrical" else length
            stiffness = conductivity * integral / length**2
            diagonal[element] += stiffness
            diagonal[element + 1] += stiffness
            lower[element] -= stiffness
            upper[element] -= stiffness

        return diagonal, lower, upper, rhs

    def _assemble_mass(self) -> tuple[list[float], list[float], list[float]]:
        node_count = len(self.coordinates)
        diagonal = [0.0] * node_count
        lower = [0.0] * (node_count - 1)
        upper = [0.0] * (node_count - 1)

        for element, layer_index in enumerate(self.element_layers):
            left = self.coordinates[element]
            right = self.coordinates[element + 1]
            length = right - left
            capacity = self.layers[layer_index].material.volumetric_heat_capacity_j_per_m3k()
            if self.geometry == "cylindrical":
                m11 = capacity * length * (left / 3.0 + length / 12.0)
                m22 = capacity * length * (left / 3.0 + length / 4.0)
                m12 = capacity * length * (left / 6.0 + length / 12.0)
            else:
                m11 = capacity * length / 3.0
                m22 = capacity * length / 3.0
                m12 = capacity * length / 6.0
            diagonal[element] += m11
            diagonal[element + 1] += m22
            lower[element] += m12
            upper[element] += m12

        return diagonal, lower, upper

    def _interface_temperatures(
        self, temperatures: Sequence[float]
    ) -> tuple[tuple[str, float], ...]:
        entries: list[tuple[str, float]] = []
        node = 0
        for layer in self.layers:
            entries.append((f"{layer.name} inner face", temperatures[node]))
            node += layer.elements
            entries.append((f"{layer.name} outer face", temperatures[node]))
        return tuple(entries)

    def _service_warnings(self, temperatures: Sequence[float]) -> list[str]:
        warnings: list[str] = []
        node = 0
        for layer in self.layers:
            hottest = max(temperatures[node], temperatures[node + layer.elements])
            coldest = min(temperatures[node], temperatures[node + layer.elements])
            warnings.extend(layer.material.service_warnings(hottest))
            warnings.extend(layer.material.service_warnings(coldest))
            node += layer.elements
        return warnings

    def _analytic_flux(
        self,
        inner_film: float,
        inner_bulk: float,
        outer_film: float,
        outer_bulk: float,
        conductivities: Sequence[float],
    ) -> tuple[float, float]:
        """Closed-form flux and resistance, referred to the inner surface area."""
        inner = self.coordinates[0]
        outer = self.coordinates[-1]

        if self.geometry == "cylindrical":
            resistance = 1.0 / (inner_film * 2.0 * pi * inner)
            node = 0
            for layer_index, layer in enumerate(self.layers):
                start = self.coordinates[node]
                node += layer.elements
                end = self.coordinates[node]
                # Element conductivities within a layer differ only through the
                # temperature dependence; their mean is the layer value.
                members = [
                    conductivities[i]
                    for i, owner in enumerate(self.element_layers)
                    if owner == layer_index
                ]
                conductivity = sum(members) / len(members) if members else 1.0
                resistance += log(end / start) / (2.0 * pi * conductivity)
            resistance += 1.0 / (outer_film * 2.0 * pi * outer)
            flow_per_length = (inner_bulk - outer_bulk) / resistance
            flux_inner = flow_per_length / (2.0 * pi * inner)
            # Report the resistance on an inner-area basis so it compares with U.
            return flux_inner, resistance * 2.0 * pi * inner

        resistance = 1.0 / inner_film
        node = 0
        for layer_index, layer in enumerate(self.layers):
            start = self.coordinates[node]
            node += layer.elements
            end = self.coordinates[node]
            members = [
                conductivities[i]
                for i, owner in enumerate(self.element_layers)
                if owner == layer_index
            ]
            conductivity = sum(members) / len(members) if members else 1.0
            resistance += (end - start) / conductivity
        resistance += 1.0 / outer_film
        return (inner_bulk - outer_bulk) / resistance, resistance


def analytic_composite_resistance(
    layers: Sequence[ConductionLayer],
    *,
    inner_radius_m: float,
    inner_film_coefficient_w_per_m2k: float,
    outer_film_coefficient_w_per_m2k: float,
    mean_temperature_c: float = 20.0,
) -> float:
    """Closed-form composite-cylinder resistance per unit length, in m.K/W.

    Independent of the finite-element assembly, so it is a genuine check rather
    than a restatement of the same code.
    """
    _require_positive("inner_radius_m", inner_radius_m)
    _require_positive("inner_film_coefficient_w_per_m2k", inner_film_coefficient_w_per_m2k)
    _require_positive("outer_film_coefficient_w_per_m2k", outer_film_coefficient_w_per_m2k)

    radius = float(inner_radius_m)
    resistance = 1.0 / (inner_film_coefficient_w_per_m2k * 2.0 * pi * radius)
    for layer in layers:
        outer = radius + layer.thickness_m
        resistance += log(outer / radius) / (
            2.0 * pi * layer.material.conductivity_at(mean_temperature_c)
        )
        radius = outer
    resistance += 1.0 / (outer_film_coefficient_w_per_m2k * 2.0 * pi * radius)
    return resistance


def _build_mesh(
    layers: Sequence[ConductionLayer], start: float
) -> tuple[list[float], list[int]]:
    """Node coordinates with every layer interface on a node, plus element ownership."""
    coordinates = [start]
    element_layers: list[int] = []
    position = start
    for layer_index, layer in enumerate(layers):
        step = layer.thickness_m / layer.elements
        for _ in range(layer.elements):
            position += step
            coordinates.append(position)
            element_layers.append(layer_index)
    return coordinates, element_layers


def _solve_tridiagonal(
    lower: Sequence[float],
    diagonal: Sequence[float],
    upper: Sequence[float],
    rhs: Sequence[float],
) -> list[float]:
    """Thomas algorithm for a tridiagonal system."""
    size = len(diagonal)
    c = [0.0] * size
    d = [0.0] * size

    pivot = diagonal[0]
    if abs(pivot) < 1.0e-30:
        raise ValueError("singular system: check that a film coefficient is non-zero")
    c[0] = upper[0] / pivot if size > 1 else 0.0
    d[0] = rhs[0] / pivot

    for index in range(1, size):
        pivot = diagonal[index] - lower[index - 1] * c[index - 1]
        if abs(pivot) < 1.0e-30:
            raise ValueError("singular system encountered during elimination")
        if index < size - 1:
            c[index] = upper[index] / pivot
        d[index] = (rhs[index] - lower[index - 1] * d[index - 1]) / pivot

    solution = [0.0] * size
    solution[-1] = d[-1]
    for index in range(size - 2, -1, -1):
        solution[index] = d[index] - c[index] * solution[index + 1]
    return solution


def _tridiagonal_multiply(
    lower: Sequence[float],
    diagonal: Sequence[float],
    upper: Sequence[float],
    vector: Sequence[float],
) -> list[float]:
    size = len(diagonal)
    result = [diagonal[index] * vector[index] for index in range(size)]
    for index in range(size - 1):
        result[index] += upper[index] * vector[index + 1]
        result[index + 1] += lower[index] * vector[index]
    return result


def _require_positive(name: str, value: float | None) -> None:
    if value is None or not isfinite(float(value)) or float(value) <= 0.0:
        raise ValueError(f"{name} must be a finite positive number")
