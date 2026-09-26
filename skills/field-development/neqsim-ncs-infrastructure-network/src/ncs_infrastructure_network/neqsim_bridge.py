"""Hand-offs from the NCS network to NeqSim Java classes.

Two layers, so everything is testable without a JVM:

* ``*_spec`` functions return plain dicts (inputs for NeqSim), no Java needed.
* ``build_*`` / ``run_*`` functions import ``neqsim`` lazily and instantiate
  the Java classes:

  - ``neqsim.process.fielddevelopment.tieback.HostFacility`` / ``TiebackAnalyzer``
    - screen a discovery against the nearest real NCS hosts (distance, CAPEX, NPV).
  - ``neqsim.process.equipment.network.LoopedPipeNetwork`` - hydraulic check of an
    export trunkline path (inlet pressure needed to move a rate to the terminal).

Only the public Python ``neqsim`` package is needed (``pip install neqsim``).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .network import NcsNetwork

SM3_OE_TO_BOE = 6.2898
INCH_TO_M = 0.0254
DEFAULT_WALL_M = 0.028  # screening wall thickness for large-bore trunklines
LEAN_GAS = {"methane": 0.90, "ethane": 0.055, "propane": 0.02, "nitrogen": 0.01, "CO2": 0.015}

_FACILITY_TYPES = {"FPSO": "FPSO", "SEMISUB": "SEMI_SUB", "SEMI": "SEMI_SUB", "TLP": "TLP", "SPAR": "SPAR"}


def _jneqsim():
    try:
        from neqsim import jneqsim  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError("the NeqSim Python package is required: pip install neqsim") from exc
    return jneqsim


# --------------------------------------------------------------------------- specs

def host_facility_spec(host: Dict[str, Any], *, gas_capacity_msm3d: Optional[float] = None,
                       gas_utilization: Optional[float] = None, oil_capacity_bopd: Optional[float] = None,
                       oil_utilization: Optional[float] = None) -> Dict[str, Any]:
    """HostFacility.builder inputs for an NCS host. Capacities are NOT open data - pass them in."""
    kind = str(host.get("kind") or "").upper().replace(" ", "")
    ftype = next((v for k, v in _FACILITY_TYPES.items() if k in kind), "PLATFORM")
    return {
        "name": host["name"], "operator": host.get("operator"), "type": ftype,
        "lat": host["lat"], "lon": host["lon"], "water_depth_m": host.get("water_depth_m") or 100.0,
        "gas_capacity_msm3d": gas_capacity_msm3d, "gas_utilization": gas_utilization,
        "oil_capacity_bopd": oil_capacity_bopd, "oil_utilization": oil_utilization,
        "field_id": host.get("field_id"),
        "capacity_basis": "caller supplied" if gas_capacity_msm3d or oil_capacity_bopd else "unknown (open data)",
    }


def tieback_screen_spec(network: NcsNetwork, discovery: str, *, n_hosts: int = 5,
                        max_km: float = 150.0) -> Dict[str, Any]:
    """Everything TiebackAnalyzer.quickScreen needs for one discovery, plus the host's export route."""
    did = network.resolve(discovery)
    disc = network.discoveries.get(did) or network.fields.get(did)
    if disc is None:
        raise KeyError(f"{discovery!r} is neither a discovery nor a field")
    reserves = disc.get("reserves", {})
    oe = reserves.get("oe_msm3") or reserves.get("remaining_oe_msm3") or 0.0
    hosts = network.nearest_hosts(did, n=n_hosts, max_km=max_km)
    spec_hosts = []
    for host in hosts:
        route = network.export_routes(host["field_id"]) if host.get("field_id") in network.nodes else None
        spec_hosts.append({**host_facility_spec(host), "distance_km": host["distance_km"],
                           "gas_export_exit": (route or {}).get("routes", {}).get("gas", [{}])[0].get("exit")
                           if route and route["routes"].get("gas") else None,
                           "gas_route_bottleneck": (route or {}).get("routes", {}).get("gas", [{}])[0].get(
                               "bottleneck_arc") if route and route["routes"].get("gas") else None})
    return {"discovery": did, "name": disc.get("name"), "lat": disc.get("lat"), "lon": disc.get("lon"),
            "status": disc.get("status"), "rc": reserves.get("rc"),
            "reserves_mmboe": round(oe * SM3_OE_TO_BOE, 2), "water_depth_m": spec_hosts[0]["water_depth_m"]
            if spec_hosts else 100.0, "hosts": spec_hosts, "source_url": disc.get("source_url")}


def trunk_hydraulics_spec(network: NcsNetwork, field: str, *, path_index: int = 0,
                          rate_msm3d: Optional[float] = None, terminal_pressure_bar: float = 100.0,
                          wall_m: float = DEFAULT_WALL_M) -> Dict[str, Any]:
    """Pipe list for a field's gas export path, from table diameters and lengths."""
    paths = network.export_paths(field, "gas")
    if not paths:
        raise ValueError(f"no gas export path for {field!r}")
    path = paths[min(path_index, len(paths) - 1)]
    pipes = []
    for arc_id in path.arcs:
        arc = network.arcs[arc_id]
        if arc.get("length_km") and arc.get("diameter_in"):
            pipes.append({"id": arc_id, "name": arc.get("name"), "from": arc["from"], "to": arc["to"],
                          "length_m": float(arc["length_km"]) * 1000.0,
                          "inner_diameter_m": float(arc["diameter_in"]) * INCH_TO_M - 2 * wall_m,
                          "capacity_msm3d": arc.get("capacity")})
    if not pipes:
        raise ValueError(f"path {path.nodes} has no pipes with length and diameter")
    caps = [p["capacity_msm3d"] for p in pipes if p["capacity_msm3d"]]
    rate = rate_msm3d if rate_msm3d is not None else (min(caps) if caps else 10.0)
    return {"field": network.resolve(field), "path": path.nodes, "pipes": pipes, "rate_msm3d": rate,
            "terminal_pressure_bar": terminal_pressure_bar, "fluid": dict(LEAN_GAS),
            "basis": "screening: ID = OD - 2 x wall, lean gas, isothermal Darcy-Weisbach network"}


# --------------------------------------------------------------------------- NeqSim

def build_host_facility(spec: Dict[str, Any]):
    """Instantiate neqsim HostFacility from ``host_facility_spec``."""
    j = _jneqsim()
    tieback = j.process.fielddevelopment.tieback
    b = tieback.HostFacility.builder(spec["name"])
    if spec.get("operator"):
        b = b.operator(spec["operator"])
    b = b.type(getattr(tieback.HostFacility.FacilityType, spec.get("type", "PLATFORM")))
    b = b.location(float(spec["lat"]), float(spec["lon"])).waterDepth(float(spec["water_depth_m"]))
    if spec.get("gas_capacity_msm3d"):
        b = b.gasCapacity(float(spec["gas_capacity_msm3d"]))
        if spec.get("gas_utilization") is not None:
            b = b.gasUtilization(float(spec["gas_utilization"]))
    if spec.get("oil_capacity_bopd"):
        b = b.oilCapacity(float(spec["oil_capacity_bopd"]))
        if spec.get("oil_utilization") is not None:
            b = b.oilUtilization(float(spec["oil_utilization"]))
    return b.build()


def run_tieback_screening(spec: Dict[str, Any], *, gas_price_usd_per_sm3: Optional[float] = None,
                          oil_price_usd_per_bbl: Optional[float] = None, discount_rate: Optional[float] = None,
                          max_distance_km: Optional[float] = None) -> List[Dict[str, Any]]:
    """Run TiebackAnalyzer.quickScreen for every host in a ``tieback_screen_spec``."""
    j = _jneqsim()
    analyzer = j.process.fielddevelopment.tieback.TiebackAnalyzer()
    if gas_price_usd_per_sm3 is not None:
        analyzer.setGasPriceUsdPerSm3(float(gas_price_usd_per_sm3))
    if oil_price_usd_per_bbl is not None:
        analyzer.setOilPriceUsdPerBbl(float(oil_price_usd_per_bbl))
    if discount_rate is not None:
        analyzer.setDiscountRate(float(discount_rate))
    if max_distance_km is not None:
        analyzer.setMaxTiebackDistanceKm(float(max_distance_km))
    out = []
    for host_spec in spec["hosts"]:
        host = build_host_facility(host_spec)
        result = analyzer.quickScreen(float(spec["lat"]), float(spec["lon"]), float(spec["reserves_mmboe"]),
                                      float(spec["water_depth_m"]), host)
        out.append({"host": str(result.getHostName()), "passed": bool(result.isPassed()),
                    "failure_reason": None if result.isPassed() else str(result.getFailureReason()),
                    "distance_km": float(result.getDistanceKm()),
                    "capex_musd": float(result.getEstimatedCapexMusd()),
                    "npv_musd": float(result.getEstimatedNpvMusd()),
                    "gas_export_exit": host_spec.get("gas_export_exit"),
                    "gas_route_bottleneck": host_spec.get("gas_route_bottleneck"),
                    "neqsim_class": "neqsim.process.fielddevelopment.tieback.TiebackAnalyzer"})
    out.sort(key=lambda r: (not r["passed"], -r["npv_musd"]))
    return out


def _solve_path(j, fluid, spec: Dict[str, Any], inlet_bar: float):
    """Pressure-pressure LoopedPipeNetwork solve; returns (network, mass flow kg/hr)."""
    net = j.process.equipment.network.LoopedPipeNetwork("ncs-export-path")
    net.setFluidTemplate(fluid)
    net.setSolverType(j.process.equipment.network.LoopedPipeNetwork.SolverType.NEWTON_RAPHSON)
    net.setMaxIterations(200)
    net.setTolerance(500.0)
    pipes = spec["pipes"]
    first, last = pipes[0]["from"], pipes[-1]["to"]
    net.addSourceNode(first, float(inlet_bar), 0.0)
    seen = {first, last}
    for p in pipes:
        for node in (p["from"], p["to"]):
            if node not in seen:
                net.addJunctionNode(node)
                seen.add(node)
    net.addFixedPressureSinkNode(last, float(spec["terminal_pressure_bar"]))
    for p in pipes:
        net.addPipe(p["from"], p["to"], p["id"], float(p["length_m"]), float(p["inner_diameter_m"]))
    net.run(_uuid())
    return net, float(net.getPipeFlowRate(pipes[-1]["id"]))


def run_trunk_hydraulics(spec: Dict[str, Any], *, inlet_pressure_bar: Optional[float] = None,
                         max_inlet_bar: float = 250.0, iterations: int = 30) -> Dict[str, Any]:
    """Hydraulic check of an export path with NeqSim ``LoopedPipeNetwork``.

    With ``inlet_pressure_bar`` the network is solved pressure-pressure and the
    deliverable rate is returned. Without it, the inlet pressure needed to move
    ``spec['rate_msm3d']`` to the terminal pressure is found by bisection
    (each step is a full NeqSim network solve).
    """
    j = _jneqsim()
    fluid = j.thermo.system.SystemSrkEos(273.15 + 15.0, 1.01325)
    for comp, frac in spec["fluid"].items():
        fluid.addComponent(comp, float(frac))
    fluid.setMixingRule("classic")
    j.thermodynamicoperations.ThermodynamicOperations(fluid).TPflash()
    fluid.initProperties()
    std_density = float(fluid.getDensity("kg/m3"))
    fluid.setTemperature(273.15 + 8.0)
    fluid.setPressure(float(spec["terminal_pressure_bar"]) + 20.0)

    def to_msm3d(kg_hr: float) -> float:
        return kg_hr * 24.0 / std_density / 1.0e6

    if inlet_pressure_bar is not None:
        net, flow = _solve_path(j, fluid, spec, inlet_pressure_bar)
        inlet = inlet_pressure_bar
    else:
        target = spec["rate_msm3d"]
        lo, hi = float(spec["terminal_pressure_bar"]) + 0.5, max_inlet_bar
        net, flow = _solve_path(j, fluid, spec, hi)
        if to_msm3d(flow) < target:
            inlet = hi  # not deliverable within max_inlet_bar
        else:
            for _ in range(iterations):
                mid = 0.5 * (lo + hi)
                net, flow = _solve_path(j, fluid, spec, mid)
                if to_msm3d(flow) >= target:
                    hi = mid
                else:
                    lo = mid
                if hi - lo < 0.2:
                    break
            inlet = hi
            net, flow = _solve_path(j, fluid, spec, inlet)
    names = [spec["pipes"][0]["from"]] + [p["to"] for p in spec["pipes"]]
    rate = to_msm3d(flow)
    return {"target_rate_msm3d": spec.get("rate_msm3d"), "deliverable_rate_msm3d": round(rate, 3),
            "inlet_pressure_bar": round(inlet, 2), "terminal_pressure_bar": spec["terminal_pressure_bar"],
            "deliverable": inlet_pressure_bar is not None or rate >= spec["rate_msm3d"] * 0.999,
            "node_pressure_bar": {n: round(float(net.getNodePressure(n)), 2) for n in names},
            "pipe_velocity_m_s": {p["id"]: round(float(net.getPipeVelocity(p["id"])), 2) for p in spec["pipes"]},
            "converged": bool(net.isConverged()), "std_density_kg_sm3": round(std_density, 4),
            "path": spec["path"], "basis": spec.get("basis"),
            "neqsim_class": "neqsim.process.equipment.network.LoopedPipeNetwork"}


def _uuid():  # pragma: no cover - JVM helper
    import jpype

    return jpype.JClass("java.util.UUID").randomUUID()
