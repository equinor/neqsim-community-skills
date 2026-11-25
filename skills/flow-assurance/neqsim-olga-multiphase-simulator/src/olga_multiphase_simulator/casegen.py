"""Grimsnes-style OLGA case generator: genkey for a subsea flowline + riser from a route profile and a NeqSim PVT table.

The generated case has the topology used for tie-back transient studies::

    wells (SOURCE at the template) --> FP_PROD (seabed pipes + riser) --> NODE_TOP (internal) --+--> FP_TOP (ESDV, optional choke) --> NODE_SEP (pressure)
                                                                                                 +--> FP_BDV (blowdown valve)          --> NODE_FLARE (pressure)

All inputs are plain Python values so a study can sweep rate, closing time, valve size or wall layers and re-render the case.
Nothing here validates the physics: always ``OlgaRunner.rule_check`` the text, and read the ``MASS SOURCE INFORMATION`` block back from
the ``.out`` file (see SKILL.md).  Only OLGA 2025.1 keyword names verified by the rules engine are used.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .geometry import (
    Discretization,
    DiscretizationError,
    PipeSegment,
    _enforce_neighbour_ratio,
    discretize_route,
)

__all__ = [
    "STEEL",
    "FlowlineCaseSpec",
    "Material",
    "RouteProfile",
    "WallLayer",
    "build_mesh",
    "equivalent_insulation_thickness",
    "load_route_profile",
    "overall_u_inner",
    "render_genkey",
    "simplify_route",
    "wrap_genkey",
]


# ------------------------------------------------------------------------------------------------ materials / walls
@dataclass(frozen=True)
class Material:
    """Solid material of a pipe-wall layer (SI)."""

    label: str
    conductivity: float  # W/m-C
    density: float  # kg/m3
    capacity: float  # J/kg-C


STEEL = Material("STEEL_X65", 45.0, 7850.0, 480.0)


@dataclass(frozen=True)
class WallLayer:
    """One concentric wall layer, innermost first."""

    material: Material
    thickness_m: float


def overall_u_inner(
    d_inner_m: float, layers: Sequence[WallLayer], h_outer: float
) -> float:
    """Overall heat-transfer coefficient referred to the INNER wall surface (W/m2-K), inner film neglected.

    :param d_inner_m: inner diameter of the pipe
    :param layers: wall layers from the inside out
    :param h_outer: outer film coefficient, W/m2-K
    :return: U on the inner-wall basis
    """
    r = d_inner_m / 2.0
    r_i = r
    resistance = 0.0
    for layer in layers:
        r_o = r + layer.thickness_m
        resistance += r_i * math.log(r_o / r) / layer.material.conductivity
        r = r_o
    resistance += r_i / (r * h_outer)
    return 1.0 / resistance


def equivalent_insulation_thickness(
    u_target: float,
    d_inner_m: float,
    steel_thickness_m: float,
    insulation: Material,
    h_outer: float,
    steel: Material = STEEL,
) -> float:
    """Insulation thickness that reproduces a target inner-basis U with a steel wall, an insulation layer and an outer film.

    Used to turn a screening U-value (SURF basis) into physical wall layers so that wall thermal inertia is represented in a
    cooldown case.  The result is an EQUIVALENT thickness, not a design insulation specification.

    :return: insulation thickness in m
    :raises ValueError: if the target U is unreachable (outer film alone too resistive)
    """
    r_i = d_inner_m / 2.0
    r_s = r_i + steel_thickness_m
    res_target = 1.0 / u_target
    res_steel = r_i * math.log(r_s / r_i) / steel.conductivity
    # unknown outer radius r_c: r_i/k*ln(r_c/r_s) + r_i/(r_c*h) = res_target - res_steel ; solve by bisection
    rest = res_target - res_steel

    def f(r_c: float) -> float:
        return (
            r_i * math.log(r_c / r_s) / insulation.conductivity
            + r_i / (r_c * h_outer)
            - rest
        )

    if f(r_s) > 0:
        raise ValueError(
            "target U is higher than the bare steel wall with the outer film allows"
        )
    lo, hi = r_s, r_s + 2.0
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if f(mid) > 0:
            hi = mid
        else:
            lo = mid
    return 0.5 * (lo + hi) - r_s


# ------------------------------------------------------------------------------------------------ geometry
@dataclass
class RouteProfile:
    """Route polyline: horizontal chainage x (m) and elevation z (m, positive up)."""

    x_m: list[float]
    z_m: list[float]
    name: str = "route"
    meta: dict = field(default_factory=dict)


def load_route_profile(
    path: str | Path, depth_key: str = "depth_m", kp_key: str = "kp_km"
) -> RouteProfile:
    """Read a SURF-style route profile JSON (``kp_km`` list and seabed ``depth_m`` list, depth positive down).

    :return: :class:`RouteProfile` with z = -depth
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    x = [float(v) * 1000.0 for v in data[kp_key]]
    z = [-float(v) for v in data[depth_key]]
    if len(x) != len(z):
        raise ValueError("kp and depth lists have different lengths")
    meta = {k: v for k, v in data.items() if k not in (kp_key, depth_key)}
    return RouteProfile(x, z, name=str(data.get("route", "route")), meta=meta)


def simplify_route(
    x: Sequence[float], z: Sequence[float], tolerance_m: float
) -> tuple[list[float], list[float]]:
    """Ramer-Douglas-Peucker simplification of an elevation profile (vertical tolerance in m).

    Keeps the end points; the maximum vertical deviation of the simplified polyline from the input is <= ``tolerance_m``.
    """
    n = len(x)
    if n < 3 or tolerance_m <= 0:
        return list(x), list(z)
    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        dmax, imax = -1.0, a
        for i in range(a + 1, b):
            zi = z[a] + (z[b] - z[a]) * (x[i] - x[a]) / (x[b] - x[a])
            d = abs(z[i] - zi)
            if d > dmax:
                dmax, imax = d, i
        if dmax > tolerance_m:
            keep[imax] = True
            stack.append((a, imax))
            stack.append((imax, b))
    idx = [i for i in range(n) if keep[i]]
    return [x[i] for i in idx], [z[i] for i in idx]


def build_mesh(
    route: RouteProfile,
    riser_length_m: float,
    riser_rise_m: float,
    target_section_m: float = 250.0,
    riser_section_m: float = 10.0,
    boundary_section_m: float = 20.0,
    simplify_tol_m: float = 0.5,
    max_adjacent_ratio: float = 1.8,
) -> Discretization:
    """Mesh the seabed route and append an inclined riser; seabed pipes are labelled ``SEA_nn`` and the riser ``RIS_01``.

    The riser starts at the end of the seabed profile, has the given LENGTH along the pipe and rises ``riser_rise_m`` (its horizontal
    span follows from the length).  The mesh is graded toward the riser so the neighbour ratio stays within the limit, also when
    the seabed route is a single pipe (two route points, or a straight route after simplification).

    :raises DiscretizationError: if the neighbour ratio of the joined seabed and riser mesh still exceeds ``max_adjacent_ratio``
    """
    x, z = simplify_route(route.x_m, route.z_m, simplify_tol_m)
    boundary_section_m = min(
        boundary_section_m, riser_section_m * max_adjacent_ratio * 0.9
    )  # keep the seabed/riser junction ratio in limit
    sea = discretize_route(
        x,
        z,
        target_section_m,
        min_section_length=5.0,
        max_section_length=2.0 * target_section_m,
        max_adjacent_ratio=max_adjacent_ratio,
        boundary_section_length=boundary_section_m,
        label_prefix="SEA",
    )
    span = math.sqrt(max(riser_length_m**2 - riser_rise_m**2, 0.0))
    x_end, z_end = x[-1], z[-1]
    ris = discretize_route(
        [x_end, x_end + span],
        [z_end, z_end + riser_rise_m],
        riser_section_m,
        min_section_length=2.0,
        max_adjacent_ratio=max_adjacent_ratio,
        label_prefix="RIS",
    )
    mesh = Discretization(list(sea.pipes) + list(ris.pipes))
    # the two parts are meshed separately, so the seabed/riser junction is only checked here
    _enforce_neighbour_ratio(
        [pipe.section_lengths for pipe in mesh.pipes], max_adjacent_ratio, 2.0
    )
    worst = mesh.max_adjacent_ratio
    if worst > max_adjacent_ratio * (1.0 + 1e-6):
        raise DiscretizationError(
            f"neighbour section ratio {worst:.2f} exceeds the limit {max_adjacent_ratio:.2f} "
            f"(target_section_m={target_section_m:g}, riser_section_m={riser_section_m:g}); "
            "use a longer riser section, a shorter seabed target or a higher max_adjacent_ratio"
        )
    return mesh


# ------------------------------------------------------------------------------------------------ case spec
def _lst(vals, fmt="%g"):
    return ", ".join(fmt % v for v in vals)


@dataclass
class FlowlineCaseSpec:
    """Everything needed to render one OLGA genkey for a flowline + riser + topside inlet."""

    name: str
    pvt_file: str
    fluid_label: str
    mesh: Discretization
    diameter_m: float
    roughness_m: float = 4.5e-5
    layers_seabed: Sequence[WallLayer] = ()
    layers_riser: Sequence[WallLayer] = ()
    h_ambient_w_m2k: float = 100.0
    t_ambient_c: float = 6.0
    # source (wells at the template)
    source_times_s: Sequence[float] = (0.0,)
    source_massflow_kg_s: Sequence[float] = (30.0,)
    source_temperature_c: float = 90.0
    gas_fraction_hc: float = (
        0.5  # mass fraction of the HYDROCARBON part (OLGA GASFRACTION with WATERFRACTION)
    )
    water_fraction: float | None = None
    # outlet
    p_outlet_bara: float = 13.0
    p_outlet_times_s: Sequence[float] | None = (
        None  # if given, p_outlet_bara is a list of the same length via p_outlet_series
    )
    p_outlet_series_bara: Sequence[float] | None = None
    t_outlet_c: float = 40.0
    topside_length_m: float = 20.0
    esdv_times_s: Sequence[float] | None = None  # valve opening table (time)
    esdv_opening: Sequence[float] | None = None
    choke_diameter_m: float | None = None  # fixed choke at the riser top (None = none)
    # blowdown valve (second branch from the riser-top node to a flare pressure node)
    bdv_mode: str = (
        "leak"  # "leak": LEAK on the last riser section (robust); "branch": VALVE in a short branch to a flare node
    )
    topology: str = (
        "single"  # "single": topside inlet pipe/ESDV inside the production flowpath; "node": internal node + FP_TOP branch
    )
    bdv_hold_bara: float = (
        150.0  # leak back pressure while the BDV is closed (above any line pressure)
    )
    bdv_diameter_m: float | None = None
    bdv_times_s: Sequence[float] | None = None
    bdv_opening: Sequence[float] | None = None
    p_flare_bara: float = 2.0
    # hydrate
    hydrate_curve_block: str | None = None  # full HYDRATECURVE text block(s)
    hydrate_curve_label: str | None = None
    # run control
    end_time_s: float = 3600.0
    max_dt_s: float = 5.0
    min_dt_s: float = 0.001
    dt_trend_s: float = 10.0
    dt_profile_s: float = 600.0
    steady_state_start: bool = True
    init_pressure_bara: float = 30.0
    init_temperature_c: float = 40.0
    init_voidfraction: float | None = None
    restart_write: str | None = (
        None  # truthy -> RESTART WRITE=APPEND with DTWRITE = restart_dt_s
    )
    restart_read: str | None = None  # .rsw file name (relative to the case directory)
    restart_dt_s: float | None = None
    start_time_s: float | None = (
        0.0  # None -> no STARTTIME (restart: time continues from the restart file)
    )
    pig: dict | None = (
        None  # {"insert_time_s", "mass_kg", "leakage_factor", "static_force_n", "track_slug"}
    )
    extra_global: Sequence[str] = ()
    extra_flowpath: Sequence[str] = ()
    trend_extra: Sequence[str] = ()
    author: str = "NeqSim R4"
    title: str = ""
    shutin: bool = False

    def esdv_table(self) -> tuple[Sequence[float], Sequence[float]]:
        if self.esdv_times_s is None:
            return (0.0,), (1.0,)
        return self.esdv_times_s, self.esdv_opening or (1.0,) * len(self.esdv_times_s)


def wrap_genkey(lines: Sequence[str], width: int = 118) -> str:
    """Wrap long statements with a trailing backslash (OLGA continuation) at ', ' boundaries."""
    out: list[str] = []
    for ln in lines:
        if ln.lstrip().startswith(
            "!"
        ):  # never wrap comments: the tail would become a statement
            out.append(ln)
            continue
        while len(ln) > width:
            cut = ln.rfind(", ", 0, width - 2)
            if cut < 0:
                cut = ln.rfind(",", 0, width - 2)
                if cut < 0:
                    break
                out.append(ln[: cut + 1] + " \\")
                ln = "      " + ln[cut + 1 :].lstrip()
                continue
            out.append(ln[: cut + 1] + " \\")
            ln = "      " + ln[cut + 2 :]
        out.append(ln)
    return "\n".join(out) + "\n"


def _material_lines(
    layers_sets: Sequence[Sequence[WallLayer]],
) -> tuple[list[str], list[str]]:
    mats: dict[str, Material] = {}
    for layers in layers_sets:
        for layer in layers:
            mats[layer.material.label] = layer.material
    lines = [
        f'MATERIAL LABEL="{m.label}", TYPE=SOLID, CAPACITY={m.capacity:g} J/kg-C, CONDUCTIVITY={m.conductivity:g} W/m-C, '
        f"DENSITY={m.density:g} kg/m3"
        for m in mats.values()
    ]
    return list(mats), lines


def render_genkey(spec: FlowlineCaseSpec) -> str:
    """Render the genkey text for ``spec``.

    :return: genkey text ending with a newline
    """
    sea_pipes = [p for p in spec.mesh.pipes if p.label.startswith("SEA")]
    ris_pipes = [p for p in spec.mesh.pipes if p.label.startswith("RIS")]
    if not sea_pipes or not ris_pipes:
        raise ValueError("mesh needs SEA_* and RIS_* pipes (use build_mesh)")
    L: list[str] = [
        f'CASE AUTHOR="{spec.author}", PROJECT="Grimsnes process safety rev B R4", TITLE="{spec.title or spec.name}"',
        "OPTIONS TEMPERATURE=WALL, COMPOSITIONAL=OFF, ELASTICWALL=OFF, DEBUG=OFF, STEADYSTATE=%s"
        % ("ON" if spec.steady_state_start else "OFF"),
        f'FILES PVTFILE="{spec.pvt_file}"',
        "INTEGRATION ENDTIME={:g} s, {}MINDT={:g} s, MAXDT={:g} s, DTSTART={:g} s".format(
            spec.end_time_s,
            "STARTTIME=0 s, " if spec.start_time_s is not None else "",
            spec.min_dt_s,
            spec.max_dt_s,
            max(spec.min_dt_s, 0.01),
        ),
        f"OUTPUT DTOUT={max(spec.end_time_s, 1.0):g} s",
        f"TREND DTPLOT={spec.dt_trend_s:g} s",
        f"PROFILE DTPLOT={spec.dt_profile_s:g} s",
    ]
    if spec.restart_write:
        L.append(
            "RESTART WRITE=APPEND, DTWRITE=%g s"
            % (spec.restart_dt_s or spec.end_time_s)
        )
    if spec.restart_read:
        L.append(f'RESTART READFILE=ON, FILE="{spec.restart_read}"')
    L.extend(spec.extra_global)
    _mats, mat_lines = _material_lines([spec.layers_seabed, spec.layers_riser])
    L.extend(mat_lines)
    for tag, layers in (
        ("WALLSEA", spec.layers_seabed),
        ("WALLRIS", spec.layers_riser),
    ):
        L.append(
            'WALL LABEL="{}", THICKNESS=({}) m, MATERIAL=({})'.format(
                tag,
                _lst([ly.thickness_m for ly in layers], "%.5f"),
                ", ".join(f'"{ly.material.label}"' for ly in layers),
            )
        )
    if spec.hydrate_curve_block:
        L.append(spec.hydrate_curve_block.rstrip())
    L.append("")
    # --- production flowpath
    x0, z0 = sea_pipes[0].x_start, sea_pipes[0].y_start
    L += [
        "NETWORKCOMPONENT TYPE=FLOWPATH, TAG=FP_PROD",
        ' PARAMETERS LABEL="PRODLINE"',
        f' BRANCH FLUID="{spec.fluid_label}"',
        f' GEOMETRY LABEL="ROUTE", XSTART={x0:.3f} m, YSTART={z0:.3f} m, ZSTART=0 m',
    ]
    for p in sea_pipes:
        L.append(p.to_genkey(spec.diameter_m, spec.roughness_m, "WALLSEA"))
    for p in ris_pipes:
        L.append(p.to_genkey(spec.diameter_m, spec.roughness_m, "WALLRIS"))
    single = spec.topology == "single" and not (
        spec.bdv_diameter_m and spec.bdv_mode == "branch"
    )
    xs, zs = ris_pipes[-1].x_end, ris_pipes[-1].y_end
    xsep = xs + spec.topside_length_m
    if (
        single
    ):  # topside inlet pipe, ESDV and optional choke inside the production flowpath: no internal node
        top = PipeSegment("TOP_01", xs, zs, xsep, zs, [spec.topside_length_m / 4.0] * 4)
        L.append(top.to_genkey(spec.diameter_m, spec.roughness_m, "WALLRIS"))
    sea_labels = ", ".join(p.label for p in sea_pipes)
    L.append(
        f' HEATTRANSFER LABEL="SEABED", PIPE=({sea_labels}), HOUTEROPTION=HGIVEN, HAMBIENT={spec.h_ambient_w_m2k:g} W/m2-C, TAMBIENT={spec.t_ambient_c:g} C, HMININNERWALL=10 W/m2-C'
    )
    L.append(
        ' HEATTRANSFER LABEL="RISERWATER", PIPE=({}), HOUTEROPTION=HGIVEN, HAMBIENT={:g} W/m2-C, TAMBIENT={:g} C, HMININNERWALL=10 W/m2-C'.format(
            ", ".join(p.label for p in ris_pipes),
            spec.h_ambient_w_m2k,
            spec.t_ambient_c,
        )
    )
    if single:
        L.append(
            ' HEATTRANSFER LABEL="TOPHT", PIPE=(TOP_01), HOUTEROPTION=HGIVEN, HAMBIENT=5 W/m2-C, TAMBIENT=10 C, HMININNERWALL=10 W/m2-C'
        )
        et, eo = spec.esdv_table()
        L.append(
            f' VALVE LABEL="ESDV", PIPE=TOP_01, SECTIONBOUNDARY=1, DIAMETER={spec.diameter_m:.4f} m, CD=0.84, TIME=({_lst(et)}) s, OPENING=({_lst(eo)}) -'
        )
        if spec.choke_diameter_m:
            L.append(
                f' VALVE LABEL="CHOKE", PIPE=TOP_01, SECTIONBOUNDARY=3, DIAMETER={spec.choke_diameter_m:.4f} m, CD=0.84, TIME=0 s, OPENING=1 -'
            )
    n = len(spec.source_times_s)
    src = ' SOURCE LABEL="WELLS", PIPE={}, SECTION=1, TIME=({}) s, MASSFLOW=({}) kg/s, TEMPERATURE=({}) C, GASFRACTION=({}) -'.format(
        sea_pipes[0].label,
        _lst(spec.source_times_s),
        _lst(spec.source_massflow_kg_s, "%.4f"),
        _lst([spec.source_temperature_c] * n),
        _lst([spec.gas_fraction_hc] * n, "%.6f"),
    )
    if spec.water_fraction is not None:
        src += ", WATERFRACTION=({}) -".format(_lst([spec.water_fraction] * n, "%.6f"))
    L.append(src)
    ic = f" INITIALCONDITIONS PRESSURE={spec.init_pressure_bara:g} bara, TEMPERATURE={spec.init_temperature_c:g} C"
    if spec.init_voidfraction is not None:
        ic += f", VOIDFRACTION={spec.init_voidfraction:g} -"
    L.append(ic)
    if spec.hydrate_curve_label:
        L.append(f' HYDRATECHECK HYDRATECURVE="{spec.hydrate_curve_label}"')
        hyd = ", DTHYD"
    else:
        hyd = ""
    if spec.shutin:
        L.append(" SHUTIN ACTIVATE=AUTOMATIC, TIME=0 s")
    if spec.pig:
        pg = spec.pig
        L.append(
            f' POSITION LABEL="PIGLAUNCH", PIPE={sea_pipes[0].label}, SECTIONBOUNDARY=1'
        )
        L.append(
            ' PIG LABEL="PIG1", LAUNCHPOSITION="PIGLAUNCH", INSERTTIME={:g} s, MASS={:g} kg, STATICFORCE={:g} N, LEAKAGEFACTOR={:g} -, TRACKSLUG={}'.format(
                pg.get("insert_time_s", 0.0),
                pg.get("mass_kg", 140.0),
                pg.get("static_force_n", 1000.0),
                pg.get("leakage_factor", 0.0),
                "ON" if pg.get("track_slug") else "OFF",
            )
        )
    if spec.bdv_diameter_m and spec.bdv_mode == "leak":
        # blowdown as a LEAK on the riser-top section: back pressure sits ABOVE any line pressure (check valve closed) until the
        # opening time, then falls to the flare pressure; opening times/openings are read from bdv_times_s/bdv_opening (first t with opening>0)
        bt = list(spec.bdv_times_s or (0.0,))
        bo = list(spec.bdv_opening or (0.0,))
        i_pos = next((i for i, o_ in enumerate(bo) if o_ > 0.0), len(bo) - 1)
        t_open = bt[
            max(i_pos - 1, 0)
        ]  # start of the opening ramp = last closed point before the first opening
        stroke = max(bt[i_pos] - t_open, 1.0)
        L.append(
            ' LEAK LABEL="BDV", PIPE=%s, SECTION=%d, DIAMETER=%.4f m, CD=0.84, TIME=(0, %g, %g) s, '  # noqa: UP031
            "BACKPRESSURE=(%g, %g, %g) bara"
            % (
                ris_pipes[-1].label,
                ris_pipes[-1].nsegments,
                spec.bdv_diameter_m,
                t_open,
                t_open + stroke,
                spec.bdv_hold_bara,
                spec.bdv_hold_bara,
                spec.p_flare_bara,
            )
        )
    L.extend(spec.extra_flowpath)
    prof = "PT, TM, HOL, ID, UG, UL, USG, USL, ROG, ROHL, GT, GG, GLT" + hyd
    L.append(f" PROFILEDATA VARIABLE=({prof})")
    L.append(f" OUTPUTDATA VARIABLE=(PT, TM, HOL, GT, GG, GLT{hyd})")
    first = sea_pipes[0].label
    rtop = ris_pipes[-1].label
    ntop = ris_pipes[-1].nsegments
    last_sea = sea_pipes[-1].label
    nlast_sea = sea_pipes[-1].nsegments
    tv = f"PT, TM, HOL, GT, GG, GLT, QLT, USG, USL{hyd}"
    L.append(f" TRENDDATA PIPE={first}, SECTION=1, VARIABLE=({tv})")
    L.append(f" TRENDDATA PIPE={last_sea}, SECTION={nlast_sea}, VARIABLE=({tv})")
    L.append(
        f" TRENDDATA PIPE={rtop}, SECTION={ntop}, VARIABLE=({tv}{', ' + ', '.join(spec.trend_extra) if spec.trend_extra else ''})"
    )
    if single:
        L.append(
            " TRENDDATA PIPE=TOP_01, SECTION=1, VARIABLE=(PT, TM, HOL, GT, GG, GLT, QLT, USG, USL)"
        )
        L.append(
            " TRENDDATA PIPE=TOP_01, SECTION=4, VARIABLE=(PT, TM, HOL, GT, GG, GLT)"
        )
    L.append(" TRENDDATA VARIABLE=(LIQC, GASC)")
    if spec.bdv_diameter_m and spec.bdv_mode == "leak":
        L.append(" TRENDDATA VARIABLE=(GTLEAK, GGLEAK, GLLEAK, TLEAK, TLEAEX, PTLKUP)")
    L.append("ENDNETWORKCOMPONENT")
    L.append("")
    # --- topside inlet branch (ESDV, optional choke) to separator pressure node (node topology only)
    if not single:
        L += [
            "NETWORKCOMPONENT TYPE=FLOWPATH, TAG=FP_TOP",
            ' PARAMETERS LABEL="TOPSIDE"',
            f' BRANCH FLUID="{spec.fluid_label}"',
            f' GEOMETRY LABEL="TOPGEO", XSTART={xs:.3f} m, YSTART={zs:.3f} m, ZSTART=0 m',
            ' PIPE LABEL=TOP_01, ROUGHNESS={:.6e} m, DIAMETER={:.4f} m, WALL="WALLRIS", NSEGMENT=4, LSEGMENT=({}) m, XEND={:.3f} m, YEND={:.3f} m, ZEND=0 m'.format(
                spec.roughness_m,
                spec.diameter_m,
                _lst([spec.topside_length_m / 4.0] * 4, "%.4f"),
                xsep,
                zs,
            ),
            ' HEATTRANSFER LABEL="TOPHT", PIPE=ALL, HOUTEROPTION=HGIVEN, HAMBIENT=5 W/m2-C, TAMBIENT=10 C, HMININNERWALL=10 W/m2-C',
        ]
        et, eo = spec.esdv_table()
        L.append(
            f' VALVE LABEL="ESDV", PIPE=TOP_01, SECTIONBOUNDARY=1, DIAMETER={spec.diameter_m:.4f} m, CD=0.84, TIME=({_lst(et)}) s, OPENING=({_lst(eo)}) -'
        )
        if spec.choke_diameter_m:
            L.append(
                f' VALVE LABEL="CHOKE", PIPE=TOP_01, SECTIONBOUNDARY=3, DIAMETER={spec.choke_diameter_m:.4f} m, CD=0.84, TIME=0 s, OPENING=1 -'
            )
        L += [
            f" INITIALCONDITIONS PRESSURE={spec.p_outlet_bara:g} bara, TEMPERATURE={spec.init_temperature_c:g} C",
            " TRENDDATA PIPE=TOP_01, SECTION=1, VARIABLE=(PT, TM, HOL, GT, GG, GLT, QLT, USG, USL)",
            " TRENDDATA PIPE=TOP_01, SECTION=4, VARIABLE=(PT, TM, HOL, GT, GG, GLT)",
            "ENDNETWORKCOMPONENT",
            "",
        ]
    # --- blowdown branch
    bdv_branch = bool(spec.bdv_diameter_m and spec.bdv_mode == "branch")
    if bdv_branch:
        L += [
            "NETWORKCOMPONENT TYPE=FLOWPATH, TAG=FP_BDV",
            ' PARAMETERS LABEL="BDVLINE"',
            f' BRANCH FLUID="{spec.fluid_label}"',
            f' GEOMETRY LABEL="BDVGEO", XSTART={xs:.3f} m, YSTART={zs:.3f} m, ZSTART=0 m',
            f' PIPE LABEL=BDV_01, ROUGHNESS={spec.roughness_m:.6e} m, DIAMETER={spec.diameter_m:.4f} m, WALL="WALLRIS", NSEGMENT=2, LSEGMENT=(2.5, 2.5) m, XEND={xs + 5.0:.3f} m, YEND={zs:.3f} m, ZEND=0 m',
            ' HEATTRANSFER LABEL="BDVHT", PIPE=ALL, HOUTEROPTION=HGIVEN, HAMBIENT=5 W/m2-C, TAMBIENT=10 C, HMININNERWALL=10 W/m2-C',
            f' VALVE LABEL="BDV", PIPE=BDV_01, SECTIONBOUNDARY=1, DIAMETER={spec.bdv_diameter_m:.4f} m, CD=0.84, TIME=({_lst(spec.bdv_times_s or (0.0,))}) s, OPENING=({_lst(spec.bdv_opening or (0.0,))}) -',
            f" INITIALCONDITIONS PRESSURE={spec.p_flare_bara:g} bara, TEMPERATURE=10 C",
            " TRENDDATA PIPE=BDV_01, SECTION=1, VARIABLE=(PT, TM, GT, GG, GLT)",
            " TRENDDATA PIPE=BDV_01, SECTION=2, VARIABLE=(PT, TM, GT, GG, GLT)",
            "ENDNETWORKCOMPONENT",
            "",
        ]
    # --- nodes
    L += [
        "NETWORKCOMPONENT TYPE=NODE, TAG=NODE_IN",
        f' PARAMETERS LABEL="TEMPLATE", TYPE=CLOSED, X={x0:.3f} m, Y={z0:.3f} m, Z=0 m',
        "ENDNETWORKCOMPONENT",
        "",
    ]
    if not single:
        L += [
            "NETWORKCOMPONENT TYPE=NODE, TAG=NODE_TOP",
            f' PARAMETERS LABEL="RISERTOP", TYPE=INTERNAL, X={xs:.3f} m, Y={zs:.3f} m, Z=0 m, FLUID="{spec.fluid_label}"',
            "ENDNETWORKCOMPONENT",
            "",
        ]
    if spec.p_outlet_series_bara and spec.p_outlet_times_s:
        pr = f"PRESSURE=({_lst(spec.p_outlet_series_bara)}) bara, TIME=({_lst(spec.p_outlet_times_s)}) s"
    else:
        pr = f"PRESSURE={spec.p_outlet_bara:g} bara"
    # separator boundary: back-flow (riser-top pressure below the host pressure) is GAS from the separator gas space, not the table-equilibrium liquid
    pr += ", GASFRACTION=1 -" + (
        ", WATERFRACTION=0 -" if spec.water_fraction is not None else ""
    )
    L += [
        "NETWORKCOMPONENT TYPE=NODE, TAG=NODE_SEP",
        (
            f' PARAMETERS LABEL="SEPARATOR", TYPE=PRESSURE, X={xsep:.3f} m, Y={zs:.3f} m, Z=0 m, {pr}, '
            f'TEMPERATURE={spec.t_outlet_c:g} C, FLUID="{spec.fluid_label}"'
        ),
        "ENDNETWORKCOMPONENT",
        "",
    ]
    if bdv_branch:
        L += [
            "NETWORKCOMPONENT TYPE=NODE, TAG=NODE_FLARE",
            (
                f' PARAMETERS LABEL="FLARE", TYPE=PRESSURE, X={xs + 5.0:.3f} m, Y={zs:.3f} m, Z=0 m, PRESSURE={spec.p_flare_bara:g} bara, '
                f'TEMPERATURE=10 C, FLUID="{spec.fluid_label}"'
            ),
            "ENDNETWORKCOMPONENT",
            "",
        ]
    if single:
        L += [
            "CONNECTION TERMINALS = (NODE_IN FLOWTERM_1, FP_PROD INLET)",
            "CONNECTION TERMINALS = (NODE_SEP FLOWTERM_1, FP_PROD OUTLET)",
        ]
    else:
        L += [
            "CONNECTION TERMINALS = (NODE_IN FLOWTERM_1, FP_PROD INLET)",
            "CONNECTION TERMINALS = (NODE_TOP FLOWTERM_1, FP_PROD OUTLET)",
            "CONNECTION TERMINALS = (NODE_TOP FLOWTERM_2, FP_TOP INLET)",
            "CONNECTION TERMINALS = (NODE_SEP FLOWTERM_1, FP_TOP OUTLET)",
        ]
    if bdv_branch:
        L += [
            "CONNECTION TERMINALS = (NODE_TOP FLOWTERM_3, FP_BDV INLET)",
            "CONNECTION TERMINALS = (NODE_FLARE FLOWTERM_1, FP_BDV OUTLET)",
        ]
    L += ["", "ENDCASE"]
    return wrap_genkey(L)
