"""Registry of independent reference sources for benchmark validation.

A benchmark is only meaningful when the reference is *more* authoritative than
the model under test. Comparing an SRK density against another SRK density is a
consistency check, not a benchmark. This module makes that judgement explicit:
every source carries an authority tier, a stated uncertainty, and the range over
which it is valid, so a reference can be rejected before it is quoted.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

# Authority tiers, most authoritative first. A benchmark reference must rank
# strictly above the model basis it is used to test.
TIER_ORDER: Tuple[str, ...] = (
    "primary_standard",  # internationally adopted standard reference formulation
    "reference_eos",     # high-accuracy multiparameter EOS for a specific fluid
    "measured_data",     # peer-reviewed experimental data with stated uncertainty
    "published_case",    # textbook or standard worked example with published answer
    "correlation",       # engineering correlation of the same class as the model
)

_TIER_RANK: Dict[str, int] = {tier: rank for rank, tier in enumerate(TIER_ORDER)}


class UnknownSourceError(KeyError):
    """Raised when a reference source key is not in the registry."""


@dataclass(frozen=True)
class ApplicabilityRange:
    """Range over which a reference source is validated.

    An empty ``fluids`` tuple means the source is not fluid-specific. A ``None``
    bound means the source imposes no limit on that variable.
    """

    fluids: Tuple[str, ...] = ()
    temperature_K: Optional[Tuple[float, float]] = None
    pressure_Pa: Optional[Tuple[float, float]] = None

    def covers(
        self,
        fluid: Optional[str] = None,
        temperature_K: Optional[float] = None,
        pressure_Pa: Optional[float] = None,
    ) -> bool:
        """Return True when the requested state lies inside the validated range."""
        if fluid is not None and self.fluids:
            if fluid.strip().lower() not in {f.lower() for f in self.fluids}:
                return False
        if temperature_K is not None and self.temperature_K is not None:
            low, high = self.temperature_K
            if not low <= temperature_K <= high:
                return False
        if pressure_Pa is not None and self.pressure_Pa is not None:
            low, high = self.pressure_Pa
            if not low <= pressure_Pa <= high:
                return False
        return True


@dataclass(frozen=True)
class ReferenceSource:
    """An independent source a NeqSim result may be benchmarked against."""

    key: str
    name: str
    tier: str
    citation: str
    applicability: ApplicabilityRange = field(default_factory=ApplicabilityRange)
    uncertainty_pct: Dict[str, float] = field(default_factory=dict)

    @property
    def tier_rank(self) -> int:
        """Lower rank means higher authority."""
        return _TIER_RANK.get(self.tier, len(TIER_ORDER))

    def property_uncertainty_pct(self, property_name: str) -> Optional[float]:
        """Stated relative uncertainty for a property, or the source default."""
        if property_name in self.uncertainty_pct:
            return self.uncertainty_pct[property_name]
        return self.uncertainty_pct.get("default")

    def is_independent_of(self, model_tier: str) -> bool:
        """True when this source outranks the model basis it would be testing."""
        model_rank = _TIER_RANK.get(model_tier, len(TIER_ORDER))
        return self.tier_rank < model_rank

    def covers(
        self,
        fluid: Optional[str] = None,
        temperature_K: Optional[float] = None,
        pressure_Pa: Optional[float] = None,
    ) -> bool:
        """Delegate to the applicability range."""
        return self.applicability.covers(fluid, temperature_K, pressure_Pa)


_REGISTRY: Dict[str, ReferenceSource] = {}


def register_source(source: ReferenceSource) -> ReferenceSource:
    """Add or replace a source in the registry and return it."""
    _REGISTRY[source.key] = source
    return source


def get_source(key: str) -> ReferenceSource:
    """Look up a source by key."""
    try:
        return _REGISTRY[key]
    except KeyError:
        raise UnknownSourceError(
            "unknown reference source '{}' — known keys: {}".format(
                key, ", ".join(sorted(_REGISTRY))
            )
        )


def list_sources() -> List[ReferenceSource]:
    """All registered sources, most authoritative first."""
    return sorted(_REGISTRY.values(), key=lambda s: (s.tier_rank, s.key))


def sources_for(
    fluid: Optional[str] = None,
    temperature_K: Optional[float] = None,
    pressure_Pa: Optional[float] = None,
    model_tier: Optional[str] = None,
) -> List[ReferenceSource]:
    """Sources valid at a state, optionally filtered to those outranking a model."""
    found: Iterable[ReferenceSource] = (
        s for s in list_sources() if s.covers(fluid, temperature_K, pressure_Pa)
    )
    if model_tier is not None:
        found = (s for s in found if s.is_independent_of(model_tier))
    return list(found)


register_source(
    ReferenceSource(
        key="iapws95",
        name="IAPWS-95 formulation for ordinary water substance",
        tier="primary_standard",
        citation=(
            "Wagner, W., & Pruss, A. (2002). The IAPWS formulation 1995 for the "
            "thermodynamic properties of ordinary water substance for general and "
            "scientific use. J. Phys. Chem. Ref. Data, 31(2), 387-535."
        ),
        applicability=ApplicabilityRange(
            fluids=("water",),
            temperature_K=(251.2, 1273.0),
            pressure_Pa=(0.0, 1.0e9),
        ),
        uncertainty_pct={"default": 0.05, "density": 0.001, "temperature": 0.001},
    )
)

register_source(
    ReferenceSource(
        key="iapws_if97",
        name="IAPWS-IF97 industrial formulation for water and steam",
        tier="primary_standard",
        citation=(
            "IAPWS R7-97(2012). Revised Release on the IAPWS Industrial Formulation "
            "1997 for the Thermodynamic Properties of Water and Steam."
        ),
        applicability=ApplicabilityRange(
            fluids=("water",),
            temperature_K=(273.15, 1073.15),
            pressure_Pa=(0.0, 1.0e8),
        ),
        uncertainty_pct={"default": 0.1},
    )
)

register_source(
    ReferenceSource(
        key="span_wagner_co2",
        name="Span-Wagner reference equation of state for carbon dioxide",
        tier="reference_eos",
        citation=(
            "Span, R., & Wagner, W. (1996). A new equation of state for carbon dioxide "
            "covering the fluid region from the triple-point temperature to 1100 K at "
            "pressures up to 800 MPa. J. Phys. Chem. Ref. Data, 25(6), 1509-1596."
        ),
        applicability=ApplicabilityRange(
            fluids=("co2", "carbon dioxide"),
            temperature_K=(216.592, 1100.0),
            pressure_Pa=(0.0, 8.0e8),
        ),
        uncertainty_pct={"default": 0.1, "density": 0.05},
    )
)

register_source(
    ReferenceSource(
        key="setzmann_wagner_methane",
        name="Setzmann-Wagner reference equation of state for methane",
        tier="reference_eos",
        citation=(
            "Setzmann, U., & Wagner, W. (1991). A new equation of state and tables of "
            "thermodynamic properties for methane covering the range from the melting "
            "line to 625 K at pressures up to 100 MPa. J. Phys. Chem. Ref. Data, "
            "20(6), 1061-1155."
        ),
        applicability=ApplicabilityRange(
            fluids=("methane",),
            temperature_K=(90.694, 625.0),
            pressure_Pa=(0.0, 1.0e8),
        ),
        uncertainty_pct={"default": 0.1, "density": 0.03},
    )
)

register_source(
    ReferenceSource(
        key="span_nitrogen",
        name="Span et al. reference equation of state for nitrogen",
        tier="reference_eos",
        citation=(
            "Span, R., Lemmon, E. W., Jacobsen, R. T., Wagner, W., & Yokozeki, A. "
            "(2000). A reference equation of state for the thermodynamic properties of "
            "nitrogen. J. Phys. Chem. Ref. Data, 29(6), 1361-1433."
        ),
        applicability=ApplicabilityRange(
            fluids=("nitrogen",),
            temperature_K=(63.151, 1000.0),
            pressure_Pa=(0.0, 2.2e9),
        ),
        uncertainty_pct={"default": 0.1, "density": 0.02},
    )
)

register_source(
    ReferenceSource(
        key="bucker_wagner_ethane",
        name="Bucker-Wagner reference equation of state for ethane",
        tier="reference_eos",
        citation=(
            "Bucker, D., & Wagner, W. (2006). A reference equation of state for the "
            "thermodynamic properties of ethane for temperatures from the melting line "
            "to 675 K and pressures up to 900 MPa. J. Phys. Chem. Ref. Data, 35(1), "
            "205-266."
        ),
        applicability=ApplicabilityRange(
            fluids=("ethane",),
            temperature_K=(90.368, 675.0),
            pressure_Pa=(0.0, 9.0e8),
        ),
        uncertainty_pct={"default": 0.1, "density": 0.04},
    )
)

register_source(
    ReferenceSource(
        key="lemmon_propane",
        name="Lemmon et al. reference equation of state for propane",
        tier="reference_eos",
        citation=(
            "Lemmon, E. W., McLinden, M. O., & Wagner, W. (2009). Thermodynamic "
            "properties of propane. III. A reference equation of state for temperatures "
            "from the melting line to 650 K and pressures up to 1000 MPa. J. Chem. Eng. "
            "Data, 54(12), 3141-3180."
        ),
        applicability=ApplicabilityRange(
            fluids=("propane",),
            temperature_K=(85.525, 650.0),
            pressure_Pa=(0.0, 1.0e9),
        ),
        uncertainty_pct={"default": 0.1, "density": 0.05},
    )
)

register_source(
    ReferenceSource(
        key="gerg2008",
        name="GERG-2008 wide-range equation of state for natural gases and mixtures",
        tier="reference_eos",
        citation=(
            "Kunz, O., & Wagner, W. (2012). The GERG-2008 wide-range equation of state "
            "for natural gases and other mixtures: an expansion of GERG-2004. J. Chem. "
            "Eng. Data, 57(11), 3032-3091. Adopted as ISO 20765-2/-3."
        ),
        applicability=ApplicabilityRange(
            temperature_K=(90.0, 450.0),
            pressure_Pa=(0.0, 3.5e7),
        ),
        uncertainty_pct={"default": 0.5, "density": 0.1, "speed_of_sound": 0.1},
    )
)

register_source(
    ReferenceSource(
        key="coolprop_heos",
        name="CoolProp HEOS backend (Helmholtz reference equations of state)",
        tier="reference_eos",
        citation=(
            "Bell, I. H., Wronski, J., Quoilin, S., & Lemort, V. (2014). Pure and "
            "pseudo-pure fluid thermophysical property evaluation and the open-source "
            "thermophysical property library CoolProp. Ind. Eng. Chem. Res., 53(6), "
            "2498-2508."
        ),
        uncertainty_pct={"default": 0.2, "density": 0.05, "viscosity": 2.0},
    )
)

register_source(
    ReferenceSource(
        key="nist_webbook",
        name="NIST Chemistry WebBook / NIST Standard Reference Database 69",
        tier="primary_standard",
        citation=(
            "Linstrom, P. J., & Mallard, W. G. (Eds.). NIST Chemistry WebBook, NIST "
            "Standard Reference Database Number 69. National Institute of Standards "
            "and Technology, Gaithersburg MD."
        ),
        uncertainty_pct={"default": 0.5},
    )
)

register_source(
    ReferenceSource(
        key="experimental",
        name="Peer-reviewed experimental data with stated uncertainty",
        tier="measured_data",
        citation="Cite the specific paper, table, and stated uncertainty.",
        uncertainty_pct={"default": 1.0},
    )
)

register_source(
    ReferenceSource(
        key="published_worked_example",
        name="Textbook or standard worked example with a published answer",
        tier="published_case",
        citation="Cite the book/standard, edition, example number, and page.",
        uncertainty_pct={"default": 2.0},
    )
)
