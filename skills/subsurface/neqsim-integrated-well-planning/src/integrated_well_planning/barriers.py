"""Proposed well-barrier schematics per well state (data model).

The elements, envelopes and functions follow the common primary/secondary barrier-envelope idea used in well-integrity
practice. This module proposes an arrangement from the completion description; it does NOT state acceptance criteria,
element lengths or compliance. Every element starts ``UNVERIFIED`` with the verification evidence still to be supplied
and its unresolved dependencies listed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .registers import get_path

STATES = ("production", "shut_in", "injection", "intervention", "abandonment")
ENVELOPES = ("primary", "secondary")
VERIFICATION_STATUS = ("UNVERIFIED", "PLANNED", "VERIFIED", "NOT_APPLICABLE")


@dataclass
class BarrierElement:
    """One barrier element (e.g. production packer, tubing, safety valve, casing cement)."""

    id: str
    name: str
    envelope: str
    function: str
    depth_md_m: Optional[float] = None
    verification_method: str = "to be defined against the verified barrier-element acceptance table"
    verification_status: str = "UNVERIFIED"
    evidence: str = ""
    depends_on: List[str] = field(default_factory=list)
    unresolved: List[str] = field(default_factory=list)


@dataclass
class BarrierState:
    """The barrier arrangement of one well state."""

    state: str
    description: str
    elements: List[BarrierElement]
    notes: List[str] = field(default_factory=list)


def _e(i, name, env, fn, depth=None, deps=None, unresolved=None, method=None):
    return BarrierElement(i, name, env, fn, depth, depends_on=list(deps or []), unresolved=list(unresolved or []),
                          **({"verification_method": method} if method else {}))


def propose_barriers(basis: Dict[str, Any]) -> List[BarrierState]:
    """Propose barrier schematics for producer or injector wells from the completion description."""
    comp = get_path(basis, "completion") or {}
    env = get_path(basis, "well.environment")
    wtype = get_path(basis, "well.type")
    packer = comp.get("packer_md_m")
    sssv = comp.get("sssv_md_m")
    casing = comp.get("casing", [])
    prod_csg = [c for c in casing if "production" in c["name"].lower()]
    shoe = prod_csg[-1]["shoe_md_m"] if prod_csg else None
    top_cement = prod_csg[-1].get("cement_top_md_m") if prod_csg else None
    tree = comp.get("tree", "tree (type to be defined)")
    injector = wtype in ("water_injector", "gas_injector")
    surface_valve = "subsea tree valves (master/wing, actuated)" if env == "subsea" else "surface tree master and wing valves"
    td = "tubing"

    common_secondary = [
        _e("S1", "Production casing and cement", "secondary", "contain wellbore pressure outside the tubing", shoe, ["casing cement top"],
           ["cement quality and top of cement evidence (logs/pressure tests) to be supplied"]),
        _e("S2", "Wellhead and annulus-A access valves (tree/wellhead seals)", "secondary", "seal the annulus at surface/seabed", None, [], ["wellhead pressure-test records to be supplied"]),
        _e("S3", "Casing hanger seal assembly", "secondary", "seal between casing and wellhead", None, [], ["seal-assembly qualification to be supplied"]),
    ]
    states: List[BarrierState] = []

    def prim(shut=False):
        els = [
            _e("P1", "Production packer", "primary", "seal annulus A from the reservoir", packer, [], ["packer setting and pressure-test evidence to be supplied"]),
            _e("P2", "Tubing string (completion tubing)", "primary", "contain wellstream/injectate to surface", comp.get("tubing", {}).get("shoe_md_m"), ["P1"],
               ["tubing integrity (pressure/leak test) to be supplied"]),
            _e("P3", "Downhole safety valve (SSSV/DHSV)", "primary", "isolate the tubing from the reservoir on demand", sssv, ["control line"],
               ["valve function and leak-rate test to be defined by the operator"]),
            _e("P4", surface_valve, "primary", "isolate flow at the tree", None, [], ["valve test records to be supplied"]),
        ]
        if injector:
            els.insert(2, _e("P2b", "Non-return/check valve or injection isolation (if fitted)", "primary", "prevent backflow", None, [], ["decide whether a check valve is used (operator practice)"]))
        return els

    states.append(BarrierState("production" if not injector else "injection", "Normal {} through the tubing".format("injection" if injector else "production"), prim() + common_secondary,
                               ["annulus-A pressure monitoring is the in-service verification of the secondary envelope (limit to be supplied)"]))
    states.append(BarrierState("shut_in", "Well shut in at the tree; reservoir pressure above the packer/DHSV", prim(True) + common_secondary,
                               ["shut-in tubing head pressure from the integrity block must be within the tree rating (see envelope)"]))
    interv = [
        _e("P1", "Production packer and tubing", "primary", "seal annulus and contain pressure", packer, [], ["tubing/packer test"]),
        _e("P3", "Downhole safety valve (closed)", "primary", "isolate reservoir during intervention", sssv, [], ["valve test"]),
        _e("P5", "Lubricator / riser and pressure-control equipment (wireline or coiled tubing)", "primary", "contain pressure at the surface/seabed during intervention", None, [],
           ["pressure-control equipment selection and test (operator procedure)"]),
        _e("S4", "Tree and wellhead (secondary)", "secondary", "back-up containment", None, [], ["test records"]),
    ]
    states.append(BarrierState("intervention", "Wireline/coiled-tubing or light-intervention operation", interv,
                               ["subsea intervention needs a riser/lubricator arrangement (system selection is an open interface)"] if env == "subsea" else []))
    aband = [
        _e("A1", "Primary reservoir plug (cement or approved alternative)", "primary", "permanent isolation of the reservoir", None, [],
           ["plug length, placement, verification and position are NOT specified here: use the verified standard/regulation"]),
        _e("A2", "Secondary plug / cemented casing annulus", "secondary", "back-up permanent isolation", top_cement, [], ["cement evidence (logs) to be supplied"]),
        _e("A3", "Surface/seabed plug and wellhead removal plan", "secondary", "final isolation at the top", None, [], ["jurisdiction requirement to be identified"]),
    ]
    states.append(BarrierState("abandonment", "Permanent abandonment (placeholder arrangement)", aband,
                               ["abandonment requirements for this jurisdiction are not identified in the basis: arrangement is a placeholder"]))
    return states


def barrier_summary(states: List[BarrierState]) -> Dict[str, Any]:
    """Counts of elements by verification status and open dependencies."""
    counts: Dict[str, int] = {}
    unresolved = 0
    for s in states:
        for e in s.elements:
            counts[e.verification_status] = counts.get(e.verification_status, 0) + 1
            unresolved += len(e.unresolved)
    return {"elements_by_status": counts, "unresolved_items": unresolved, "compliance_statement": "NONE - elements are proposed and UNVERIFIED"}


def to_rows(states: List[BarrierState]) -> List[Dict[str, Any]]:
    """Flatten the barrier states for tables."""
    rows = []
    for s in states:
        for e in s.elements:
            d = asdict(e)
            d["state"] = s.state
            rows.append(d)
    return rows


def set_verification(states: List[BarrierState], element_id: str, state: str, status: str, evidence: str) -> None:
    """Record verification evidence for one element in one state.

    Raises:
        ValueError: for an unknown status or VERIFIED without evidence.
        KeyError: when the element is not found.
    """
    if status not in VERIFICATION_STATUS:
        raise ValueError("status must be one of {}".format(VERIFICATION_STATUS))
    if status == "VERIFIED" and not evidence:
        raise ValueError("VERIFIED needs an evidence reference")
    for s in states:
        if s.state == state:
            for e in s.elements:
                if e.id == element_id:
                    e.verification_status, e.evidence = status, evidence
                    return
    raise KeyError((state, element_id))
