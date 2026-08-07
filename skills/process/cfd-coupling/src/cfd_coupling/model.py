from __future__ import annotations

import re
from dataclasses import dataclass
from importlib.util import find_spec
from math import isfinite, sqrt

# Blasius smooth-pipe friction gives wall shear proportional to velocity^1.75.
_SHEAR_VELOCITY_EXPONENT = 1.75

# Valid wall-function y+ band for standard log-law wall treatment.
_WALL_FUNCTION_MIN_YPLUS = 30.0
_WALL_FUNCTION_MAX_YPLUS = 300.0

# Resolved (low-Reynolds) wall treatment targets y+ of order one.
_RESOLVED_GOOD_YPLUS = 1.0
_RESOLVED_CAUTION_YPLUS = 5.0

# Models are classified by the tokens their names contain, with case and
# separators stripped, because the same family is written kOmegaSST,
# k-omega-sst and "k omega SST" by different codes and has many derivatives.
# Scale-resolving tokens are tested first: kOmegaSSTDES is a DES model, not RANS.
_SCALE_RESOLVING_TOKENS = ("les", "des", "sas", "sbes", "dns")
_RANS_TOKENS = (
    "kepsilon",
    "komega",
    "sst",
    "rsm",
    "reynoldsstress",
    "spalartallmaras",
    "v2f",
    "rng",
)


def _normalise_model(name: str) -> str:
    """Strip case, spaces and separators so model spellings compare equal."""
    return re.sub(r"[^0-9a-z]+", "", (name or "").lower())


def _classify_model(name: str) -> str:
    """Return 'scale_resolving', 'rans' or 'unknown' for a turbulence model name."""
    key = _normalise_model(name)
    if not key:
        return "unknown"
    if any(token in key for token in _SCALE_RESOLVING_TOKENS):
        return "scale_resolving"
    if any(token in key for token in _RANS_TOKENS):
        return "rans"
    return "unknown"


@dataclass(frozen=True)
class CfdEnhancementResult:
    """Local-to-bulk enhancement factors derived from a CFD study."""

    location: str
    velocity_enhancement: float
    shear_enhancement: float
    mass_transfer_enhancement: float
    shear_source: str
    assumptions: tuple[str, ...]


@dataclass(frozen=True)
class CfdQualityResult:
    """Verdict on whether a CFD study is fit to feed an engineering model."""

    verdict: str
    findings: tuple[str, ...]
    wall_treatment_ok: bool
    mesh_independence_ok: bool
    turbulence_model_class: str
    assumptions: tuple[str, ...]


@dataclass(frozen=True)
class CfdWallResolutionResult:
    """First-cell sizing needed to hit a target y+ in a CFD mesh."""

    reynolds: float
    friction_factor: float
    friction_velocity_ms: float
    first_cell_centroid_height_m: float
    first_cell_height_m: float
    target_y_plus: float
    assumptions: tuple[str, ...]


class CfdCouplingModel:
    """Bridges computational fluid dynamics results and one-dimensional engineering models.

    This skill does not perform CFD. It does three things that make an existing CFD study
    usable inside a NeqSim workflow:

    1. Converts CFD local-versus-bulk flow results into the enhancement factors that
       one-dimensional models need, replacing generic textbook multipliers with
       study-specific ones.
    2. Gates the CFD study on the quality checks that decide whether its numbers can be
       trusted at all - wall treatment, mesh independence and turbulence model class.
    3. Sizes the near-wall mesh needed to resolve a target y+, so NeqSim fluid properties
       can be turned into a defensible CFD setup.
    """

    def __init__(self, caution_enhancement: float = 5.0) -> None:
        self._require_positive("caution_enhancement", caution_enhancement)
        self.caution_enhancement = caution_enhancement

    def evaluate_local_enhancement(
        self,
        *,
        location: str,
        bulk_velocity: float,
        local_peak_velocity: float,
        bulk_wall_shear: float | None = None,
        local_peak_wall_shear: float | None = None,
    ) -> CfdEnhancementResult:
        """Convert CFD local peaks into enhancement factors for a one-dimensional model.

        Wall shear is preferred over velocity when the CFD study reports it, because
        near-wall mass transfer scales with the friction velocity rather than with the
        bulk velocity.
        """
        if not location or not location.strip():
            raise ValueError("location must be a non-empty label")
        self._require_positive("bulk_velocity", bulk_velocity)
        self._require_positive("local_peak_velocity", local_peak_velocity)

        velocity_enhancement = local_peak_velocity / bulk_velocity

        if bulk_wall_shear is not None or local_peak_wall_shear is not None:
            if bulk_wall_shear is None or local_peak_wall_shear is None:
                raise ValueError(
                    "supply both bulk_wall_shear and local_peak_wall_shear, or neither"
                )
            self._require_positive("bulk_wall_shear", bulk_wall_shear)
            self._require_positive("local_peak_wall_shear", local_peak_wall_shear)
            shear_enhancement = local_peak_wall_shear / bulk_wall_shear
            shear_source = "cfd_wall_shear"
        else:
            shear_enhancement = velocity_enhancement**_SHEAR_VELOCITY_EXPONENT
            shear_source = "estimated_from_velocity"

        # Near-wall mass transfer scales with the friction velocity, u* = sqrt(tau / rho).
        mass_transfer_enhancement = sqrt(shear_enhancement)

        assumptions = [
            "This skill does not run CFD; it converts results from an existing study.",
            "Mass-transfer enhancement is taken as the square root of the shear "
            "enhancement, because near-wall transfer scales with the friction velocity.",
        ]
        if shear_source == "estimated_from_velocity":
            assumptions.append(
                "Wall shear was not reported, so it was estimated from velocity using the "
                "Blasius exponent 1.75. Prefer a CFD-reported wall shear when available."
            )
        if velocity_enhancement > self.caution_enhancement:
            assumptions.append(
                f"Velocity enhancement {velocity_enhancement:.1f} is large; confirm the "
                "peak is a resolved flow feature and not a single-cell artefact."
            )

        return CfdEnhancementResult(
            location=location.strip(),
            velocity_enhancement=round(velocity_enhancement, 3),
            shear_enhancement=round(shear_enhancement, 3),
            mass_transfer_enhancement=round(mass_transfer_enhancement, 3),
            shear_source=shear_source,
            assumptions=tuple(assumptions),
        )

    def assess_quality(
        self,
        *,
        turbulence_model: str,
        wall_treatment: str,
        y_plus: float | None = None,
        mesh_levels: int = 1,
        gci_percent: float | None = None,
        steady_state: bool = True,
    ) -> CfdQualityResult:
        """Decide whether a CFD study is fit to feed an engineering model."""
        model_key = _normalise_model(turbulence_model)
        treatment_key = (wall_treatment or "").strip().lower()
        if treatment_key not in {"wall_function", "resolved"}:
            raise ValueError("wall_treatment must be 'wall_function' or 'resolved'")

        findings: list[str] = []

        model_class = _classify_model(turbulence_model)
        if model_class == "rans":
            findings.append(
                f"'{turbulence_model}' is a RANS model; peak local values in separated or "
                "strongly unsteady flow are typically under-predicted."
            )
        elif model_class == "unknown":
            findings.append(
                f"Turbulence model '{turbulence_model}' not recognised; classify it before "
                "relying on local peaks."
            )

        wall_ok = True
        if y_plus is None:
            wall_ok = False
            findings.append("y+ not reported, so the wall treatment cannot be verified.")
        else:
            self._require_positive("y_plus", y_plus)
            if treatment_key == "wall_function":
                if not _WALL_FUNCTION_MIN_YPLUS <= y_plus <= _WALL_FUNCTION_MAX_YPLUS:
                    wall_ok = False
                    findings.append(
                        f"y+ = {y_plus:g} is outside the wall-function band "
                        f"{_WALL_FUNCTION_MIN_YPLUS:g}-{_WALL_FUNCTION_MAX_YPLUS:g}; "
                        "near-wall shear and heat transfer are unreliable."
                    )
            elif y_plus > _RESOLVED_CAUTION_YPLUS:
                wall_ok = False
                findings.append(
                    f"y+ = {y_plus:g} is too coarse for a resolved wall treatment "
                    f"(target below {_RESOLVED_GOOD_YPLUS:g})."
                )
            elif y_plus > _RESOLVED_GOOD_YPLUS:
                findings.append(
                    f"y+ = {y_plus:g} exceeds the ideal resolved target of "
                    f"{_RESOLVED_GOOD_YPLUS:g}; treat near-wall gradients with caution."
                )

        mesh_ok = True
        if mesh_levels < 2:
            mesh_ok = False
            findings.append(
                "Only one mesh reported, so mesh independence has not been demonstrated. "
                "Differences in cell count between load cases are not a convergence study."
            )
        elif mesh_levels == 2:
            findings.append(
                "Two meshes allow a difference check but not a grid-convergence index; "
                "three levels are the usual requirement."
            )
        if gci_percent is not None:
            self._require_finite("gci_percent", gci_percent)
            if gci_percent > 10.0:
                mesh_ok = False
                findings.append(
                    f"Grid-convergence index {gci_percent:g} % exceeds 10 %; the solution "
                    "is not grid converged."
                )
            elif gci_percent > 5.0:
                findings.append(
                    f"Grid-convergence index {gci_percent:g} % is between 5 % and 10 %; "
                    "carry it as an uncertainty band on any derived factor."
                )

        if steady_state and model_class == "scale_resolving":
            findings.append(
                "A scale-resolving model reported as steady state is inconsistent; confirm "
                "whether the quoted results are time-averaged."
            )

        if not wall_ok and not mesh_ok:
            verdict = "not_usable"
        elif wall_ok and mesh_ok and model_class != "unknown":
            verdict = "usable"
        else:
            verdict = "usable_with_caution"

        return CfdQualityResult(
            verdict=verdict,
            findings=tuple(findings),
            wall_treatment_ok=wall_ok,
            mesh_independence_ok=mesh_ok,
            turbulence_model_class=model_class,
            assumptions=(
                "Screening quality gate for reusing a CFD study, not a CFD verification "
                "and validation review.",
                "A 'usable_with_caution' verdict means derived factors should carry an "
                "explicit uncertainty band in the receiving engineering model.",
                "Wall-function and resolved y+ bands follow standard practice and may be "
                "tightened by a project CFD specification.",
            ),
        )

    def plan_wall_resolution(
        self,
        *,
        density: float,
        viscosity: float,
        velocity: float,
        hydraulic_diameter: float,
        target_y_plus: float = 1.0,
    ) -> CfdWallResolutionResult:
        """Size the near-wall cell needed to reach a target y+.

        Fluid properties are normally taken from a NeqSim flash of the actual fluid rather
        than from tables, because composition changes both density and viscosity.
        """
        self._require_positive("density", density)
        self._require_positive("viscosity", viscosity)
        self._require_positive("velocity", velocity)
        self._require_positive("hydraulic_diameter", hydraulic_diameter)
        self._require_positive("target_y_plus", target_y_plus)

        reynolds = density * velocity * hydraulic_diameter / viscosity
        friction_factor = (
            64.0 / reynolds if reynolds < 2300.0 else 0.3164 / reynolds**0.25
        )
        friction_velocity = velocity * sqrt(friction_factor / 8.0)
        centroid_height = target_y_plus * viscosity / (density * friction_velocity)

        assumptions = [
            "Blasius smooth-pipe friction is used to estimate the friction velocity.",
            "The reported centroid height is the distance from the wall to the first cell "
            "centre; a cell-centred solver therefore needs roughly twice that cell height.",
            "Fluid properties should come from a NeqSim flash of the actual fluid at the "
            "local condition, not from generic tables.",
        ]
        if reynolds < 2300.0:
            assumptions.append(
                "Flow is laminar, so the turbulent y+ concept does not apply; the result is "
                "reported only for completeness."
            )

        return CfdWallResolutionResult(
            reynolds=round(reynolds, 1),
            friction_factor=round(friction_factor, 5),
            friction_velocity_ms=round(friction_velocity, 5),
            first_cell_centroid_height_m=centroid_height,
            first_cell_height_m=2.0 * centroid_height,
            target_y_plus=target_y_plus,
            assumptions=tuple(assumptions),
        )

    @staticmethod
    def neqsim_available() -> bool:
        """Report whether the optional NeqSim package is importable."""
        return find_spec("neqsim") is not None

    @staticmethod
    def _require_finite(name: str, value: float) -> None:
        if not isfinite(value):
            raise ValueError(f"{name} must be finite")

    @classmethod
    def _require_positive(cls, name: str, value: float) -> None:
        cls._require_finite(name, value)
        if value <= 0.0:
            raise ValueError(f"{name} must be positive")
