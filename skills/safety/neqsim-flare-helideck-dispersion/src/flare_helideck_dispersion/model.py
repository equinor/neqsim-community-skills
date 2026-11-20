"""Source and plume model for an unignited flare-tip release.

The model is a screening chain, not a CFD substitute:

1. Choked (sonic) flow at the flare tip with ideal-gas relations, and a Birch
   notional nozzle that turns the choked state into an equivalent atmospheric-pressure
   jet (effective diameter, velocity, density).
2. Briggs (1975) momentum plume rise for the vertical momentum component of an inclined
   tip, with the Briggs stable-air limits for Pasquill classes E and F and a
   dense-gas sinking term (negative buoyancy) with its own final-rise cap.
3. A Gaussian plume with Briggs open-country sigmas (Briggs 1973), sea-surface
   reflection and a rise-dependent virtual-source initial spread
   ``sigma0 = |dh| / sigma0_divisor``.
4. A free-jet centreline decay (Chen and Rodi 1980, ``C/C0 = 6.2 d/x sqrt(rho0/rho_a)``)
   as an independent cross-check of the jet-phase distance to a given LFL fraction.

Geometry is in east/north/up metres relative to the flare tip, with heights above sea
level. Wind direction is the direction the wind blows FROM (meteorological
convention); the plume travels towards ``wind_from + 180`` degrees.

References:
    Briggs, G. A. (1969) Plume Rise, USAEC Critical Review Series.
    Briggs, G. A. (1973) Diffusion estimation for small emissions, ATDL-106.
    Briggs, G. A. (1975) Plume rise predictions, in Lectures on Air Pollution and
    Environmental Impact Analyses, AMS.
    Birch, A. D., Brown, D. R., Dodson, M. G. and Swaffield, F. (1984) The structure and
    concentration decay of high pressure jets of natural gas, Combust. Sci. Technol. 36,
    249-261 (notional nozzle).
    Chen, C. J. and Rodi, W. (1980) Vertical Turbulent Buoyant Jets: A Review of
    Experimental Data, Pergamon.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np

R_GAS = 8.314462618
"""Universal gas constant, J/(mol K)."""
P_AMB_PA = 101325.0
"""Ambient pressure, Pa."""
M_AIR = 0.028964
"""Molar mass of air, kg/mol."""
GRAVITY = 9.81
"""Gravitational acceleration, m/s2."""

RISE_MODES = ("briggs", "none")
"""``briggs``: momentum rise and dense-gas sinking; ``none``: passive release at tip
height (bounding case)."""

SIGMA_Y_COEFFS: dict[str, tuple] = {
    "A": (0.22, 0.0001),
    "B": (0.16, 0.0001),
    "C": (0.11, 0.0001),
    "D": (0.08, 0.0001),
    "E": (0.06, 0.0001),
    "F": (0.04, 0.0001),
}
"""Briggs open-country ``sigma_y = a x / sqrt(1 + b x)`` coefficients (a, b)."""

SIGMA_Z_COEFFS: dict[str, tuple] = {
    "A": (0.20, 0.0, 1.0),
    "B": (0.12, 0.0, 1.0),
    "C": (0.08, 0.0002, 0.5),
    "D": (0.06, 0.0015, 0.5),
    "E": (0.03, 0.0003, 1.0),
    "F": (0.016, 0.0003, 1.0),
}
"""Briggs open-country ``sigma_z = a x / (1 + b x)^p`` coefficients (a, b, p)."""


def _default_dtheta_dz() -> dict[str, float]:
    """Return the default potential-temperature gradients for stable classes."""
    return {"E": 0.020, "F": 0.035}


@dataclass(frozen=True)
class ModelParameters:
    """Tunable physical parameters of the plume model.

    Attributes:
        tilt_deg: Flare-tip inclination above horizontal, degrees. Only the vertical
            momentum component ``v sin(tilt)`` lifts the plume.
        sigma0_divisor: Virtual-source initial spread ``sigma0 = |dh| / divisor``.
        wind_exponent: Power-law exponent that scales the 10 m wind to release height.
        reference_height_m: Height of the reference wind speed, m.
        ambient_temperature_k: Ambient air temperature, K (air density and stable
            stratification).
        stable_dtheta_dz: Potential-temperature gradient (K/m) per stable class, which
            sets the Briggs stable-air limits on rise and sinking.
    """

    tilt_deg: float = 45.0
    sigma0_divisor: float = 3.5
    wind_exponent: float = 0.11
    reference_height_m: float = 10.0
    ambient_temperature_k: float = 278.15
    stable_dtheta_dz: Mapping[str, float] = field(default_factory=_default_dtheta_dz)

    def __post_init__(self) -> None:
        """Validate parameter ranges.

        Raises:
            ValueError: If a parameter is outside its physical range.
        """
        if not 0.0 < self.tilt_deg <= 90.0:
            raise ValueError("tilt_deg must be in (0, 90] degrees")
        if self.sigma0_divisor <= 0.0:
            raise ValueError("sigma0_divisor must be positive")
        if self.wind_exponent < 0.0:
            raise ValueError("wind_exponent must be non-negative")
        if self.reference_height_m <= 0.0 or self.ambient_temperature_k <= 0.0:
            raise ValueError(
                "reference height and ambient temperature must be positive"
            )

    @property
    def rho_air(self) -> float:
        """Ambient air density, kg/m3."""
        return P_AMB_PA * M_AIR / (R_GAS * self.ambient_temperature_k)

    def replace(self, **changes: Any) -> ModelParameters:
        """Return a copy with selected fields replaced.

        Args:
            **changes: Field names and new values.

        Returns:
            A new :class:`ModelParameters`.
        """
        values = asdict(self)
        values.update(changes)
        return ModelParameters(**values)


@dataclass
class ReleaseCase:
    """Input description of one unignited tip release.

    Attributes:
        name: Case identifier carried into every output.
        mass_flow_kg_s: Release mass flow, kg/s (rated PSV capacity or blowdown peak).
        mw_kg_mol: Molar mass of the release gas, kg/mol.
        gamma: Heat-capacity ratio Cp/Cv.
        t0_k: Stagnation temperature upstream of the tip, K.
        lfl_vol_frac: Lower flammability limit as a volume fraction of the FUEL
            (combustible part) of the gas, for example 0.04.
        fuel_mole_frac: Mole fraction of combustible gas in the release gas
            (inerts such as CO2 and N2 are excluded).
        tip_diameter_m: Flare-tip exit diameter, m.
        tip_override: Optional mapping with ``velocity_m_s``, ``diameter_m`` and
            ``density_kg_m3`` that replaces the choked-flow notional jet, for example
            with values from a real-gas flare-tip calculation. The override fixes the
            jet momentum; a later mass-flow scaling then only scales the concentration
            source term.
        rho_gas_amb_kg_m3: Gas density at ambient conditions, kg/m3. Defaults to the
            ideal-gas value at ambient temperature.
        description: Free text.
    """

    name: str
    mass_flow_kg_s: float
    mw_kg_mol: float
    gamma: float
    t0_k: float
    lfl_vol_frac: float
    fuel_mole_frac: float
    tip_diameter_m: float = 0.6
    tip_override: Mapping[str, float] | None = None
    rho_gas_amb_kg_m3: float | None = None
    description: str = ""

    def __post_init__(self) -> None:
        """Validate inputs.

        Raises:
            ValueError: If an input is non-physical.
        """
        if self.mass_flow_kg_s <= 0.0:
            raise ValueError("mass_flow_kg_s must be positive")
        if not 0.001 < self.mw_kg_mol < 1.0:
            raise ValueError("mw_kg_mol must be in kg/mol (for example 0.019)")
        if self.gamma <= 1.0:
            raise ValueError("gamma must be greater than 1")
        if self.t0_k <= 0.0 or self.tip_diameter_m <= 0.0:
            raise ValueError("t0_k and tip_diameter_m must be positive")
        if not 0.0 < self.lfl_vol_frac < 1.0:
            raise ValueError("lfl_vol_frac must be a volume fraction in (0, 1)")
        if not 0.0 < self.fuel_mole_frac <= 1.0:
            raise ValueError("fuel_mole_frac must be in (0, 1]")
        if self.tip_override is not None:
            missing = {"velocity_m_s", "diameter_m", "density_kg_m3"} - set(
                self.tip_override
            )
            if missing:
                raise ValueError(f"tip_override is missing {sorted(missing)}")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable mapping.

        Returns:
            Plain dictionary of the case fields.
        """
        data = asdict(self)
        if self.tip_override is not None:
            data["tip_override"] = dict(self.tip_override)
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ReleaseCase:
        """Build a case from a mapping (for example parsed JSON).

        Args:
            data: Mapping with the field names of :class:`ReleaseCase`. The aliases
                ``mdot_kg_s``, ``lfl`` and ``rho_gas_amb`` are accepted.

        Returns:
            The release case.
        """
        values = dict(data)
        aliases = {
            "mdot_kg_s": "mass_flow_kg_s",
            "lfl": "lfl_vol_frac",
            "rho_gas_amb": "rho_gas_amb_kg_m3",
            "id": "name",
        }
        for old, new in aliases.items():
            if old in values and new not in values:
                values[new] = values.pop(old)
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in values.items() if k in known})


def choked_tip(
    mass_flow_kg_s: float,
    mw_kg_mol: float,
    gamma: float,
    t0_k: float,
    d_exit_m: float,
    ambient_temperature_k: float = 278.15,
) -> dict[str, Any]:
    """Compute tip exit conditions and the Birch notional nozzle.

    The stagnation pressure needed to pass ``mass_flow_kg_s`` through the exit area is
    found from the choked-flow mass flux. If it exceeds the critical pressure ratio the
    flow is choked at the exit and the notional nozzle expands the jet to ambient
    pressure with momentum conservation (Birch); otherwise the exit flow is subsonic
    at ambient pressure.

    Args:
        mass_flow_kg_s: Mass flow, kg/s.
        mw_kg_mol: Molar mass, kg/mol.
        gamma: Heat-capacity ratio.
        t0_k: Stagnation temperature, K.
        d_exit_m: Physical exit diameter, m.
        ambient_temperature_k: Ambient temperature for the density ratio, K.

    Returns:
        Dictionary with ``p0_bara``, ``choked``, ``v_exit_ms``, ``mach_throat``,
        ``rho_exp`` (notional-nozzle density), ``d_eff_m``, ``t_exp_k`` and
        ``rho_ratio_to_air``.
    """
    area = math.pi * d_exit_m**2 / 4.0
    g_flux = mass_flow_kg_s / area
    fac = math.sqrt(gamma * mw_kg_mol / (R_GAS * t0_k)) * (2.0 / (gamma + 1.0)) ** (
        (gamma + 1.0) / (2.0 * (gamma - 1.0))
    )
    p0 = g_flux / fac
    if p0 > P_AMB_PA * ((gamma + 1.0) / 2.0) ** (gamma / (gamma - 1.0)):
        ts = t0_k * 2.0 / (gamma + 1.0)
        ps = p0 * (2.0 / (gamma + 1.0)) ** (gamma / (gamma - 1.0))
        rhos = ps * mw_kg_mol / (R_GAS * ts)
        vs = math.sqrt(gamma * R_GAS * ts / mw_kg_mol)
        ve = vs + (ps - P_AMB_PA) / (rhos * vs)
        te = ts
        choked = True
    else:
        te = t0_k
        ve = mass_flow_kg_s / (P_AMB_PA * mw_kg_mol / (R_GAS * t0_k) * area)
        choked = False
        p0 = P_AMB_PA
    rho_e = P_AMB_PA * mw_kg_mol / (R_GAS * te)
    d_eff = math.sqrt(4.0 * mass_flow_kg_s / (math.pi * rho_e * ve))
    rho_air = P_AMB_PA * M_AIR / (R_GAS * ambient_temperature_k)
    return {
        "p0_bara": p0 / 1e5,
        "choked": choked,
        "v_exit_ms": ve,
        "mach_throat": (
            1.0 if choked else ve / math.sqrt(gamma * R_GAS * t0_k / mw_kg_mol)
        ),
        "rho_exp": rho_e,
        "d_eff_m": d_eff,
        "t_exp_k": te,
        "rho_ratio_to_air": rho_e / rho_air,
    }


def sigmas(x: Any, stability: str) -> tuple:
    """Briggs open-country lateral and vertical dispersion coefficients.

    Args:
        x: Downwind distance, m (scalar or array).
        stability: Pasquill class ``A`` to ``F``.

    Returns:
        Tuple ``(sigma_y, sigma_z)`` in metres, same shape as ``x``.

    Raises:
        ValueError: If the stability class is unknown.
    """
    if stability not in SIGMA_Y_COEFFS:
        raise ValueError(f"stability must be one of {sorted(SIGMA_Y_COEFFS)}")
    ya, yb = SIGMA_Y_COEFFS[stability]
    za, zb, zp = SIGMA_Z_COEFFS[stability]
    sy = ya * x / np.sqrt(1.0 + yb * x)
    sz = za * x / (1.0 + zb * x) ** zp
    return sy, sz


def wind_frame(rel_east_north: np.ndarray, wind_from_deg: float) -> tuple:
    """Rotate east/north offsets into downwind/crosswind coordinates.

    Args:
        rel_east_north: Array ``(N, 2+)`` of east and north offsets from the source, m.
        wind_from_deg: Direction the wind blows FROM, degrees true.

    Returns:
        Tuple ``(x_downwind, y_crosswind)``; the plume travels towards
        ``wind_from_deg + 180``.
    """
    travel = math.radians(wind_from_deg + 180.0)
    wx, wy = math.sin(travel), math.cos(travel)
    x = rel_east_north[:, 0] * wx + rel_east_north[:, 1] * wy
    y = -rel_east_north[:, 0] * wy + rel_east_north[:, 1] * wx
    return x, y


class Release:
    """Unignited tip release with all derived plume quantities.

    Args:
        case: The release description.
        params: Plume-model parameters.
    """

    def __init__(
        self, case: ReleaseCase, params: ModelParameters | None = None
    ) -> None:
        self.case = case
        self.params = params or ModelParameters()
        self.name = case.name
        self.mdot = case.mass_flow_kg_s
        self.mw = case.mw_kg_mol
        self.lfl = case.lfl_vol_frac
        self.fuel_y = case.fuel_mole_frac
        self.rho_air = self.params.rho_air
        self.tip = choked_tip(
            case.mass_flow_kg_s,
            case.mw_kg_mol,
            case.gamma,
            case.t0_k,
            case.tip_diameter_m,
            self.params.ambient_temperature_k,
        )
        if case.tip_override:
            override = case.tip_override
            self.tip["v_exit_ms"] = override["velocity_m_s"]
            self.tip["d_eff_m"] = override["diameter_m"]
            self.tip["rho_exp"] = override["density_kg_m3"]
            self.tip["rho_ratio_to_air"] = override["density_kg_m3"] / self.rho_air
        self.rho_gas_amb = (
            case.rho_gas_amb_kg_m3
            if case.rho_gas_amb_kg_m3
            else P_AMB_PA * case.mw_kg_mol / (R_GAS * self.params.ambient_temperature_k)
        )

    def plume_params(self, u10: float, z_rel: float) -> tuple:
        """Wind at release height, momentum flux parameter and neutral final rise.

        Only the vertical momentum component ``v sin(tilt)`` is used for the rise; the
        horizontal component is ignored, which is conservative for the height of the
        cloud.

        Args:
            u10: Wind speed at the reference height, m/s.
            z_rel: Release height above sea level, m.

        Returns:
            Tuple ``(u, fm, beta, dh_final)``: wind at release height (m/s), Briggs
            momentum flux parameter (m4/s2), entrainment parameter and neutral final
            rise (m).
        """
        p = self.params
        u = u10 * (max(z_rel, 1.0) / p.reference_height_m) ** p.wind_exponent
        v = self.tip["v_exit_ms"] * math.sin(math.radians(p.tilt_deg))
        d = self.tip["d_eff_m"]
        fm = self.tip["rho_ratio_to_air"] * v * v * d * d / 4.0
        beta = 1.0 / 3.0 + u / v
        dh_final = 3.0 * d * v / u
        return u, fm, beta, dh_final

    def centreline_height(
        self,
        xs: np.ndarray,
        u10: float,
        z_rel: float,
        rise_mode: str,
        stability: str | None = None,
    ) -> np.ndarray:
        """Plume centreline rise (signed, m) at downwind distances ``xs``.

        In stable classes E/F the Briggs stable-air limits cap the momentum rise and
        the sinking of a dense plume (potential-temperature gradients from
        :class:`ModelParameters`). Without them the neutral rise ``3 d v / u`` grows as
        ``1/u`` and over-lifts the plume in light stable wind.

        Args:
            xs: Downwind distances, m.
            u10: Reference wind speed, m/s.
            z_rel: Release height above sea level, m.
            rise_mode: ``briggs`` or ``none``.
            stability: Pasquill class or ``None``.

        Returns:
            Centreline height change at each distance, m (negative means sinking).

        Raises:
            ValueError: If ``rise_mode`` is unknown.
        """
        if rise_mode not in RISE_MODES:
            raise ValueError(f"rise_mode must be one of {RISE_MODES}")
        if rise_mode == "none":
            return np.zeros_like(xs)
        u, fm, beta, dh_final = self.plume_params(u10, z_rel)
        dh = np.minimum(dh_final, (3.0 * fm * xs / (beta**2 * u**2)) ** (1.0 / 3.0))
        s = None
        gradients = self.params.stable_dtheta_dz
        if stability in gradients:
            s = GRAVITY / self.params.ambient_temperature_k * gradients[stability]
            dh = np.minimum(dh, 1.5 * (fm / (u * math.sqrt(s))) ** (1.0 / 3.0))
        v = self.tip["v_exit_ms"]
        d = self.tip["d_eff_m"]
        fb = GRAVITY * (self.tip["rho_ratio_to_air"] - 1.0) * v * d * d / 4.0
        if fb > 0.0:
            fin = (21.425 * fb**0.75 if fb < 55.0 else 38.71 * fb**0.6) / u
            if s is not None:
                fin = min(fin, 2.6 * (fb / (u * s)) ** (1.0 / 3.0))
            sink = np.minimum(1.6 * fb ** (1.0 / 3.0) * xs ** (2.0 / 3.0) / u, fin)
            dh = dh - sink
        return dh

    def pct_lfl(
        self,
        pts: np.ndarray,
        wind_from_deg: float,
        u10: float,
        stability: str,
        tip_pos: np.ndarray,
        rise_mode: str = "briggs",
    ) -> np.ndarray:
        """Percent of the LFL at points in east/north/up coordinates.

        Gaussian plume ``C = Q / (2 pi u sy sz) exp(-y2/2sy2) [exp(-(z-h)2/2sz2) +
        exp(-(z+h)2/2sz2)]`` with sea reflection and total spreads
        ``sqrt(sigma_briggs2 + sigma0_2)``. Points within 1 m downwind or upwind of the
        source return zero.

        Args:
            pts: Array ``(N, 3)`` of east, north, up coordinates, m (up is height ASL).
            wind_from_deg: Direction the wind blows FROM, degrees true.
            u10: Wind speed at the reference height, m/s.
            stability: Pasquill class.
            tip_pos: Source position ``(e, n, up)``, m.
            rise_mode: ``briggs`` (momentum rise and cold-gas sinking) or ``none``
                (passive release at tip height, bounding case).

        Returns:
            Percent of LFL at each point.
        """
        z_rel = tip_pos[2]
        u, _fm, _beta, _dh_final = self.plume_params(u10, z_rel)
        rel = pts - tip_pos
        x, y = wind_frame(rel, wind_from_deg)
        ok = x > 1.0
        xs = np.where(ok, x, 1.0)
        dh = self.centreline_height(xs, u10, z_rel, rise_mode, stability)
        hc = np.maximum(z_rel + dh, 0.0)
        sy, sz = sigmas(xs, stability)
        if rise_mode != "none":
            s0 = np.abs(dh) / self.params.sigma0_divisor
        else:
            s0 = np.full_like(xs, self.tip["d_eff_m"])
        sy = np.sqrt(sy**2 + s0**2)
        sz = np.sqrt(sz**2 + s0**2)
        z = pts[:, 2]
        c = (
            self.mdot
            / (2.0 * np.pi * u * sy * sz)
            * np.exp(-0.5 * (y / sy) ** 2)
            * (
                np.exp(-0.5 * ((z - hc) / sz) ** 2)
                + np.exp(-0.5 * ((z + hc) / sz) ** 2)
            )
        )
        frac_fuel = c / self.rho_gas_amb * self.fuel_y
        return np.where(ok, frac_fuel / self.lfl * 100.0, 0.0)

    def jet_distance_to(self, frac_lfl: float) -> float:
        """Free-jet axial distance at which fuel concentration falls to a LFL fraction.

        Chen and Rodi (1980): ``C/C0 = 6.2 (d / x) sqrt(rho0 / rho_a)``.

        Args:
            frac_lfl: Fraction of the LFL, for example 0.2 for 20 % LFL.

        Returns:
            Axial distance from the notional nozzle, m.
        """
        c_target = frac_lfl * self.lfl / self.fuel_y
        d = self.tip["d_eff_m"]
        return 6.2 * d * math.sqrt(self.tip["rho_ratio_to_air"]) / c_target

    def axis_distance_to_pct_lfl(
        self,
        pct_lfl: float,
        u10: float,
        stability: str,
        tip_z: float,
        rise_mode: str = "briggs",
        x_max_m: float = 10000.0,
        dx_m: float = 5.0,
    ) -> float:
        """Last downwind distance at which the plume centreline reaches a given % LFL.

        The last crossing (not the first) is reported because a lifted plume can be
        above the threshold, fall below it and return to it further downwind.

        Args:
            pct_lfl: Threshold in percent of the LFL.
            u10: Reference wind speed, m/s.
            stability: Pasquill class.
            tip_z: Release height above sea level, m.
            rise_mode: ``briggs`` or ``none``.
            x_max_m: Search limit, m.
            dx_m: Search step, m.

        Returns:
            Distance in metres, or 0.0 if the threshold is never reached.
        """
        xs = np.arange(dx_m, x_max_m + dx_m, dx_m)
        dh = self.centreline_height(xs, u10, tip_z, rise_mode, stability)
        hc = np.maximum(tip_z + dh, 0.0)
        pts = np.column_stack([xs, np.zeros_like(xs), hc])
        tip_pos = np.array([0.0, 0.0, tip_z])
        values = self.pct_lfl(pts, 270.0, u10, stability, tip_pos, rise_mode)
        idx = np.nonzero(values >= pct_lfl)[0]
        return float(xs[idx[-1]]) if idx.size else 0.0


def jet_consistency_check(
    release: Release,
    u10: float,
    stability: str,
    tip_z: float,
    frac_lfl: float = 0.2,
) -> dict[str, Any]:
    """Compare the Gaussian-plume distance with the free-jet distance to a LFL fraction.

    A Gaussian plume whose virtual source over-dilutes a momentum jet reaches a given
    LFL fraction much closer to the tip than a free jet does. The flag below marks that
    inconsistency so a reviewer can treat the Gaussian value as non-conservative.

    Args:
        release: The release.
        u10: Reference wind speed, m/s.
        stability: Pasquill class.
        tip_z: Release height above sea level, m.
        frac_lfl: Fraction of the LFL, for example 0.2.

    Returns:
        Dictionary with ``gaussian_last_crossing_m``, ``free_jet_axial_m``,
        ``ratio_gaussian_to_free_jet`` and ``gaussian_shorter_than_free_jet``.
    """
    gauss = release.axis_distance_to_pct_lfl(frac_lfl * 100.0, u10, stability, tip_z)
    jet = release.jet_distance_to(frac_lfl)
    return {
        "u10_m_s": u10,
        "stability": stability,
        "frac_lfl": frac_lfl,
        "gaussian_last_crossing_m": gauss,
        "free_jet_axial_m": jet,
        "ratio_gaussian_to_free_jet": gauss / jet if jet > 0.0 else float("nan"),
        "gaussian_shorter_than_free_jet": gauss < jet,
    }
