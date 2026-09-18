"""Build a screening-level reservoir model from whatever data is available.

The builder implements a data-maturity ladder: it accepts anything from a single
public headline volume up to a full static-model parameter set, fills the gaps
with clearly labelled public defaults, records how every number was obtained, and
emits a NeqSim-ready specification plus a ranked plan of the data that would most
reduce the remaining uncertainty.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Sequence

from .parameters import (
    ACQUISITION_ROUTE,
    AQUIFER_VOLUME_MULTIPLE,
    GEOTHERMAL_GRADIENT_C_PER_KM,
    HYDROSTATIC_GRADIENT_BAR_PER_M,
    PARAMETER_WEIGHTS,
    RECOVERY_FACTOR,
    SEABED_TEMPERATURE_C,
    STANDARD_PRESSURE_BARA,
    STANDARD_TEMPERATURE_K,
    Parameter,
    default_parameter,
    derived,
)

FLUID_TYPES = ("gas", "oil", "gas_condensate")
AQUIFER_STRENGTHS = tuple(AQUIFER_VOLUME_MULTIPLE)

#: Darcy radial-inflow constant for practical metric units
#: (rate in Sm3/day, k in mD, h in m, dp in bar, mu in cP).
DARCY_METRIC_CONSTANT = 0.05357

DATA_TIERS = {
    0: "tier-0-headline",
    1: "tier-1-public-volumetric",
    2: "tier-2-well-and-pvt",
    3: "tier-3-static-model",
}


@dataclass(frozen=True)
class ReservoirInputs:
    """Everything a user may know about a reservoir. Nearly all of it is optional."""

    field_name: str
    fluid_type: str = "oil"
    sea_area: str = "generic"

    # --- structure and rock -------------------------------------------------
    area_km2: float | None = None
    gross_thickness_m: float | None = None
    net_pay_m: float | None = None
    net_to_gross: float | None = None
    porosity: float | None = None
    water_saturation: float | None = None
    permeability_mD: float | None = None

    # --- conditions ---------------------------------------------------------
    datum_depth_m_tvdmsl: float | None = None
    water_depth_m: float | None = None
    initial_pressure_bara: float | None = None
    reservoir_temperature_C: float | None = None
    abandonment_pressure_bara: float | None = None

    # --- fluid --------------------------------------------------------------
    fluid_composition: Mapping[str, float] | None = None
    oil_formation_volume_factor: float | None = None
    gas_compressibility_factor: float | None = None
    solution_gas_oil_ratio_Sm3_per_Sm3: float | None = None
    oil_viscosity_cP: float | None = None
    gas_viscosity_cP: float | None = None

    # --- volumes (any one of these short-circuits the volumetric calculation) -
    stoiip_Sm3: float | None = None
    giip_Sm3: float | None = None
    recoverable_oil_Sm3: float | None = None
    recoverable_gas_Sm3: float | None = None
    recovery_factor: float | None = None

    # --- drive and aquifer --------------------------------------------------
    drive_mechanism: str | None = None
    aquifer_strength: str | None = None
    has_gas_cap: bool = False
    injection_plan: str | None = None

    # --- wells and offtake --------------------------------------------------
    producer_count: int | None = None
    injector_count: int | None = None
    productivity_index_Sm3_per_day_bar: float | None = None
    target_plateau_rate_Sm3_per_day: float | None = None
    plateau_offtake_fraction_per_year: float | None = None
    drainage_radius_m: float | None = None
    wellbore_radius_m: float | None = None
    skin_factor: float | None = None
    drawdown_fraction: float | None = None

    # --- simulation control -------------------------------------------------
    simulation_years: float = 25.0
    time_step_days: float = 30.0

    #: Provenance to attach to every user-supplied value, and its source note.
    provenance: str = "public-reported"
    reference: str = ""
    #: Per-field provenance and source overrides, so values from different data
    #: sources keep their own labels as the model is refined.
    field_provenance: Mapping[str, str] = field(default_factory=dict)
    field_reference: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.fluid_type not in FLUID_TYPES:
            raise ValueError(f"fluid_type must be one of {FLUID_TYPES}")
        if self.aquifer_strength is not None and self.aquifer_strength not in AQUIFER_STRENGTHS:
            raise ValueError(f"aquifer_strength must be one of {AQUIFER_STRENGTHS}")


@dataclass(frozen=True)
class Volumetrics:
    """In-place and recoverable volumes at standard and reservoir conditions."""

    hydrocarbon_pore_volume_rm3: float | None
    stoiip_Sm3: float | None
    giip_Sm3: float | None
    recoverable_oil_Sm3: float | None
    recoverable_gas_Sm3: float | None
    reservoir_oil_volume_rm3: float | None
    reservoir_gas_volume_rm3: float | None
    connate_water_volume_rm3: float | None
    aquifer_volume_rm3: float | None

    def to_dict(self) -> dict:
        return {key: value for key, value in self.__dict__.items()}


@dataclass(frozen=True)
class RefinementItem:
    """One data item that would reduce model uncertainty, with how to get it."""

    parameter: str
    current_provenance: str
    weight: float
    relative_uncertainty: float
    priority_score: float
    acquisition_route: str

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class ReservoirModel:
    """A resolved reservoir model: parameters, volumes, NeqSim spec and gaps."""

    field_name: str
    fluid_type: str
    drive_mechanism: str
    parameters: dict[str, Parameter]
    volumetrics: Volumetrics
    derivations: list[str]
    warnings: list[str]
    data_tier: str
    completeness: float
    refinement_plan: list[RefinementItem]
    neqsim_spec: dict
    changes: list[dict] = field(default_factory=list)
    _inputs: ReservoirInputs | None = field(default=None, repr=False, compare=False)

    def get(self, name: str) -> float | None:
        parameter = self.parameters.get(name)
        return None if parameter is None else parameter.value

    def refine(
        self,
        updates: Mapping[str, Any],
        provenance: str = "measured",
        reference: str = "",
    ) -> "ReservoirModel":
        """Return a new model rebuilt with ``updates`` applied to the inputs."""
        if self._inputs is None:
            raise RuntimeError("this model was not built from ReservoirInputs and cannot be refined")
        unknown = [key for key in updates if not hasattr(self._inputs, key)]
        if unknown:
            raise ValueError(f"unknown input field(s): {', '.join(sorted(unknown))}")

        refined_inputs = replace(
            self._inputs,
            **dict(updates),
            field_provenance={
                **self._inputs.field_provenance,
                **{key: provenance for key in updates},
            },
            field_reference={
                **self._inputs.field_reference,
                **{key: reference for key in updates if reference},
            },
        )
        refined = ReservoirModelBuilder().build(refined_inputs)
        refined.changes = self._diff(refined)
        return refined

    def _diff(self, other: "ReservoirModel") -> list[dict]:
        changes: list[dict] = []
        for name in sorted(set(self.parameters) | set(other.parameters)):
            before = self.parameters.get(name)
            after = other.parameters.get(name)
            if before is None or after is None:
                changes.append(
                    {
                        "parameter": name,
                        "before": None if before is None else before.value,
                        "after": None if after is None else after.value,
                        "provenance_before": None if before is None else before.provenance,
                        "provenance_after": None if after is None else after.provenance,
                    }
                )
                continue
            value_changed = not math.isclose(before.value, after.value, rel_tol=1e-9, abs_tol=0.0)
            if value_changed or before.provenance != after.provenance:
                changes.append(
                    {
                        "parameter": name,
                        "before": before.value,
                        "after": after.value,
                        "provenance_before": before.provenance,
                        "provenance_after": after.provenance,
                    }
                )
        return changes

    def to_dict(self) -> dict:
        return {
            "schemaVersion": "1.0",
            "field_name": self.field_name,
            "fluid_type": self.fluid_type,
            "drive_mechanism": self.drive_mechanism,
            "data_tier": self.data_tier,
            "completeness": self.completeness,
            "parameters": {name: p.to_dict() for name, p in sorted(self.parameters.items())},
            "volumetrics": self.volumetrics.to_dict(),
            "derivations": list(self.derivations),
            "warnings": list(self.warnings),
            "refinement_plan": [item.to_dict() for item in self.refinement_plan],
            "neqsim_spec": self.neqsim_spec,
            "changes": list(self.changes),
        }


class ReservoirModelBuilder:
    """Resolve a :class:`ReservoirInputs` set into a runnable screening model."""

    def build(self, inputs: ReservoirInputs) -> ReservoirModel:
        parameters: dict[str, Parameter] = {}
        derivations: list[str] = []
        warnings: list[str] = []

        self._resolve_conditions(inputs, parameters, derivations, warnings)
        self._resolve_rock(inputs, parameters, warnings)
        self._resolve_fluid(inputs, parameters, derivations)
        drive = self._resolve_drive(inputs, parameters, warnings)
        volumetrics = self._resolve_volumes(inputs, parameters, derivations, warnings, drive)
        self._resolve_wells(inputs, parameters, derivations, warnings, volumetrics)
        self._resolve_aquifer(inputs, parameters, volumetrics)

        tier, completeness = self._assess_maturity(parameters, inputs)
        self._check_physics(inputs, parameters, warnings)
        plan = self._refinement_plan(parameters, inputs)
        spec = self._neqsim_spec(inputs, parameters, volumetrics)

        return ReservoirModel(
            field_name=inputs.field_name,
            fluid_type=inputs.fluid_type,
            drive_mechanism=drive,
            parameters=parameters,
            volumetrics=volumetrics,
            derivations=derivations,
            warnings=warnings,
            data_tier=tier,
            completeness=completeness,
            refinement_plan=plan,
            neqsim_spec=spec,
            _inputs=inputs,
        )

    # -- helpers ------------------------------------------------------------

    def _given(
        self,
        inputs: ReservoirInputs,
        name: str,
        value: float | None,
        unit: str,
    ) -> Parameter | None:
        if value is None:
            return None
        return Parameter(
            name=name,
            value=float(value),
            unit=unit,
            provenance=self._provenance_of(inputs, name),
            reference=self._reference_of(inputs, name),
        )

    @staticmethod
    def _provenance_of(inputs: ReservoirInputs, name: str) -> str:
        return inputs.field_provenance.get(name, inputs.provenance)

    @staticmethod
    def _reference_of(inputs: ReservoirInputs, name: str) -> str:
        return (
            inputs.field_reference.get(name)
            or inputs.reference
            or f"supplied for {inputs.field_name}"
        )

    def _resolve(
        self,
        inputs: ReservoirInputs,
        parameters: dict[str, Parameter],
        name: str,
        value: float | None,
        unit: str | None = None,
    ) -> Parameter:
        """Use the supplied value if present, otherwise the generic default."""
        supplied = self._given(inputs, name, value, unit or "-")
        parameter = supplied if supplied is not None else default_parameter(name)
        parameters[name] = parameter
        return parameter

    # -- resolution steps ---------------------------------------------------

    def _resolve_conditions(
        self,
        inputs: ReservoirInputs,
        parameters: dict[str, Parameter],
        derivations: list[str],
        warnings: list[str],
    ) -> None:
        depth = self._given(inputs, "datum_depth_m_tvdmsl", inputs.datum_depth_m_tvdmsl, "m TVDMSL")
        if depth is not None:
            parameters["datum_depth_m_tvdmsl"] = depth

        pressure = self._given(inputs, "initial_pressure_bara", inputs.initial_pressure_bara, "bara")
        if pressure is None:
            if depth is None:
                raise ValueError(
                    "either initial_pressure_bara or datum_depth_m_tvdmsl must be supplied"
                )
            value = STANDARD_PRESSURE_BARA + HYDROSTATIC_GRADIENT_BAR_PER_M * depth.value
            pressure = derived(
                "initial_pressure_bara",
                round(value, 2),
                "bara",
                basis=[depth],
                reference=(
                    f"normal hydrostatic gradient {HYDROSTATIC_GRADIENT_BAR_PER_M} bar/m; "
                    "verify against RFT/DST data"
                ),
                low=round(0.95 * value, 2),
                high=round(1.25 * value, 2),
            )
            derivations.append(
                f"initial_pressure_bara = {STANDARD_PRESSURE_BARA} + "
                f"{HYDROSTATIC_GRADIENT_BAR_PER_M} x {depth.value:g} m = {pressure.value:g} bara "
                "(normal hydrostatic assumption)"
            )
            warnings.append(
                "Initial pressure was assumed hydrostatic; an over- or under-pressured reservoir "
                "will change in-place gas volume and well deliverability."
            )
        parameters["initial_pressure_bara"] = pressure

        temperature = self._given(
            inputs, "reservoir_temperature_C", inputs.reservoir_temperature_C, "degC"
        )
        if temperature is None:
            if depth is None:
                raise ValueError(
                    "either reservoir_temperature_C or datum_depth_m_tvdmsl must be supplied"
                )
            seabed = SEABED_TEMPERATURE_C.get(inputs.sea_area, SEABED_TEMPERATURE_C["generic"])
            gradient = GEOTHERMAL_GRADIENT_C_PER_KM.get(
                inputs.sea_area, GEOTHERMAL_GRADIENT_C_PER_KM["generic"]
            )
            water_depth = inputs.water_depth_m or 0.0
            below_seabed = max(depth.value - water_depth, 0.0)
            value = seabed + gradient * below_seabed / 1000.0
            temperature = derived(
                "reservoir_temperature_C",
                round(value, 1),
                "degC",
                basis=[depth],
                reference=(
                    f"{seabed} degC seabed + {gradient} degC/km over {below_seabed:g} m below seabed "
                    f"({inputs.sea_area}); verify against a bottom-hole temperature survey"
                ),
                low=round(value - 10.0, 1),
                high=round(value + 10.0, 1),
            )
            derivations.append(
                f"reservoir_temperature_C = {seabed} + {gradient}/1000 x {below_seabed:g} = "
                f"{temperature.value:g} degC (geothermal gradient assumption)"
            )
        parameters["reservoir_temperature_C"] = temperature

        abandonment = self._given(
            inputs, "abandonment_pressure_bara", inputs.abandonment_pressure_bara, "bara"
        )
        if abandonment is None:
            value = max(0.25 * pressure.value, 15.0)
            abandonment = derived(
                "abandonment_pressure_bara",
                round(value, 1),
                "bara",
                basis=[pressure],
                reference="25 % of initial pressure, floored at 15 bara (screening placeholder)",
            )
        parameters["abandonment_pressure_bara"] = abandonment

    def _resolve_rock(
        self,
        inputs: ReservoirInputs,
        parameters: dict[str, Parameter],
        warnings: list[str],
    ) -> None:
        self._resolve(inputs, parameters, "porosity", inputs.porosity)
        self._resolve(inputs, parameters, "water_saturation", inputs.water_saturation)
        self._resolve(inputs, parameters, "net_to_gross", inputs.net_to_gross)
        self._resolve(inputs, parameters, "rock_compressibility_1_per_bar", None)

        for name, value, unit in (
            ("area_km2", inputs.area_km2, "km2"),
            ("gross_thickness_m", inputs.gross_thickness_m, "m"),
            ("net_pay_m", inputs.net_pay_m, "m"),
            ("permeability_mD", inputs.permeability_mD, "mD"),
        ):
            parameter = self._given(inputs, name, value, unit)
            if parameter is not None:
                parameters[name] = parameter

        if inputs.net_pay_m is not None and inputs.gross_thickness_m is not None:
            warnings.append(
                "Both net_pay_m and gross_thickness_m were supplied; net_pay_m is used directly "
                "and net_to_gross is treated as informational to avoid double-counting."
            )

    def _resolve_fluid(
        self,
        inputs: ReservoirInputs,
        parameters: dict[str, Parameter],
        derivations: list[str],
    ) -> None:
        self._resolve(
            inputs, parameters, "oil_formation_volume_factor", inputs.oil_formation_volume_factor
        )
        self._resolve(inputs, parameters, "water_formation_volume_factor", None)
        self._resolve(inputs, parameters, "oil_viscosity_cP", inputs.oil_viscosity_cP)
        self._resolve(inputs, parameters, "gas_viscosity_cP", inputs.gas_viscosity_cP)
        z_factor = self._resolve(
            inputs, parameters, "gas_compressibility_factor", inputs.gas_compressibility_factor
        )

        if inputs.solution_gas_oil_ratio_Sm3_per_Sm3 is not None:
            parameters["solution_gas_oil_ratio_Sm3_per_Sm3"] = self._given(
                inputs,
                "solution_gas_oil_ratio_Sm3_per_Sm3",
                inputs.solution_gas_oil_ratio_Sm3_per_Sm3,
                "Sm3/Sm3",
            )

        pressure = parameters["initial_pressure_bara"]
        temperature = parameters["reservoir_temperature_C"]
        temperature_k = temperature.value + 273.15
        bg = (
            STANDARD_PRESSURE_BARA
            * z_factor.value
            * temperature_k
            / (STANDARD_TEMPERATURE_K * pressure.value)
        )
        parameters["gas_formation_volume_factor"] = derived(
            "gas_formation_volume_factor",
            bg,
            "rm3/Sm3",
            basis=[z_factor, pressure, temperature],
            reference="Bg = (Psc x Z x T) / (Tsc x P) with Psc = 1.01325 bara, Tsc = 288.15 K",
        )
        derivations.append(
            f"gas_formation_volume_factor = {STANDARD_PRESSURE_BARA} x {z_factor.value:g} x "
            f"{temperature_k:.2f} / (288.15 x {pressure.value:g}) = {bg:.6f} rm3/Sm3"
        )

    def _resolve_drive(
        self,
        inputs: ReservoirInputs,
        parameters: dict[str, Parameter],
        warnings: list[str],
    ) -> str:
        aquifer = inputs.aquifer_strength or "weak"
        parameters["aquifer_volume_multiple"] = Parameter(
            name="aquifer_volume_multiple",
            value=AQUIFER_VOLUME_MULTIPLE[aquifer],
            unit="x HCPV",
            provenance=(
                self._provenance_of(inputs, "aquifer_strength")
                if inputs.aquifer_strength
                else "default"
            ),
            reference=(
                f"aquifer strength '{aquifer}'"
                if inputs.aquifer_strength
                else "no aquifer information supplied; a weak aquifer is assumed"
            ),
        )

        if inputs.drive_mechanism is not None:
            drive = inputs.drive_mechanism
        elif inputs.injection_plan in ("water_injection", "gas_injection"):
            drive = inputs.injection_plan
        elif aquifer in ("moderate", "strong"):
            drive = "water_drive"
        elif inputs.fluid_type == "oil":
            drive = "gas_cap_drive" if inputs.has_gas_cap else "solution_gas_drive"
        else:
            drive = "depletion"

        if (inputs.fluid_type, drive) not in RECOVERY_FACTOR:
            warnings.append(
                f"No screening recovery-factor range is tabulated for "
                f"({inputs.fluid_type}, {drive}); a depletion/solution-gas analogue is used."
            )
        return drive

    def _recovery_factor(
        self,
        inputs: ReservoirInputs,
        drive: str,
        parameters: dict[str, Parameter],
    ) -> Parameter:
        supplied = self._given(inputs, "recovery_factor", inputs.recovery_factor, "-")
        if supplied is not None:
            parameters["recovery_factor"] = supplied
            return supplied

        fallback = "depletion" if inputs.fluid_type != "oil" else "solution_gas_drive"
        low, base, high = RECOVERY_FACTOR.get(
            (inputs.fluid_type, drive), RECOVERY_FACTOR[(inputs.fluid_type, fallback)]
        )
        parameter = Parameter(
            name="recovery_factor",
            value=base,
            unit="-",
            provenance="analogue",
            reference=(
                f"public screening range for {inputs.fluid_type} under {drive}; "
                "replace with simulation or analogue field performance"
            ),
            low=low,
            high=high,
        )
        parameters["recovery_factor"] = parameter
        return parameter

    def _resolve_volumes(
        self,
        inputs: ReservoirInputs,
        parameters: dict[str, Parameter],
        derivations: list[str],
        warnings: list[str],
        drive: str,
    ) -> Volumetrics:
        recovery = self._recovery_factor(inputs, drive, parameters)
        bo = parameters["oil_formation_volume_factor"].value
        bg = parameters["gas_formation_volume_factor"].value
        bw = parameters["water_formation_volume_factor"].value

        hcpv = self._hydrocarbon_pore_volume(inputs, parameters, derivations)
        stoiip = inputs.stoiip_Sm3
        giip = inputs.giip_Sm3
        from_geometry = False

        if stoiip is None and giip is None:
            if hcpv is not None:
                from_geometry = True
                if inputs.fluid_type == "oil":
                    stoiip = hcpv / bo
                    derivations.append(
                        f"STOIIP = HCPV / Bo = {hcpv:.4g} / {bo:g} = {stoiip:.4g} Sm3"
                    )
                else:
                    giip = hcpv / bg
                    derivations.append(
                        f"GIIP = HCPV / Bg = {hcpv:.4g} / {bg:.6f} = {giip:.4g} Sm3"
                    )
            elif inputs.recoverable_oil_Sm3 is not None:
                stoiip = inputs.recoverable_oil_Sm3 / recovery.value
                derivations.append(
                    f"STOIIP = recoverable oil / RF = {inputs.recoverable_oil_Sm3:.4g} / "
                    f"{recovery.value:g} = {stoiip:.4g} Sm3 (back-calculated)"
                )
            elif inputs.recoverable_gas_Sm3 is not None:
                giip = inputs.recoverable_gas_Sm3 / recovery.value
                derivations.append(
                    f"GIIP = recoverable gas / RF = {inputs.recoverable_gas_Sm3:.4g} / "
                    f"{recovery.value:g} = {giip:.4g} Sm3 (back-calculated)"
                )
            else:
                raise ValueError(
                    "cannot size the reservoir: supply in-place volume, recoverable volume, "
                    "or the geometry (area_km2 with net_pay_m or gross_thickness_m)"
                )

        recoverable_oil = inputs.recoverable_oil_Sm3
        if recoverable_oil is None and stoiip is not None:
            recoverable_oil = stoiip * recovery.value
        recoverable_gas = inputs.recoverable_gas_Sm3
        if recoverable_gas is None and giip is not None:
            recoverable_gas = giip * recovery.value

        self._cross_check_recovery(
            inputs,
            parameters,
            warnings,
            in_place=stoiip if inputs.fluid_type == "oil" else giip,
            reported_recoverable=(
                inputs.recoverable_oil_Sm3
                if inputs.fluid_type == "oil"
                else inputs.recoverable_gas_Sm3
            ),
            in_place_from_geometry=from_geometry,
            recovery=recovery,
        )

        if hcpv is None:
            hcpv = (stoiip or 0.0) * bo + (giip or 0.0) * bg
            derivations.append(
                f"HCPV back-calculated from in-place volumes = {hcpv:.4g} rm3 "
                "(no geometry supplied)"
            )
            warnings.append(
                "No structural geometry was supplied, so area, net pay, porosity and Sw are "
                "unconstrained; the model reproduces the given volume but cannot be used for "
                "any geometry-driven conclusion."
            )

        porosity = parameters["porosity"].value
        water_saturation = parameters["water_saturation"].value
        pore_volume = hcpv / max(1.0 - water_saturation, 1e-6)
        connate_water_rm3 = pore_volume * water_saturation
        aquifer_rm3 = hcpv * parameters["aquifer_volume_multiple"].value

        volumetrics = Volumetrics(
            hydrocarbon_pore_volume_rm3=hcpv,
            stoiip_Sm3=stoiip,
            giip_Sm3=giip,
            recoverable_oil_Sm3=recoverable_oil,
            recoverable_gas_Sm3=recoverable_gas,
            reservoir_oil_volume_rm3=None if stoiip is None else stoiip * bo,
            reservoir_gas_volume_rm3=None if giip is None else giip * bg,
            connate_water_volume_rm3=connate_water_rm3,
            aquifer_volume_rm3=aquifer_rm3,
        )
        derivations.append(
            f"pore volume = HCPV / (1 - Sw) = {hcpv:.4g} / (1 - {water_saturation:g}) = "
            f"{pore_volume:.4g} rm3 at porosity {porosity:g}"
        )
        return volumetrics

    def _cross_check_recovery(
        self,
        inputs: ReservoirInputs,
        parameters: dict[str, Parameter],
        warnings: list[str],
        in_place: float | None,
        reported_recoverable: float | None,
        in_place_from_geometry: bool,
        recovery: Parameter,
    ) -> None:
        """Compare a geometry-derived in-place volume with a reported recoverable volume."""
        if not in_place_from_geometry or not in_place or not reported_recoverable:
            return
        implied = reported_recoverable / in_place
        parameters["implied_recovery_factor"] = derived(
            "implied_recovery_factor",
            implied,
            "-",
            basis=[parameters["porosity"], parameters["water_saturation"]],
            reference="reported recoverable volume divided by the geometry-derived in-place volume",
        )
        if abs(implied - recovery.value) > 0.25 * recovery.value:
            warnings.append(
                f"The reported recoverable volume implies a recovery factor of {implied:.0%}, "
                f"while the assumed recovery factor is {recovery.value:.0%}. Either the geometry, "
                "the reported volume or the recovery factor is inconsistent; reconcile these "
                "before using the model."
            )

    def _hydrocarbon_pore_volume(
        self,
        inputs: ReservoirInputs,
        parameters: dict[str, Parameter],
        derivations: list[str],
    ) -> float | None:
        if inputs.area_km2 is None:
            return None
        if inputs.net_pay_m is not None:
            thickness = inputs.net_pay_m
            ntg = 1.0
            thickness_note = "net pay used directly (net_to_gross not re-applied)"
        elif inputs.gross_thickness_m is not None:
            thickness = inputs.gross_thickness_m
            ntg = parameters["net_to_gross"].value
            thickness_note = f"gross thickness x net_to_gross {ntg:g}"
        else:
            return None

        porosity = parameters["porosity"].value
        water_saturation = parameters["water_saturation"].value
        hcpv = (
            inputs.area_km2 * 1.0e6 * thickness * ntg * porosity * (1.0 - water_saturation)
        )
        derivations.append(
            f"HCPV = {inputs.area_km2:g} km2 x 1e6 x {thickness:g} m x {ntg:g} x "
            f"{porosity:g} x (1 - {water_saturation:g}) = {hcpv:.4g} rm3 ({thickness_note})"
        )
        return hcpv

    def _resolve_wells(
        self,
        inputs: ReservoirInputs,
        parameters: dict[str, Parameter],
        derivations: list[str],
        warnings: list[str],
        volumetrics: Volumetrics,
    ) -> None:
        self._resolve(inputs, parameters, "drainage_radius_m", inputs.drainage_radius_m)
        self._resolve(inputs, parameters, "wellbore_radius_m", inputs.wellbore_radius_m)
        self._resolve(inputs, parameters, "skin_factor", inputs.skin_factor)
        drawdown_fraction = self._resolve(
            inputs, parameters, "drawdown_fraction", inputs.drawdown_fraction
        )

        pressure = parameters["initial_pressure_bara"]
        drawdown = drawdown_fraction.value * pressure.value
        parameters["design_drawdown_bar"] = derived(
            "design_drawdown_bar",
            round(drawdown, 2),
            "bar",
            basis=[drawdown_fraction, pressure],
            reference="design drawdown = drawdown fraction x initial pressure",
        )

        productivity_index = self._productivity_index(inputs, parameters, derivations, warnings)
        per_well_rate = productivity_index.value * drawdown
        parameters["per_well_rate_Sm3_per_day"] = derived(
            "per_well_rate_Sm3_per_day",
            per_well_rate,
            "Sm3/day",
            basis=[productivity_index, parameters["design_drawdown_bar"]],
            reference="rate = productivity index x design drawdown (linear IPR at initial pressure)",
        )

        plateau = inputs.target_plateau_rate_Sm3_per_day
        if plateau is None:
            offtake = inputs.plateau_offtake_fraction_per_year or 0.07
            recoverable = volumetrics.recoverable_gas_Sm3 or volumetrics.recoverable_oil_Sm3 or 0.0
            plateau = recoverable * offtake / 365.0
            derivations.append(
                f"target plateau = {offtake:g} x recoverable {recoverable:.4g} Sm3 / 365 = "
                f"{plateau:.4g} Sm3/day (screening offtake fraction)"
            )
        plateau_supplied = inputs.target_plateau_rate_Sm3_per_day is not None
        parameters["target_plateau_rate_Sm3_per_day"] = Parameter(
            name="target_plateau_rate_Sm3_per_day",
            value=plateau,
            unit="Sm3/day",
            provenance=(
                self._provenance_of(inputs, "target_plateau_rate_Sm3_per_day")
                if plateau_supplied
                else "default"
            ),
            reference=(
                self._reference_of(inputs, "target_plateau_rate_Sm3_per_day")
                if plateau_supplied
                else "screening plateau offtake fraction of recoverable volume"
            ),
        )

        if inputs.producer_count is not None:
            producers = int(inputs.producer_count)
            provenance = self._provenance_of(inputs, "producer_count")
            reference = self._reference_of(inputs, "producer_count")
        elif per_well_rate > 0.0:
            producers = max(1, math.ceil(plateau / per_well_rate))
            provenance = "derived"
            reference = "producers = ceil(plateau rate / per-well rate at design drawdown)"
            derivations.append(
                f"producer_count = ceil({plateau:.4g} / {per_well_rate:.4g}) = {producers}"
            )
        else:
            producers = 1
            provenance = "default"
            reference = "no deliverability information; a single producer is assumed"
        parameters["producer_count"] = Parameter(
            name="producer_count",
            value=float(producers),
            unit="wells",
            provenance=provenance,
            reference=reference,
        )

        injectors = inputs.injector_count
        if injectors is None:
            injectors = producers if inputs.injection_plan else 0
        parameters["injector_count"] = Parameter(
            name="injector_count",
            value=float(injectors),
            unit="wells",
            provenance=(
                self._provenance_of(inputs, "injector_count")
                if inputs.injector_count is not None
                else "default"
            ),
            reference=(
                "supplied injector count"
                if inputs.injector_count is not None
                else "one injector per producer when an injection plan is declared, else none"
            ),
        )

    def _productivity_index(
        self,
        inputs: ReservoirInputs,
        parameters: dict[str, Parameter],
        derivations: list[str],
        warnings: list[str],
    ) -> Parameter:
        name = "productivity_index_Sm3_per_day_bar"
        supplied = self._given(
            inputs, name, inputs.productivity_index_Sm3_per_day_bar, "Sm3/day/bar"
        )
        if supplied is not None:
            parameters[name] = supplied
            return supplied

        permeability = parameters.get("permeability_mD")
        if permeability is None:
            warnings.append(
                "Neither a productivity index nor a permeability was supplied, so well count "
                "and plateau deliverability are not constrained by reservoir quality."
            )
            parameter = Parameter(
                name=name,
                value=0.0,
                unit="Sm3/day/bar",
                provenance="default",
                reference="unknown: supply a well-test PI or a permeability and net pay",
            )
            parameters[name] = parameter
            return parameter

        thickness = (
            inputs.net_pay_m
            if inputs.net_pay_m is not None
            else (inputs.gross_thickness_m or 0.0) * parameters["net_to_gross"].value
        )
        if inputs.fluid_type == "oil":
            viscosity = parameters["oil_viscosity_cP"].value
            fvf = parameters["oil_formation_volume_factor"].value
        else:
            viscosity = parameters["gas_viscosity_cP"].value
            fvf = parameters["gas_formation_volume_factor"].value

        re_over_rw = parameters["drainage_radius_m"].value / parameters["wellbore_radius_m"].value
        denominator = viscosity * fvf * (math.log(re_over_rw) - 0.75 + parameters["skin_factor"].value)
        if thickness <= 0.0 or denominator <= 0.0:
            parameter = Parameter(
                name=name,
                value=0.0,
                unit="Sm3/day/bar",
                provenance="default",
                reference="Darcy inflow could not be evaluated with the supplied parameters",
            )
            parameters[name] = parameter
            return parameter

        value = DARCY_METRIC_CONSTANT * permeability.value * thickness / denominator
        parameter = derived(
            name,
            value,
            "Sm3/day/bar",
            basis=[permeability, parameters["drainage_radius_m"]],
            reference=(
                "pseudo-steady radial Darcy inflow: J = 0.05357 k h / "
                "(mu B (ln(re/rw) - 0.75 + S)); replace with a well test"
            ),
        )
        parameters[name] = parameter
        derivations.append(
            f"productivity index = {DARCY_METRIC_CONSTANT} x {permeability.value:g} mD x "
            f"{thickness:g} m / ({viscosity:g} cP x {fvf:.4g} x "
            f"(ln({re_over_rw:.1f}) - 0.75 + {parameters['skin_factor'].value:g})) = "
            f"{value:.4g} Sm3/day/bar"
        )
        return parameter

    def _resolve_aquifer(
        self,
        inputs: ReservoirInputs,
        parameters: dict[str, Parameter],
        volumetrics: Volumetrics,
    ) -> None:
        multiple = parameters["aquifer_volume_multiple"].value
        hcpv = volumetrics.hydrocarbon_pore_volume_rm3 or 0.0
        parameters["aquifer_volume_rm3"] = derived(
            "aquifer_volume_rm3",
            hcpv * multiple,
            "rm3",
            basis=[parameters["aquifer_volume_multiple"]],
            reference="aquifer pore volume expressed as a multiple of the hydrocarbon pore volume",
        )

    # -- assessment ---------------------------------------------------------

    def _assess_maturity(
        self,
        parameters: Mapping[str, Parameter],
        inputs: ReservoirInputs,
    ) -> tuple[str, float]:
        total_weight = 0.0
        data_weight = 0.0
        for name, weight in PARAMETER_WEIGHTS.items():
            total_weight += weight
            if name == "fluid_composition":
                if inputs.fluid_composition:
                    data_weight += weight
                continue
            parameter = parameters.get(name)
            if parameter is not None and parameter.is_data_backed:
                data_weight += weight
        completeness = round(data_weight / total_weight, 3) if total_weight else 0.0

        has_geometry = all(
            parameters.get(name) is not None and parameters[name].is_data_backed
            for name in ("area_km2", "porosity", "water_saturation")
        )
        has_pvt = bool(inputs.fluid_composition) or any(
            parameters.get(name) is not None and parameters[name].is_data_backed
            for name in ("oil_formation_volume_factor", "gas_compressibility_factor")
        )
        has_flow = any(
            parameters.get(name) is not None and parameters[name].is_data_backed
            for name in ("permeability_mD", "productivity_index_Sm3_per_day_bar")
        )
        has_aquifer = parameters["aquifer_volume_multiple"].is_data_backed

        if has_geometry and has_pvt and has_flow and has_aquifer:
            tier = 3
        elif has_geometry and (has_pvt or has_flow):
            tier = 2
        elif has_geometry or inputs.stoiip_Sm3 or inputs.giip_Sm3 or inputs.recoverable_oil_Sm3 or inputs.recoverable_gas_Sm3:
            tier = 1
        else:
            tier = 0
        return DATA_TIERS[tier], completeness

    def _check_physics(
        self,
        inputs: ReservoirInputs,
        parameters: Mapping[str, Parameter],
        warnings: list[str],
    ) -> None:
        temperature = parameters["reservoir_temperature_C"].value
        pressure = parameters["initial_pressure_bara"].value
        depth = parameters.get("datum_depth_m_tvdmsl")

        if temperature < 30.0:
            warnings.append(
                f"Reservoir temperature is {temperature:g} degC. A cold reservoir gives little "
                "thermal margin in the flowline, so hydrate and wax management, and cooldown, "
                "should be screened early."
            )
        if temperature > 150.0:
            warnings.append(
                f"Reservoir temperature is {temperature:g} degC (HP/HT range); check material "
                "selection, completion limits and PVT model validity."
            )
        if depth is not None and depth.value < 1200.0:
            warnings.append(
                f"Datum depth is {depth.value:g} m TVDMSL. Shallow reservoirs have low initial "
                "energy and low gas expansion, so pressure support and artificial lift usually "
                "control the recovery factor."
            )
        if depth is not None:
            hydrostatic = STANDARD_PRESSURE_BARA + HYDROSTATIC_GRADIENT_BAR_PER_M * depth.value
            ratio = pressure / hydrostatic
            if ratio > 1.15:
                warnings.append(
                    f"Initial pressure is {ratio:.2f} x hydrostatic (over-pressured); confirm the "
                    "pressure basis and the drilling/completion implications."
                )
            elif ratio < 0.85:
                warnings.append(
                    f"Initial pressure is {ratio:.2f} x hydrostatic (under-pressured or already "
                    "depleted); confirm whether the pressure is virgin or current."
                )
        if parameters["water_saturation"].value > 0.5:
            warnings.append(
                "Water saturation above 0.5 leaves little hydrocarbon pore volume; confirm the "
                "saturation-height model and the contacts."
            )
        if inputs.fluid_type == "gas" and parameters["aquifer_volume_multiple"].value >= 12.0:
            warnings.append(
                "A moderate-to-strong aquifer under a gas reservoir traps gas behind the advancing "
                "water and typically lowers the recovery factor; water handling must be sized."
            )

    def _refinement_plan(
        self,
        parameters: Mapping[str, Parameter],
        inputs: ReservoirInputs,
    ) -> list[RefinementItem]:
        items: list[RefinementItem] = []
        for name, weight in PARAMETER_WEIGHTS.items():
            if name == "fluid_composition":
                if inputs.fluid_composition:
                    continue
                items.append(
                    RefinementItem(
                        parameter=name,
                        current_provenance="missing",
                        weight=weight,
                        relative_uncertainty=1.0,
                        priority_score=round(weight, 3),
                        acquisition_route=ACQUISITION_ROUTE[name],
                    )
                )
                continue
            parameter = parameters.get(name)
            if parameter is None:
                items.append(
                    RefinementItem(
                        parameter=name,
                        current_provenance="missing",
                        weight=weight,
                        relative_uncertainty=1.0,
                        priority_score=round(weight, 3),
                        acquisition_route=ACQUISITION_ROUTE.get(name, "field-specific data"),
                    )
                )
                continue
            if parameter.is_data_backed:
                continue
            uncertainty = parameter.uncertainty_pct
            relative = 0.5 if uncertainty is None else min(uncertainty / 100.0, 1.0)
            items.append(
                RefinementItem(
                    parameter=name,
                    current_provenance=parameter.provenance,
                    weight=weight,
                    relative_uncertainty=round(relative, 3),
                    priority_score=round(weight * relative, 3),
                    acquisition_route=ACQUISITION_ROUTE.get(name, "field-specific data"),
                )
            )
        items.sort(key=lambda item: (-item.priority_score, item.parameter))
        return items

    # -- NeqSim hand-off ----------------------------------------------------

    def _neqsim_spec(
        self,
        inputs: ReservoirInputs,
        parameters: Mapping[str, Parameter],
        volumetrics: Volumetrics,
    ) -> dict:
        pressure = parameters["initial_pressure_bara"].value
        drawdown = parameters["design_drawdown_bar"].value
        producers = int(parameters["producer_count"].value)
        per_well_rate = parameters["per_well_rate_Sm3_per_day"].value
        plateau = parameters["target_plateau_rate_Sm3_per_day"].value

        producer_rate = plateau / producers if producers else plateau
        producer_list = [
            {
                "name": f"PROD-{index + 1}",
                "flowRate": {"value": round(producer_rate, 4), "unit": "Sm3/day"},
            }
            for index in range(producers)
        ]

        bottomhole = max(pressure - drawdown, 1.0)
        quadratic_pi = None
        if per_well_rate > 0.0:
            squared_drawdown = pressure**2 - bottomhole**2
            if squared_drawdown > 0.0:
                quadratic_pi = (per_well_rate / 1.0e6) / squared_drawdown

        composition = dict(inputs.fluid_composition) if inputs.fluid_composition else None

        return {
            "schemaVersion": "1.0",
            "tool": "runReservoir",
            "components": composition,
            "reservoirConditions": {
                "temperature_C": parameters["reservoir_temperature_C"].value,
                "pressure_bara": pressure,
                "abandonmentPressure_bara": parameters["abandonment_pressure_bara"].value,
            },
            # SimpleReservoir.setReservoirFluid takes IN-SITU reservoir volumes at the
            # fluid's temperature and pressure, even though the MCP keys are named _Sm3.
            "gasVolume_Sm3": volumetrics.reservoir_gas_volume_rm3 or 0.0,
            "oilVolume_Sm3": volumetrics.reservoir_oil_volume_rm3 or 0.0,
            "waterVolume_Sm3": volumetrics.connate_water_volume_rm3 or 0.0,
            "volumeBasis": "reservoir m3 at reservoir temperature and pressure",
            # The aquifer is reported separately: adding a large aquifer to the tank water
            # volume changes the depletion behaviour and must be a deliberate choice.
            "aquiferVolume_rm3": volumetrics.aquifer_volume_rm3 or 0.0,
            "standardConditionVolumes": {
                "stoiip_Sm3": volumetrics.stoiip_Sm3,
                "giip_Sm3": volumetrics.giip_Sm3,
                "recoverableOil_Sm3": volumetrics.recoverable_oil_Sm3,
                "recoverableGas_Sm3": volumetrics.recoverable_gas_Sm3,
            },
            "producers": producer_list,
            "injectors": int(parameters["injector_count"].value),
            "wellModel": {
                "inflowModel": "PRODUCTION_INDEX",
                "productivityIndex_Sm3_per_day_bar": per_well_rate / drawdown if drawdown else 0.0,
                "neqsimWellProductionIndex_MSm3_per_day_bar2": quadratic_pi,
                "reservoirPressure_bara": pressure,
                "designBottomHolePressure_bara": bottomhole,
            },
            "simulationYears": inputs.simulation_years,
            "timeStepDays": inputs.time_step_days,
        }


def build_reservoir_model(**kwargs: Any) -> ReservoirModel:
    """Convenience wrapper: build a model directly from keyword inputs."""
    return ReservoirModelBuilder().build(ReservoirInputs(**kwargs))


def summarize(model: ReservoirModel, top_refinements: int = 5) -> str:
    """Return a short human-readable summary of a built model."""
    lines = [
        f"{model.field_name} ({model.fluid_type}, {model.drive_mechanism})",
        f"  data tier      : {model.data_tier}  completeness {model.completeness:.0%}",
    ]
    volumes: Sequence[tuple[str, float | None]] = (
        ("STOIIP", model.volumetrics.stoiip_Sm3),
        ("GIIP", model.volumetrics.giip_Sm3),
        ("recoverable oil", model.volumetrics.recoverable_oil_Sm3),
        ("recoverable gas", model.volumetrics.recoverable_gas_Sm3),
    )
    for label, value in volumes:
        if value:
            lines.append(f"  {label:<15}: {value:.4g} Sm3")
    lines.append(f"  producers      : {int(model.get('producer_count') or 0)}")
    if model.refinement_plan:
        lines.append("  next data to acquire:")
        for item in model.refinement_plan[:top_refinements]:
            lines.append(f"    - {item.parameter} ({item.current_provenance}) -> {item.acquisition_route}")
    for warning in model.warnings:
        lines.append(f"  ! {warning}")
    return "\n".join(lines)
