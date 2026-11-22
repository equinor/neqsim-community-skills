"""Calibrated equation-of-state asphaltene onset for blends (solid model).

Precipitated asphaltene is a pure solid whose fugacity depends only on
temperature and pressure. It is anchored at a measured onset of the
asphaltenic fluid (Nghiem and Coombe, 1997)::

    ln f_s(T, P) = ln f_L(T*, P*) + v_s (P - P*) / (R T) - (h_s / R)(1/T - 1/T*)

``f_L`` is the asphaltene fugacity in the equilibrated fluid without solid.
Asphaltene precipitates where ``f_L > f_s``. Because ``f_s`` does not depend
on the fluid, one calibration on the host oil predicts the onset of every
blend with another fluid. The asphaltene interaction parameters follow a
size-asymmetry correlation on the co-volume (``b ~ Tc/Pc``)::

    k_ij = 1 - [2 (b_i b_j)^(1/6) / (b_i^(1/3) + b_j^(1/3))]^e

so light components (N2, CO2, C1) get large values and heavy fractions about 0.

The Java class ``neqsim.pvtsimulation.flowassurance.AsphalteneSolidModel`` is
used when the installed NeqSim has it; otherwise a Python implementation of the
same equations runs on the same NeqSim flashes (``backend`` tells which).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .evaluator import add_pseudo_components
from .fluids import Blend, FluidSpec, FluidSpecError, as_blend

R = 8.314462618
DEFAULT_SOLID_DENSITY = 1150.0  # kg/m3
PRESSURE_TOLERANCE = 0.05  # bar


@dataclass(frozen=True)
class MeasuredOnset:
    """Measured asphaltene onset of the asphaltenic fluid.

    Attributes:
        temperature_c: Test temperature, deg C.
        pressure_bara: Upper onset pressure (above the bubble point), bara.
        lower_pressure_bara: Optional lower onset (below the bubble point),
            bara. Fits the solid molar volume.
    """

    temperature_c: float
    pressure_bara: float
    lower_pressure_bara: float | None = None

    def __post_init__(self) -> None:
        if not -20.0 <= self.temperature_c <= 250.0:
            raise ValueError("onset temperature must be within -20..250 C")
        if not self.pressure_bara > 0:
            raise ValueError("onset pressure must be > 0")
        if self.lower_pressure_bara is not None and not (
            0 < self.lower_pressure_bara < self.pressure_bara
        ):
            raise ValueError("lower onset must be > 0 and below the upper onset")


@dataclass(frozen=True)
class OnsetResult:
    """Onset search result for one fluid or blend."""

    upper_bara: float
    lower_bara: float
    unstable_at_max: bool


def size_asymmetry_kij(asph_tc_pc: float, comp_tc_pc: float, exponent: float) -> float:
    """Asphaltene-component interaction parameter from co-volume asymmetry."""
    if asph_tc_pc <= 0 or comp_tc_pc <= 0:
        return 0.0
    a, c = asph_tc_pc ** (1 / 3), comp_tc_pc ** (1 / 3)
    return 1.0 - (2.0 * math.sqrt(a * c) / (a + c)) ** exponent


def _asphaltene_pseudo(fluid: FluidSpec):
    found = [p for p in fluid.pseudo_components if "asphalten" in p.name.lower()]
    if len(found) != 1:
        raise FluidSpecError(
            f"{fluid.label}: the asphaltenic fluid needs exactly one pseudo-component named "
            f"'Asphaltene...' (found {len(found)})"
        )
    if not found[0].has_critical_properties:
        raise FluidSpecError(
            f"{fluid.label}: give the asphaltene pseudo-component its critical temperature, "
            "pressure and acentric factor (for example 1015 K, 15.7 bar, 1.5)"
        )
    return found[0]


class CalibratedAsphalteneModel:
    """Asphaltene solid model calibrated to a measured onset of one fluid.

    Args:
        fluid: The asphaltenic fluid with one asphaltene pseudo-component that
            has critical properties. Water is ignored.
        onset: Measured onset of that fluid.
        kij_exponent: Size-asymmetry exponent (1.0 default; larger values give
            a stronger light-component effect).
        eos: ``"srk"`` or ``"pr"``.
        backend: ``"auto"`` (Java if available), ``"java"`` or ``"python"``.
    """

    def __init__(
        self,
        fluid: FluidSpec,
        onset: MeasuredOnset,
        kij_exponent: float = 1.0,
        eos: str = "srk",
        backend: str = "auto",
    ) -> None:
        if eos not in ("srk", "pr"):
            raise ValueError("eos must be 'srk' or 'pr'")
        if backend not in ("auto", "java", "python"):
            raise ValueError("backend must be 'auto', 'java' or 'python'")
        if not kij_exponent > 0:
            raise ValueError("kij_exponent must be > 0")
        try:
            from neqsim import jneqsim
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "neqsim is not installed: python -m pip install neqsim"
            ) from exc
        self._j = jneqsim
        self.eos = eos
        self.measured = onset
        self.fluid_label = fluid.label
        pseudo = _asphaltene_pseudo(fluid)
        self.solid_molar_volume = pseudo.molar_mass_kg_mol / (
            pseudo.density_g_cm3 * 1000.0
            if 0.9 <= pseudo.density_g_cm3 <= 1.4
            else DEFAULT_SOLID_DENSITY
        )
        self.kij_exponent = float(kij_exponent)
        self._reference = as_blend(fluid).without_water()
        java_class = self._java_class() if backend != "python" else None
        if backend == "java" and java_class is None:
            raise RuntimeError(
                "the installed NeqSim has no AsphalteneSolidModel (needs a newer NeqSim)"
            )
        self.backend = "java" if java_class is not None else "python"
        t_k = 273.15 + onset.temperature_c
        if self.backend == "java":
            self._model = java_class(
                self.system(self._reference, onset.temperature_c, 100.0)
            )
            self._model.setKijExponent(self.kij_exponent)
            self._model.calibrate(t_k, float(onset.pressure_bara))
            if onset.lower_pressure_bara is not None:
                self._model.calibrateLowerOnset(float(onset.lower_pressure_bara))
                self.solid_molar_volume = float(self._model.getSolidMolarVolume())
        else:
            self._ln_ref = self.ln_fugacity(self._reference, t_k, onset.pressure_bara)
            if onset.lower_pressure_bara is not None:
                ln_low = self.ln_fugacity(
                    self._reference, t_k, onset.lower_pressure_bara
                )
                volume = (
                    (ln_low - self._ln_ref)
                    * R
                    * t_k
                    / ((onset.lower_pressure_bara - onset.pressure_bara) * 1e5)
                )
                if not volume > 0:
                    raise ValueError(
                        "the lower onset gives a non-positive solid molar volume; the fluid "
                        "model cannot reproduce both onsets"
                    )
                self.solid_molar_volume = volume

    def _java_class(self):
        try:
            return self._j.pvtsimulation.flowassurance.AsphalteneSolidModel
        except AttributeError:
            return None

    # -- fluid --------------------------------------------------------------
    def system(self, blend: Blend, temperature_c: float, pressure_bara: float):
        """NeqSim system for a (water-free) blend."""
        thermo = self._j.thermo.system
        cls = thermo.SystemSrkEos if self.eos == "srk" else thermo.SystemPrEos
        system = cls(273.15 + temperature_c, float(pressure_bara))
        for name, x in blend.components.items():
            if name != "water" and x > 0:
                system.addComponent(name, float(x))
        add_pseudo_components(system, blend)
        system.setMixingRule("classic")
        return system

    def _apply_kij(self, system) -> None:
        phase0 = system.getPhase(0)
        n = phase0.getNumberOfComponents()
        names = [str(phase0.getComponent(i).getComponentName()) for i in range(n)]
        asph = [i for i, name in enumerate(names) if "asphalten" in name.lower()]
        if len(asph) != 1:
            raise FluidSpecError("each blend needs exactly one asphaltene component")
        a = asph[0]
        size_a = phase0.getComponent(a).getTC() / phase0.getComponent(a).getPC()
        kij = [
            size_asymmetry_kij(
                size_a,
                phase0.getComponent(k).getTC() / phase0.getComponent(k).getPC(),
                self.kij_exponent,
            )
            for k in range(n)
        ]
        for p in range(system.getMaxNumberOfPhases()):
            rule = system.getPhase(p).getEosMixingRule()
            for k in range(n):
                if k != a and names[k] != "water":
                    rule.setBinaryInteractionParameter(a, k, kij[k])
                    rule.setBinaryInteractionParameter(k, a, kij[k])

    def ln_fugacity(
        self, blend: Blend, temperature_k: float, pressure_bara: float
    ) -> float:
        """ln of the asphaltene fugacity (bar) in the blend without solid (Python path)."""
        system = self.system(blend, temperature_k - 273.15, pressure_bara)
        self._apply_kij(system)
        self._j.thermodynamicoperations.ThermodynamicOperations(system).TPflash()
        system.init(1)
        best_x, ln_f = -1.0, math.nan
        for p in range(system.getNumberOfPhases()):
            phase = system.getPhase(p)
            for i in range(phase.getNumberOfComponents()):
                comp = phase.getComponent(i)
                if "asphalten" not in str(comp.getComponentName()).lower():
                    continue
                x, phi = float(comp.getx()), float(comp.getFugacityCoefficient())
                if x > best_x and x > 0 and 0 < phi < math.inf:
                    best_x = x
                    ln_f = math.log(x) + math.log(phi) + math.log(pressure_bara)
        if not math.isfinite(ln_f):
            raise RuntimeError(f"no finite asphaltene fugacity at {pressure_bara} bara")
        return ln_f

    # -- results ------------------------------------------------------------
    def _ln_solid(self, temperature_k: float, pressure_bara: float) -> float:
        return self._ln_ref + self.solid_molar_volume * (
            pressure_bara - self.measured.pressure_bara
        ) * 1e5 / (R * temperature_k)

    def supersaturation(
        self, blend: Blend, temperature_c: float, pressure_bara: float
    ) -> float:
        """ln(f_L / f_s) of the asphaltene; positive means it precipitates."""
        t_k = 273.15 + temperature_c
        if self.backend == "java":
            return float(
                self._model.supersaturation(
                    self.system(blend.without_water(), temperature_c, pressure_bara),
                    t_k,
                    float(pressure_bara),
                )
            )
        return self.ln_fugacity(
            blend.without_water(), t_k, pressure_bara
        ) - self._ln_solid(t_k, pressure_bara)

    def onset(
        self,
        blend: Blend,
        temperature_c: float | None = None,
        max_pressure_bara: float = 600.0,
        min_pressure_bara: float = 10.0,
        step_bar: float = 5.0,
    ) -> OnsetResult:
        """Upper and lower onset pressures of a blend (default: calibration temperature)."""
        t_c = self.measured.temperature_c if temperature_c is None else temperature_c
        if not max_pressure_bara > min_pressure_bara > 0 or not step_bar > 0:
            raise ValueError("need max > min > 0 and step > 0")
        dry = blend.without_water()
        if self.backend == "java":
            r = self._model.onsetPressures(
                self.system(dry, t_c, max_pressure_bara),
                273.15 + t_c,
                float(max_pressure_bara),
                float(min_pressure_bara),
                float(step_bar),
            )
            return OnsetResult(
                float(r.getUpperOnsetPressure()),
                float(r.getLowerOnsetPressure()),
                bool(r.isUnstableAtMaximumPressure()),
            )

        def sigma(p: float) -> float:
            return self.supersaturation(dry, t_c, p)

        def bisect(low: float, high: float) -> float:
            low_positive = sigma(low) > 0
            for _ in range(60):
                if high - low <= PRESSURE_TOLERANCE:
                    break
                mid = 0.5 * (low + high)
                if (sigma(mid) > 0) == low_positive:
                    low = mid
                else:
                    high = mid
            return 0.5 * (low + high)

        prev_p = max_pressure_bara
        prev = sigma(prev_p)
        unstable = prev > 0
        upper = lower = math.nan
        while prev_p > min_pressure_bara:
            p = max(min_pressure_bara, prev_p - step_bar)
            value = sigma(p)
            if prev <= 0 < value and math.isnan(upper):
                upper = bisect(p, prev_p)
            elif prev > 0 >= value and (not math.isnan(upper) or unstable):
                lower = bisect(p, prev_p)
                break
            prev, prev_p = value, p
        return OnsetResult(upper, lower, unstable)
