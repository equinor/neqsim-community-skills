"""Best-guess structural geometry when no seismic, log or contact data exists.

When a reservoir model is needed and the subsurface dataset is empty, the choice
is not between "build a model" and "do not build a model" — it is between an
implicit guess buried in a spreadsheet and an explicit, labelled one. This module
makes the guess explicit.

It supplies:

* a table of **structural styles** by play, each one the trap geometry that
  dominates that play, so the assumed structure is at least the most likely
  structure rather than an arbitrary box;
* a table of **reservoir stratigraphy** by play, because the vertical
  permeability contrast is what decides whether a horizontal drain drains the
  interval or only one layer of it;
* two **inversion solvers** that turn published numbers into geometry — a fluid
  contact solved to honour a reported volume, and a culmination height solved to
  honour a reported volume split — so the numbers that *can* be derived are
  derived rather than guessed;
* an **assumption register** that lists every geometric number with its
  provenance, so a reader can see in one table what was known and what was
  invented.

Nothing here is a substitute for an interpretation. The point is that the model
should say so itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence

from .parameters import Parameter

#: Structural style by play. Each entry is the trap geometry that dominates the
#: play, with the geometric parameters a screening grid needs.
#:
#: ``trap`` describes the closure; ``dip_deg`` is the regional dip of the
#: reservoir top; ``fault_throw_m`` is the offset needed for the bounding fault
#: to seal a normal reservoir thickness; ``relief_m`` is the vertical closure
#: from crest to spill; ``cell_size_m`` is a sensible screening cell.
STRUCTURAL_STYLE: Mapping[str, Mapping[str, object]] = {
    "tampen_brent": {
        "description": "Rotated Brent fault blocks, Tampen Spur, northern North Sea",
        "trap": "three-way dip closure sealed against a N-S normal fault",
        "dip_deg": 1.3,
        "fault_throw_m": 60.0,
        "fault_seal_multiplier": 0.02,
        "relief_m": 120.0,
        "cell_size_m": 100.0,
        "analogues": ("Gullfaks", "Visund", "Statfjord", "Snorre"),
    },
    "north_sea_horst": {
        "description": "Fault-bounded horst block, central and northern North Sea",
        "trap": "four-way closure bounded by faults on two sides",
        "dip_deg": 2.0,
        "fault_throw_m": 80.0,
        "fault_seal_multiplier": 0.05,
        "relief_m": 150.0,
        "cell_size_m": 100.0,
        "analogues": ("Oseberg", "Brage"),
    },
    "north_sea_salt_dome": {
        "description": "Drape closure over a salt structure, central North Sea",
        "trap": "four-way dip closure, radial dip off the crest",
        "dip_deg": 3.5,
        "fault_throw_m": 0.0,
        "fault_seal_multiplier": 1.0,
        "relief_m": 200.0,
        "cell_size_m": 100.0,
        "analogues": ("Ekofisk", "Valhall"),
    },
    "halten_terrace": {
        "description": "Rotated Jurassic fault blocks, Halten Terrace, Norwegian Sea",
        "trap": "three-way dip closure against a NE-SW fault",
        "dip_deg": 1.5,
        "fault_throw_m": 90.0,
        "fault_seal_multiplier": 0.02,
        "relief_m": 160.0,
        "cell_size_m": 125.0,
        "analogues": ("Aasgard", "Heidrun", "Kristin"),
    },
    "barents_platform": {
        "description": "Gently dipping platform closure, Barents Sea",
        "trap": "broad four-way closure, low relief, uplift-affected",
        "dip_deg": 0.6,
        "fault_throw_m": 40.0,
        "fault_seal_multiplier": 0.10,
        "relief_m": 70.0,
        "cell_size_m": 150.0,
        "analogues": ("Johan Castberg", "Wisting", "Goliat"),
    },
    "generic_anticline": {
        "description": "Generic four-way anticlinal closure, no play information",
        "trap": "four-way dip closure",
        "dip_deg": 2.0,
        "fault_throw_m": 0.0,
        "fault_seal_multiplier": 1.0,
        "relief_m": 120.0,
        "cell_size_m": 100.0,
        "analogues": (),
    },
}

#: Reservoir stratigraphy by play, as a layered sequence from top down.
#:
#: Each entry is ``(formation, thickness_fraction, porosity, net_to_gross,
#: permeability_mD, kv_over_kh)``. The fractions sum to one over the gross
#: interval. These are screening analogues, not mapped properties — but they
#: carry the property *contrast* that a single-layer tank model destroys.
STRATIGRAPHY: Mapping[str, Sequence[tuple[str, float, float, float, float, float]]] = {
    "tampen_brent": (
        ("Tarbert", 0.25, 0.225, 0.78, 260.0, 0.30),
        ("Ness", 0.375, 0.175, 0.34, 35.0, 0.05),
        ("Etive/Rannoch", 0.375, 0.190, 0.56, 120.0, 0.20),
    ),
    "north_sea_horst": (
        ("Tarbert", 0.30, 0.230, 0.80, 300.0, 0.30),
        ("Ness", 0.35, 0.180, 0.35, 40.0, 0.05),
        ("Etive/Rannoch", 0.35, 0.195, 0.60, 140.0, 0.20),
    ),
    "north_sea_salt_dome": (
        ("Tor", 0.40, 0.320, 0.85, 5.0, 0.40),
        ("Hod", 0.60, 0.280, 0.70, 1.0, 0.30),
    ),
    "halten_terrace": (
        ("Garn", 0.30, 0.240, 0.85, 400.0, 0.35),
        ("Not", 0.10, 0.140, 0.15, 5.0, 0.02),
        ("Ile", 0.35, 0.220, 0.70, 250.0, 0.25),
        ("Tofte/Tilje", 0.25, 0.190, 0.60, 120.0, 0.20),
    ),
    "barents_platform": (
        ("Stoe", 0.45, 0.220, 0.75, 400.0, 0.30),
        ("Nordmela", 0.30, 0.180, 0.45, 60.0, 0.08),
        ("Tubaen", 0.25, 0.200, 0.65, 200.0, 0.20),
    ),
    "generic_anticline": (
        ("Upper reservoir", 0.35, 0.220, 0.75, 200.0, 0.25),
        ("Middle barrier", 0.30, 0.170, 0.35, 30.0, 0.05),
        ("Lower reservoir", 0.35, 0.200, 0.60, 120.0, 0.20),
    ),
}

#: Which sea area maps onto which structural style when no play is given.
SEA_AREA_DEFAULT_PLAY: Mapping[str, str] = {
    "north_sea": "tampen_brent",
    "norwegian_sea": "halten_terrace",
    "barents_sea": "barents_platform",
    "generic": "generic_anticline",
}


@dataclass(frozen=True)
class StructuralAssumption:
    """One assumed geometric element with the reason it was assumed."""

    element: str
    value: str
    provenance: str
    rationale: str
    would_be_replaced_by: str

    def to_dict(self) -> dict:
        return {
            "element": self.element,
            "value": self.value,
            "provenance": self.provenance,
            "rationale": self.rationale,
            "would_be_replaced_by": self.would_be_replaced_by,
        }


@dataclass(frozen=True)
class StructuralModel:
    """A best-guess structural description plus its assumption register."""

    play: str
    style: Mapping[str, object]
    formations: Sequence[tuple[str, float, float, float, float, float]]
    parameters: Mapping[str, Parameter]
    assumptions: Sequence[StructuralAssumption] = field(default_factory=tuple)

    @property
    def is_faulted(self) -> bool:
        """True when the assumed trap needs a bounding fault."""
        return float(self.style["fault_throw_m"]) > 0.0

    def to_dict(self) -> dict:
        return {
            "play": self.play,
            "interpretation": (
                "ASSUMED structural style - {} - no seismic data was used".format(
                    self.style["description"]
                )
            ),
            "style": dict(self.style),
            "formations": [
                {
                    "name": name,
                    "thickness_fraction": fraction,
                    "porosity": poro,
                    "net_to_gross": ntg,
                    "permeability_mD": perm,
                    "kv_over_kh": kvkh,
                }
                for name, fraction, poro, ntg, perm, kvkh in self.formations
            ],
            "parameters": {
                key: value.to_dict() for key, value in self.parameters.items()
            },
            "assumptions": [item.to_dict() for item in self.assumptions],
        }


def resolve_play(play: str | None = None, sea_area: str | None = None) -> str:
    """Pick a structural style from an explicit play or a sea area."""
    if play and play in STRUCTURAL_STYLE:
        return play
    if play:
        raise KeyError(
            "unknown play '{}'; expected one of {}".format(
                play, sorted(STRUCTURAL_STYLE)
            )
        )
    key = (sea_area or "generic").strip().lower().replace(" ", "_")
    return SEA_AREA_DEFAULT_PLAY.get(key, "generic_anticline")


def assume_structure(
    play: str | None = None,
    sea_area: str | None = None,
    gross_thickness_m: float | None = None,
) -> StructuralModel:
    """Return a best-guess structural model with every assumption labelled.

    Parameters
    ----------
    play:
        Explicit key into :data:`STRUCTURAL_STYLE`. Overrides ``sea_area``.
    sea_area:
        ``north_sea``, ``norwegian_sea``, ``barents_sea`` or ``generic``; used
        only when ``play`` is not given.
    gross_thickness_m:
        Reservoir gross thickness. Used to check that the assumed fault throw is
        actually large enough to seal, and to flag it when it is not.
    """
    key = resolve_play(play, sea_area)
    style = STRUCTURAL_STYLE[key]
    formations = STRATIGRAPHY[key]
    analogues = ", ".join(style["analogues"]) or "no named analogue"

    parameters = {
        "regional_dip_deg": Parameter(
            name="regional_dip_deg",
            value=float(style["dip_deg"]),
            unit="deg",
            provenance="analogue",
            reference="{} structural style".format(key),
            low=0.5 * float(style["dip_deg"]),
            high=2.0 * float(style["dip_deg"]),
        ),
        "structural_relief_m": Parameter(
            name="structural_relief_m",
            value=float(style["relief_m"]),
            unit="m",
            provenance="analogue",
            reference="{} structural style".format(key),
            low=0.5 * float(style["relief_m"]),
            high=1.8 * float(style["relief_m"]),
        ),
        "cell_size_m": Parameter(
            name="cell_size_m",
            value=float(style["cell_size_m"]),
            unit="m",
            provenance="default",
            reference="screening resolution",
        ),
    }
    if float(style["fault_throw_m"]) > 0.0:
        parameters["fault_throw_m"] = Parameter(
            name="fault_throw_m",
            value=float(style["fault_throw_m"]),
            unit="m",
            provenance="analogue",
            reference="{} structural style".format(key),
            low=0.5 * float(style["fault_throw_m"]),
            high=2.0 * float(style["fault_throw_m"]),
        )
        parameters["fault_seal_multiplier"] = Parameter(
            name="fault_seal_multiplier",
            value=float(style["fault_seal_multiplier"]),
            unit="-",
            provenance="default",
            reference="sealing fault assumed; no fault-seal analysis performed",
        )

    assumptions = [
        StructuralAssumption(
            element="Structural style",
            value=str(style["description"]),
            provenance="analogue",
            rationale=(
                "Dominant trap style of the play. Analogues: {}.".format(analogues)
            ),
            would_be_replaced_by="3D seismic interpretation and a depth structure map",
        ),
        StructuralAssumption(
            element="Trap geometry",
            value=str(style["trap"]),
            provenance="analogue",
            rationale="Follows from the structural style.",
            would_be_replaced_by="mapped closure outline and spill point",
        ),
        StructuralAssumption(
            element="Regional dip",
            value="{:.1f} deg".format(float(style["dip_deg"])),
            provenance="analogue",
            rationale=(
                "Typical for the play; steep enough to close, gentle enough that "
                "the closure stays inside a screening-sized grid."
            ),
            would_be_replaced_by="depth structure map on the reservoir top",
        ),
        StructuralAssumption(
            element="Stratigraphy",
            value=" / ".join(name for name, *_ in formations),
            provenance="analogue",
            rationale=(
                "Reservoir interval of the play. Carries the vertical "
                "permeability contrast that controls drain performance."
            ),
            would_be_replaced_by="well logs with formation tops and core data",
        ),
        StructuralAssumption(
            element="Property distribution",
            value="per-formation porosity, net-to-gross and permeability",
            provenance="analogue",
            rationale=(
                "Screening analogue values; better rock is placed at the crest, "
                "which is the usual observation on structural closures."
            ),
            would_be_replaced_by="log-derived properties and a geostatistical model",
        ),
    ]
    if float(style["fault_throw_m"]) > 0.0:
        assumptions.append(
            StructuralAssumption(
                element="Bounding fault",
                value="{:.0f} m throw, transmissibility multiplier {:g}".format(
                    float(style["fault_throw_m"]),
                    float(style["fault_seal_multiplier"]),
                ),
                provenance="analogue",
                rationale=(
                    "Throw must exceed the reservoir thickness for the fault to "
                    "seal and hold a separate column."
                ),
                would_be_replaced_by=(
                    "fault mapping plus a juxtaposition / shale-gouge analysis"
                ),
            )
        )
        if gross_thickness_m and float(style["fault_throw_m"]) < gross_thickness_m:
            assumptions.append(
                StructuralAssumption(
                    element="Fault seal check",
                    value="THROW BELOW RESERVOIR THICKNESS",
                    provenance="derived",
                    rationale=(
                        "Assumed throw of {:.0f} m is less than the {:.0f} m gross "
                        "interval, so the reservoir is self-juxtaposed and the "
                        "fault cannot be assumed to seal. Either raise the throw "
                        "or model the compartments as connected.".format(
                            float(style["fault_throw_m"]), gross_thickness_m
                        )
                    ),
                    would_be_replaced_by="juxtaposition analysis",
                )
            )
    return StructuralModel(
        play=key,
        style=style,
        formations=formations,
        parameters=parameters,
        assumptions=tuple(assumptions),
    )


def solve_contact_for_volume(
    volume_above: Callable[[float], float],
    target_volume: float,
    shallow_m: float,
    deep_m: float,
    iterations: int = 60,
) -> float:
    """Bisect a fluid contact depth so the volume above it hits ``target_volume``.

    This is the inversion that turns a *published recoverable volume* into a
    *contact depth*: instead of guessing where the water sits, guess the
    structure and let the published volume place the contact.

    Parameters
    ----------
    volume_above:
        Callable returning the hydrocarbon volume above a trial contact depth.
        Must be monotonically increasing with depth.
    target_volume:
        Volume the closure must contain, in the same unit the callable returns.
    shallow_m, deep_m:
        Bracketing depths. ``shallow_m`` must give less than ``target_volume``
        and ``deep_m`` more.
    iterations:
        Bisection steps; 60 is ample for metre-level convergence.

    Returns
    -------
    float
        Contact depth in metres.

    Raises
    ------
    ValueError
        If the bracket does not contain the target, which means the assumed
        structure simply cannot hold the reported volume — a real result worth
        reporting rather than an error to suppress.
    """
    if shallow_m >= deep_m:
        raise ValueError("shallow_m must be above deep_m")
    low_volume = volume_above(shallow_m)
    high_volume = volume_above(deep_m)
    if not (low_volume <= target_volume <= high_volume):
        raise ValueError(
            "assumed structure cannot hold the target volume: bracket gives "
            "{:.4g} to {:.4g}, target is {:.4g}. Increase the relief, the area "
            "or the porosity, or question the reported volume.".format(
                low_volume, high_volume, target_volume
            )
        )
    for _ in range(iterations):
        middle = 0.5 * (shallow_m + deep_m)
        if volume_above(middle) < target_volume:
            shallow_m = middle
        else:
            deep_m = middle
    return 0.5 * (shallow_m + deep_m)


def solve_amplitude_for_split(
    split_for_amplitude: Callable[[float], float],
    target_fraction: float,
    low_m: float,
    high_m: float,
    iterations: int = 24,
) -> float:
    """Bisect a culmination height so a compartment carries ``target_fraction``.

    Used when a field has two accumulations whose *relative* size is public but
    whose geometry is not. Guess the structural style, then solve the height of
    the secondary culmination until the volume split matches the published one.

    ``split_for_amplitude`` must re-solve the fluid contact internally, because
    growing a culmination adds pore volume and therefore moves the contact.
    Forgetting that is the most common way this loop silently fails to converge.

    Parameters
    ----------
    split_for_amplitude:
        Callable returning the secondary compartment's volume fraction for a
        trial amplitude. Must increase with amplitude.
    target_fraction:
        Published volume fraction of the secondary compartment, 0 to 1.
    low_m, high_m:
        Bracketing amplitudes in metres.
    iterations:
        Bisection steps. Each one runs a full contact solve, so keep it modest.

    Returns
    -------
    float
        Culmination amplitude in metres. If the bracket does not span the
        target, the nearest bracket end is returned and the caller should treat
        the split as unattainable under the assumed structure.
    """
    if low_m >= high_m:
        raise ValueError("low_m must be less than high_m")
    if split_for_amplitude(high_m) < target_fraction:
        return high_m
    if split_for_amplitude(low_m) > target_fraction:
        return low_m
    for _ in range(iterations):
        middle = 0.5 * (low_m + high_m)
        if split_for_amplitude(middle) < target_fraction:
            low_m = middle
        else:
            high_m = middle
    return 0.5 * (low_m + high_m)


def longest_run_above_contact(depths_m: Sequence[float], contact_m: float) -> tuple:
    """Longest contiguous stretch of a well track that sits above the contact.

    A nominal well position taken from a tank model is meaningless once there is
    a structure: the drain may sit partly or wholly in the water leg. Rather
    than move drains by hand, place each one on the longest continuous run of
    cells above the contact and centre it there.

    Parameters
    ----------
    depths_m:
        Reservoir depth at each step along the planned track.
    contact_m:
        Fluid contact depth.

    Returns
    -------
    tuple
        ``(start_index, length)`` of the longest run, or ``(0, 0)`` when no part
        of the track is above the contact — meaning the well should be moved or
        dropped, which is itself a result.
    """
    best_start, best_length = 0, 0
    run_start, run_length = 0, 0
    for index, depth in enumerate(depths_m):
        if depth < contact_m:
            if run_length == 0:
                run_start = index
            run_length += 1
            if run_length > best_length:
                best_start, best_length = run_start, run_length
        else:
            run_length = 0
    return best_start, best_length


def assumption_register(model: StructuralModel) -> list[dict]:
    """Flatten a structural model into a reportable assumption table."""
    rows = [item.to_dict() for item in model.assumptions]
    for name, parameter in sorted(model.parameters.items()):
        rows.append(
            {
                "element": name,
                "value": "{:g} {}".format(parameter.value, parameter.unit).strip(),
                "provenance": parameter.provenance,
                "rationale": parameter.reference,
                "would_be_replaced_by": "field measurement",
            }
        )
    return rows
