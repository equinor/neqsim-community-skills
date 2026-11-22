"""Inputs, flowline profiles and NeqSim chemistry for the corrosion profile.

* :class:`CorrosionFluid` - the well stream, with water and optional salinity.
* :class:`PipelineSpec` and :func:`neqsim_pipeline_profile` - a pressure,
  temperature and flow profile from the NeqSim Beggs and Brill pipeline model.
* :class:`ProfilePoint` - one profile station; supply your own list (for
  example exported from a transient simulator) instead of the NeqSim pipeline.
* :class:`NeqSimChemistry` - free water and gas CO2/H2S at a station from a
  NeqSim SRK-CPA flash, and in-situ pH from the NORSOK M-506 model in NeqSim
  ``NorsokM506CorrosionRate`` (CO2, bicarbonate, ionic strength).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Protocol

NAN = float("nan")
CHLORIDE_MOLAR_MASS_MG = 35453.0
GLYCOLS = ("MEG", "DEG", "TEG")


class CorrosionInputError(ValueError):
    """Raised for an invalid fluid, pipeline or profile."""


@dataclass(frozen=True)
class PseudoCut:
    """A C7+ cut: name, amount (same basis as components), kg/mol, g/cm3."""

    name: str
    amount: float
    molar_mass_kg_mol: float
    density_g_cm3: float

    def __post_init__(self) -> None:
        if not 0.05 <= self.molar_mass_kg_mol <= 3.0:
            raise CorrosionInputError(
                f"{self.name}: molar mass must be in kg/mol (0.05-3.0)"
            )
        if not 0.55 <= self.density_g_cm3 <= 1.3:
            raise CorrosionInputError(f"{self.name}: density must be 0.55-1.3 g/cm3")
        if self.amount < 0:
            raise CorrosionInputError(f"{self.name}: amount must be >= 0")


@dataclass
class CorrosionFluid:
    """Well-stream composition for corrosion assessment.

    Attributes:
        components: Amounts keyed by NeqSim component name on any consistent
            molar basis. Include ``"water"`` (and ``"CO2"``, ``"H2S"``).
        pseudo_components: Optional C7+ cuts.
        chloride_mg_l: Chloride in the produced water, mg/L. Sets the ionic
            strength for the pH model; 0 for condensed water.
        bicarbonate_mg_l: Bicarbonate in the produced water, mg/L. Buffers
            the pH upwards; 0 for condensed water.
        dense_phase_impurities_ppmv: For CO2-rich streams only: O2, SO2, NOx
            impurities in ppm(v), keys ``"O2"``, ``"SO2"``, ``"NOx"``.
    """

    components: dict[str, float]
    pseudo_components: list[PseudoCut] = field(default_factory=list)
    chloride_mg_l: float = 0.0
    bicarbonate_mg_l: float = 0.0
    dense_phase_impurities_ppmv: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if any(not math.isfinite(v) or v < 0 for v in self.components.values()):
            raise CorrosionInputError("component amounts must be finite and >= 0")
        if self.total() <= 0:
            raise CorrosionInputError("fluid has no material")
        if self.chloride_mg_l < 0 or self.chloride_mg_l > 250000:
            raise CorrosionInputError("chloride_mg_l must be 0-250000")
        if not 0 <= self.bicarbonate_mg_l <= 20000:
            raise CorrosionInputError("bicarbonate_mg_l must be 0-20000")
        if self.components.get("water", 0.0) <= 0.0:
            raise CorrosionInputError(
                "add water to the composition: CO2 corrosion needs water, and the "
                "flash decides where free water exists"
            )

    def total(self) -> float:
        """Total molar amount."""
        return sum(self.components.values()) + sum(
            p.amount for p in self.pseudo_components
        )

    def mole_fraction(self, name: str) -> float:
        """Mole fraction of a defined component in the whole stream."""
        return self.components.get(name, 0.0) / self.total()

    def dry_co2_fraction(self) -> float:
        """CO2 mole fraction on a water-free basis."""
        dry = self.total() - self.components.get("water", 0.0)
        return self.components.get("CO2", 0.0) / dry if dry > 0 else 0.0

    def is_co2_rich(self, threshold: float = 0.5) -> bool:
        """True for CCS / CO2-injection streams (dense-phase assessment)."""
        return self.dry_co2_fraction() >= threshold


@dataclass
class ProfilePoint:
    """One station along the flowline.

    Velocity, density and viscosity are mixture values used for wall shear
    stress. Give ``wall_shear_pa`` directly to bypass that calculation.
    """

    distance_m: float
    pressure_bara: float
    temperature_c: float
    mixture_velocity_m_s: float | None = None
    mixture_density_kg_m3: float | None = None
    mixture_viscosity_pa_s: float | None = None
    wall_shear_pa: float | None = None
    flow_regime: str | None = None

    def __post_init__(self) -> None:
        if not self.pressure_bara > 0:
            raise CorrosionInputError("pressure_bara must be > 0")
        if not -50 <= self.temperature_c <= 300:
            raise CorrosionInputError("temperature_c must be -50..300 C")


def wall_shear_stress_pa(
    velocity_m_s: float,
    density_kg_m3: float,
    viscosity_pa_s: float,
    diameter_m: float,
    roughness_m: float = 5e-5,
) -> float:
    """Wall shear stress from mixture flow, Pa.

    ``tau = f_D / 8 * rho * v^2`` with the Haaland friction factor (laminar
    ``64/Re`` below Re 2300). A homogeneous-mixture estimate; supply measured
    or simulator shear on the wetted wall when you have it.
    """
    if min(velocity_m_s, density_kg_m3, viscosity_pa_s, diameter_m) <= 0:
        return NAN
    reynolds = density_kg_m3 * velocity_m_s * diameter_m / viscosity_pa_s
    if reynolds < 2300:
        friction = 64.0 / reynolds
    else:
        friction = (
            -1.8 * math.log10(6.9 / reynolds + (roughness_m / diameter_m / 3.7) ** 1.11)
        ) ** -2
    return friction / 8.0 * density_kg_m3 * velocity_m_s**2


@dataclass
class PipelineSpec:
    """Flowline for the NeqSim Beggs and Brill profile.

    Attributes:
        length_m: Pipe length, m.
        inner_diameter_m: Inner diameter, m.
        mass_flow_kg_h: Total mass rate, kg/h.
        inlet_pressure_bara: Inlet pressure, bara.
        inlet_temperature_c: Inlet temperature, deg C.
        segments: Number of calculation increments (profile stations).
        elevation_change_m: Outlet minus inlet elevation, m.
        roughness_m: Wall roughness, m.
        ambient_temperature_c: Surroundings temperature; with
            ``overall_u_w_m2k`` gives a cooling line. Omit both for adiabatic.
        overall_u_w_m2k: Overall heat-transfer coefficient, W/m2K.
    """

    length_m: float
    inner_diameter_m: float
    mass_flow_kg_h: float
    inlet_pressure_bara: float
    inlet_temperature_c: float
    segments: int = 20
    elevation_change_m: float = 0.0
    roughness_m: float = 5e-5
    ambient_temperature_c: float | None = None
    overall_u_w_m2k: float | None = None

    def __post_init__(self) -> None:
        if min(self.length_m, self.inner_diameter_m, self.mass_flow_kg_h) <= 0:
            raise CorrosionInputError("length, diameter and mass flow must be > 0")
        if self.inlet_pressure_bara <= 1:
            raise CorrosionInputError("inlet_pressure_bara must be > 1")
        if not 2 <= self.segments <= 500:
            raise CorrosionInputError("segments must be 2-500")
        if (self.ambient_temperature_c is None) != (self.overall_u_w_m2k is None):
            raise CorrosionInputError(
                "give both ambient_temperature_c and overall_u_w_m2k, or neither"
            )


class NeqSimUnavailableError(RuntimeError):
    """Raised when the neqsim package cannot be imported."""


def _jneqsim():
    try:
        from neqsim import jneqsim
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise NeqSimUnavailableError(
            "neqsim is not installed: python -m pip install neqsim"
        ) from exc
    return jneqsim


def _add_fluid(system, fluid: CorrosionFluid, with_ions: bool = False) -> None:
    total = fluid.total()
    for name, amount in fluid.components.items():
        if amount > 0:
            system.addComponent(name, float(amount / total))
    for cut in fluid.pseudo_components:
        if cut.amount > 0:
            system.addTBPfraction(
                cut.name,
                float(cut.amount / total),
                float(cut.molar_mass_kg_mol),
                float(cut.density_g_cm3),
            )
    del with_ions  # salinity enters through the pH model, not the flash


def neqsim_pipeline_profile(
    fluid: CorrosionFluid, pipe: PipelineSpec
) -> list[ProfilePoint]:
    """Pressure, temperature and flow profile from NeqSim Beggs and Brill."""
    j = _jneqsim()
    system = j.thermo.system.SystemSrkCPAstatoil(
        273.15 + pipe.inlet_temperature_c, pipe.inlet_pressure_bara
    )
    _add_fluid(system, fluid, with_ions=False)
    system.setMixingRule(10)
    system.setMultiPhaseCheck(True)
    stream = j.process.equipment.stream.Stream("inlet", system)
    stream.setFlowRate(float(pipe.mass_flow_kg_h), "kg/hr")
    stream.setTemperature(float(pipe.inlet_temperature_c), "C")
    stream.setPressure(float(pipe.inlet_pressure_bara), "bara")
    line = j.process.equipment.pipeline.PipeBeggsAndBrills("flowline", stream)
    line.setLength(float(pipe.length_m))
    line.setDiameter(float(pipe.inner_diameter_m))
    line.setElevation(float(pipe.elevation_change_m))
    line.setPipeWallRoughness(float(pipe.roughness_m))
    line.setNumberOfIncrements(int(pipe.segments))
    if pipe.overall_u_w_m2k is not None:
        line.setRunIsothermal(False)
        line.setConstantSurfaceTemperature(float(pipe.ambient_temperature_c), "C")
        line.setHeatTransferCoefficient(float(pipe.overall_u_w_m2k))
    process = j.process.processmodel.ProcessSystem()
    process.add(stream)
    process.add(line)
    process.run()
    points = []
    for i in range(1, pipe.segments + 1):
        points.append(
            ProfilePoint(
                # getSegmentLength returns the distance from the inlet
                distance_m=float(line.getSegmentLength(i)),
                pressure_bara=float(line.getSegmentPressure(i)),
                temperature_c=float(line.getSegmentTemperature(i)) - 273.15,
                mixture_velocity_m_s=float(
                    line.getSegmentMixtureSuperficialVelocity(i)
                ),
                mixture_density_kg_m3=float(line.getSegmentMixtureDensity(i)),
                mixture_viscosity_pa_s=float(line.getSegmentMixtureViscosity(i)),
                flow_regime=str(line.getSegmentFlowRegime(i)),
            )
        )
    inlet = ProfilePoint(
        distance_m=0.0,
        pressure_bara=pipe.inlet_pressure_bara,
        temperature_c=pipe.inlet_temperature_c,
        mixture_velocity_m_s=points[0].mixture_velocity_m_s,
        mixture_density_kg_m3=points[0].mixture_density_kg_m3,
        mixture_viscosity_pa_s=points[0].mixture_viscosity_pa_s,
        flow_regime=points[0].flow_regime,
    )
    return [inlet, *points]


@dataclass
class PointChemistry:
    """Water and acid-gas state at one station."""

    free_water: bool
    in_situ_ph: float
    ph_source: str
    gas_co2_mole_fraction: float
    gas_h2s_mole_fraction: float
    co2_fugacity_eos_bar: float = NAN
    has_gas_phase: bool = True
    glycol_weight_fraction: float = 0.0
    water_vapour_mass_fraction: float = NAN
    notes: list[str] = field(default_factory=list)


class ChemistryModel(Protocol):
    """Anything that gives :class:`PointChemistry` at a station."""

    def evaluate(
        self, fluid: CorrosionFluid, pressure_bara: float, temperature_c: float
    ) -> PointChemistry: ...


class NeqSimChemistry:
    """Station chemistry from NeqSim.

    Free water and the gas composition come from an SRK-CPA (Statoil) flash;
    the aqueous phase is the liquid phase with more than 50 mol % water. The
    in-situ pH comes from the NORSOK M-506 model in NeqSim
    ``NorsokM506CorrosionRate#calculateEquilibriumPH`` (CO2, bicarbonate and
    ionic strength from chloride), or is fixed with ``ph=...``.

    Args:
        ph: ``"m506"`` (default) or a fixed pH value, e.g. a measured one.
    """

    def __init__(self, ph: str | float = "m506") -> None:
        if not (ph == "m506" or isinstance(ph, int | float) and 2.0 <= ph <= 9.0):
            raise CorrosionInputError("ph must be 'm506' or a value in 2-9")
        self._j = _jneqsim()
        self.ph = ph

    def _system(
        self, fluid: CorrosionFluid, pressure_bara: float, temperature_c: float
    ):
        system = self._j.thermo.system.SystemSrkCPAstatoil(
            273.15 + temperature_c, float(pressure_bara)
        )
        _add_fluid(system, fluid, with_ions=False)
        system.setMixingRule(10)
        system.setMultiPhaseCheck(True)
        return system

    def evaluate(
        self, fluid: CorrosionFluid, pressure_bara: float, temperature_c: float
    ) -> PointChemistry:
        """Free water, pH and gas CO2/H2S at one station."""
        system = self._system(fluid, pressure_bara, temperature_c)
        ops = self._j.thermodynamicoperations.ThermodynamicOperations(system)
        ops.TPflash()
        system.init(3)
        aqueous, gas, other = None, None, None
        for i in range(system.getNumberOfPhases()):
            phase = system.getPhase(i)
            kind = str(phase.getType()).lower()
            water = float(phase.getComponent("water").getx())
            if kind == "gas":
                gas = phase
            elif water > 0.5 and (aqueous is None or water > aqueous[1]):
                aqueous = (phase, water)
            elif other is None:
                other = phase
        carrier = gas if gas is not None else other
        notes: list[str] = []

        def fraction(phase, name: str) -> float:
            if phase is None or not phase.hasComponent(name):
                return 0.0
            return float(phase.getComponent(name).getx())

        y_co2 = fraction(carrier, "CO2")
        y_h2s = fraction(carrier, "H2S")
        eos_fugacity = NAN
        if carrier is not None and carrier.hasComponent("CO2"):
            comp = carrier.getComponent("CO2")
            eos_fugacity = float(comp.getFugacityCoefficient()) * y_co2 * pressure_bara
        if gas is None:
            notes.append("no gas phase: CO2 fugacity from the equation of state")
        free_water = aqueous is not None
        glycol = 0.0
        if free_water:
            phase = aqueous[0]
            total_mass = sum(
                float(phase.getComponent(i).getx())
                * float(phase.getComponent(i).getMolarMass())
                for i in range(phase.getNumberOfComponents())
            )
            glycol_mass = sum(
                float(phase.getComponent(name).getx())
                * float(phase.getComponent(name).getMolarMass())
                for name in GLYCOLS
                if phase.hasComponent(name)
            )
            glycol = glycol_mass / total_mass if total_mass > 0 else 0.0
        vapour = NAN
        if gas is not None:
            system_mass = float(system.getMolarMass()) * float(
                system.getTotalNumberOfMoles()
            )
            gas_mass = float(gas.getMolarMass()) * float(gas.getNumberOfMolesInPhase())
            water = gas.getComponent("water")
            water_in_gas = (
                float(water.getx())
                * float(water.getMolarMass())
                / float(gas.getMolarMass())
            )
            vapour = gas_mass / system_mass * water_in_gas if system_mass > 0 else NAN
        elif carrier is not None:
            vapour = 0.0
        ph = NAN
        source = ""
        if free_water:
            if self.ph == "m506":
                model = self._j.process.corrosion.NorsokM506CorrosionRate()
                model.setTemperatureCelsius(float(temperature_c))
                model.setTotalPressureBara(float(pressure_bara))
                partial = (
                    y_co2
                    if gas is not None
                    else eos_fugacity / max(pressure_bara, 1e-9)
                )
                model.setCO2MoleFraction(float(min(max(partial, 0.0), 1.0)))
                model.setBicarbonateConcentrationMgL(float(fluid.bicarbonate_mg_l))
                model.setIonicStrengthMolL(
                    float(fluid.chloride_mg_l / CHLORIDE_MOLAR_MASS_MG)
                )
                ph = float(model.calculateEquilibriumPH())
                source = "NORSOK M-506 pH model (NeqSim)"
            else:
                ph = float(self.ph)
                source = "user-supplied pH"
        return PointChemistry(
            free_water=free_water,
            in_situ_ph=ph,
            ph_source=source,
            gas_co2_mole_fraction=y_co2,
            gas_h2s_mole_fraction=y_h2s,
            co2_fugacity_eos_bar=eos_fugacity,
            has_gas_phase=gas is not None,
            glycol_weight_fraction=glycol,
            water_vapour_mass_fraction=vapour,
            notes=notes,
        )
