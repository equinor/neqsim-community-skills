"""Fluid descriptions and molar blending for commingling screening.

A :class:`FluidSpec` holds a defined-component composition plus optional
pseudo-components (C7+ cuts). Blending is done on a molar basis: a blend with
``fraction_b = 0.3`` contains 30 mol % of fluid B and 70 mol % of fluid A.

Defined components with the same name are summed. Pseudo-components are kept
separate and prefixed with the fluid label, because a C10 cut from one
reservoir is not the same component as a C10 cut from another.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field


class FluidSpecError(ValueError):
    """Raised for an invalid fluid description."""


@dataclass(frozen=True)
class PseudoComponent:
    """A characterised plus-fraction cut.

    Attributes:
        name: Cut name, for example ``"C10"``.
        amount: Mole amount on the same basis as the defined components.
        molar_mass_kg_mol: Molar mass in kg/mol (for example 0.140).
        density_g_cm3: Standard-condition liquid density in g/cm3.
    """

    name: str
    amount: float
    molar_mass_kg_mol: float
    density_g_cm3: float

    def __post_init__(self) -> None:
        if not self.name:
            raise FluidSpecError("pseudo-component needs a name")
        if not math.isfinite(self.amount) or self.amount < 0:
            raise FluidSpecError(f"{self.name}: amount must be >= 0")
        if not 0.05 <= self.molar_mass_kg_mol <= 3.0:
            raise FluidSpecError(
                f"{self.name}: molar mass {self.molar_mass_kg_mol} kg/mol is outside "
                "0.05-3.0 kg/mol; give kg/mol, not g/mol"
            )
        if not 0.55 <= self.density_g_cm3 <= 1.3:
            raise FluidSpecError(
                f"{self.name}: density {self.density_g_cm3} g/cm3 is outside 0.55-1.3"
            )


@dataclass
class FluidSpec:
    """A reservoir or well-stream fluid.

    Attributes:
        label: Short identifier used to prefix pseudo-components, e.g. ``"host"``.
        components: Defined-component amounts keyed by NeqSim component name
            (``"methane"``, ``"CO2"``, ``"H2S"``, ``"water"`` ...). Any consistent
            molar basis (mol %, mole fraction, kmol/h) is accepted.
        pseudo_components: Optional plus-fraction cuts on the same basis.
        asphaltenic: True when this fluid carries the asphaltenes of concern.
    """

    label: str
    components: dict[str, float]
    pseudo_components: list[PseudoComponent] = field(default_factory=list)
    asphaltenic: bool = False

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{0,11}", self.label or ""):
            raise FluidSpecError(
                "label must be 1-12 alphanumeric characters starting with a letter"
            )
        for name, amount in self.components.items():
            if not math.isfinite(amount) or amount < 0:
                raise FluidSpecError(f"{self.label}: amount of {name} must be >= 0")
        if self.total() <= 0:
            raise FluidSpecError(f"{self.label}: fluid has no material")

    def total(self) -> float:
        """Total molar amount of defined plus pseudo components."""
        return sum(self.components.values()) + sum(
            p.amount for p in self.pseudo_components
        )

    def has_water(self) -> bool:
        """True when the fluid contains water."""
        return self.components.get("water", 0.0) > 0.0


@dataclass(frozen=True)
class BlendedPseudo:
    """A pseudo-component in a blend, with its unique NeqSim name."""

    name: str
    mole_fraction: float
    molar_mass_kg_mol: float
    density_g_cm3: float


@dataclass(frozen=True)
class Blend:
    """A normalised molar blend of two fluids."""

    fraction_b: float
    components: dict[str, float]
    pseudo_components: tuple[BlendedPseudo, ...]

    def has_water(self) -> bool:
        """True when the blend contains water."""
        return self.components.get("water", 0.0) > 0.0

    def without_water(self) -> Blend:
        """The same blend with water removed and renormalised."""
        dry = {k: v for k, v in self.components.items() if k != "water"}
        total = sum(dry.values()) + sum(p.mole_fraction for p in self.pseudo_components)
        if total <= 0:
            raise FluidSpecError("blend has no hydrocarbon material")
        return Blend(
            fraction_b=self.fraction_b,
            components={k: v / total for k, v in dry.items()},
            pseudo_components=tuple(
                BlendedPseudo(
                    p.name,
                    p.mole_fraction / total,
                    p.molar_mass_kg_mol,
                    p.density_g_cm3,
                )
                for p in self.pseudo_components
            ),
        )


def blend(fluid_a: FluidSpec, fluid_b: FluidSpec, fraction_b: float) -> Blend:
    """Blend two fluids on a molar basis.

    Args:
        fluid_a: First fluid (fraction ``1 - fraction_b``).
        fluid_b: Second fluid (fraction ``fraction_b``).
        fraction_b: Mole fraction of fluid B in the blend, 0-1.

    Returns:
        A normalised :class:`Blend`.
    """
    if not 0.0 <= fraction_b <= 1.0:
        raise FluidSpecError(f"fraction_b must be within 0-1, got {fraction_b}")
    if fluid_a.label == fluid_b.label:
        raise FluidSpecError("the two fluids need different labels")

    components: dict[str, float] = {}
    pseudos: list[BlendedPseudo] = []
    for fluid, weight in ((fluid_a, 1.0 - fraction_b), (fluid_b, fraction_b)):
        if weight <= 0.0:
            continue
        total = fluid.total()
        for name, amount in fluid.components.items():
            if amount > 0:
                components[name] = components.get(name, 0.0) + weight * amount / total
        for pseudo in fluid.pseudo_components:
            if pseudo.amount > 0:
                safe = re.sub(r"[^A-Za-z0-9]", "", pseudo.name) or "PC"
                pseudos.append(
                    BlendedPseudo(
                        name=f"{safe}{fluid.label}",
                        mole_fraction=weight * pseudo.amount / total,
                        molar_mass_kg_mol=pseudo.molar_mass_kg_mol,
                        density_g_cm3=pseudo.density_g_cm3,
                    )
                )
    names = [p.name for p in pseudos]
    if len(set(names)) != len(names):
        raise FluidSpecError(f"pseudo-component names collide in the blend: {names}")
    return Blend(fraction_b, components, tuple(pseudos))


def mole_fraction_from_rates(molar_rate_a: float, molar_rate_b: float) -> float:
    """Mole fraction of fluid B from the two molar rates (any consistent unit)."""
    if molar_rate_a < 0 or molar_rate_b < 0:
        raise FluidSpecError("molar rates must be >= 0")
    total = molar_rate_a + molar_rate_b
    if total <= 0:
        raise FluidSpecError("at least one molar rate must be positive")
    return molar_rate_b / total
