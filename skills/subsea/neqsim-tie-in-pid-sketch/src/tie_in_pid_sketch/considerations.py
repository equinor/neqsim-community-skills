"""Checklist of subsea tie-in design considerations and a register that records the status of each in a project.

The list is deliberately generic (any subsea tie-back to an existing host). A study fills in the status, the evidence and
the action for each item with :func:`considerations_register`; an item that nobody addressed stays ``OPEN`` and is shown as
a gap, never as "not needed". Generic standards are named as pointers only: check the edition and the project's own
requirements before citing one.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

STATUSES = ("ADDRESSED", "SCREENED", "OPEN", "NOT_APPLICABLE")

CATEGORIES = {
    "W": "Reservoir and wells",
    "S": "Subsea production system",
    "F": "Flowline and riser",
    "H": "Host interface",
    "A": "Flow assurance",
    "O": "Operations and safety",
    "I": "Installation and hook-up",
    "L": "Integrity and life",
    "E": "Environment and third parties",
    "X": "Interfaces and evidence",
}

# id, topic, question to answer, why it matters, evidence normally needed, pointer
_ITEMS = [
    ("W1", "Shut-in pressure against line design pressure", "Is the shut-in tubing head pressure of the highest-pressure well above the flowline and riser design pressure?",
     "Decides between a design pressure that covers the shut-in pressure and an instrumented overpressure protection system (HIPPS) with the valves, voting and testing that follow.",
     "Static column calculation for gas-filled and liquid-filled tubing at the highest reservoir pressure; line design pressure; tree and manifold ratings", "ISO 13628-1; API RP 17O; ISO 13623"),
    ("W2", "Drilling and start-up sequence", "Which wells are on stream at first oil and how are later wells brought in while the others produce?",
     "The first-oil rate, the flowline thermal state and simultaneous drilling and production safety follow from the sequence.", "Well schedule, rig availability, simultaneous-operations basis", ""),
    ("W3", "Well clean-up and completion fluid", "Where do clean-up flow, completion fluid and sand go during start-up?",
     "A clean-up flow through the new line can carry solids and fluids the host inlet is not rated for.", "Clean-up procedure, host receiving capacity, sand management basis", ""),
    ("W4", "Artificial lift and late life", "Is gas lift, a pump or boosting provided for in the layout and the host?",
     "Late-life rates and water cut may need lift; adding it later needs spare slots, lines and power.", "Nodal analysis late life, spare ports and umbilical lines", ""),
    ("W5", "Well barriers and tree valve philosophy", "Which valves are the primary and secondary barrier on each well and which fail closed?",
     "The tree valve arrangement fixes the first two isolation barriers drawn on the P&ID.", "Well barrier schematic, tree specification", "ISO 13628-4; NORSOK D-010"),
    ("S1", "Seabed footprint and levelling", "Is the seabed slope and soil at the template site inside what the foundation and levelling system accept?",
     "A template out of tolerance cannot be installed or connected.", "Bathymetry grid, geotechnical data, vendor levelling capability", "ISO 13628-1"),
    ("S2", "Manifold, choke and pigging arrangement", "Is there a pigging loop or a launcher on the template, and where are chokes and isolation valves?",
     "A single line without a loop can only be pigged one way; the choice sets the template layout.", "Pigging philosophy, template general arrangement", "ISO 13628-1"),
    ("S3", "Control system and umbilical capacity", "Does the umbilical carry the hydraulic, chemical, power and fibre functions for all trees and manifolds with spares?",
     "A missing line cannot be added after installation.", "Umbilical function list, control-system functional description", "ISO 13628-5"),
    ("S4", "Chemical injection points", "Where is each chemical injected (tree, manifold, flowline start) and how is back flow prevented?",
     "Injection point and check-valve barriers decide whether inhibitors reach the fluid and whether well fluid can enter the umbilical.", "Chemical injection schematic, dosing basis from flow assurance", "ISO 13628-6"),
    ("S5", "Metering and allocation", "How is each well measured: multiphase meter, virtual metering or periodic test through the host?",
     "Allocation and reservoir management need a metering basis from the first day.", "Metering philosophy, allocation agreement", ""),
    ("S6", "Protection structures", "Are trees and manifolds protected from trawl gear and dropped objects, and is that a fishing-intensity decision?",
     "Protection adds weight and installation scope; omitting it needs an accepted risk basis.", "Fishing-intensity data, dropped-object analysis", "ISO 13628-1"),
    ("F1", "Design pressure and wall thickness", "What is the design pressure of the flowline and riser and is the wall designed for it, collapse and installation?",
     "The design pressure ties to the shut-in pressure (W1), the hydrotest and the material cost.", "Pressure design to the pipeline standard, installation analysis", "DNV-ST-F101"),
    ("F2", "Pigging philosophy", "Is the line pigged one way or round trip, from which end, and what pigs and frequency?",
     "Pig launcher and receiver, kicker lines and chemical use depend on it; a single line cannot be pigged round trip without a loop.", "Pigging basis (wax, scale, liquid holdup), pig launcher position", "ISO 13628-1"),
    ("F3", "Route and crossings", "Which existing lines and cables does the route cross, at what angle, and who owns them?",
     "Each crossing needs an agreement, a design and an installation method.", "Route survey, crossing register, owner agreements", "DNV-ST-F101"),
    ("F4", "Riser configuration and hang-off", "Which riser type, hang-off and guide structure are used and are the host slots free?",
     "The riser fixes dynamic loading, the host modification and the tie-in point.", "Riser analysis, host slot and I-tube or J-tube register", "API RP 2RD; ISO 13628-12"),
    ("F5", "Expansion, buckling and free spans", "Do lateral buckling, expansion and free spans stay inside limits along the route?",
     "These govern the number of spools, anchors and rock placement.", "Route-specific analysis", "DNV-RP-F110; DNV-RP-F105"),
    ("F6", "Subsea isolation valve", "Is a subsea isolation valve required, where is it placed, and what inventory does it isolate?",
     "A line inventory that can feed a riser or topside leak needs an isolation barrier at a safe distance; omitting one needs a risk acceptance.", "Inventory calculation, topside leak scenarios, safety-zone geometry", "ISO 13628-1; ISO 13702"),
    ("F7", "Depressurisation of the line", "Can the line be depressurised through the host or a subsea path inside the hydrate-safe time?",
     "A line that cannot be depressurised cannot be cleared of a hydrate plug.", "Depressurisation analysis, vent or flare path", ""),
    ("H1", "Host slot and riser support", "Is there a free riser slot, J-tube or I-tube, hang-off position and umbilical entry on the host?",
     "A missing slot is a host modification and can decide the concept.", "Host drawings, slot register, owner confirmation", ""),
    ("H2", "Host inlet conditions and slug handling", "Does the host accept the arrival pressure, temperature, rates and slug volumes through the inlet separator?",
     "The host can limit the rate before the line does.", "Host process model, slug catcher or separator capacity", ""),
    ("H3", "Topside isolation and protection", "Which ESD valve, pig receiver, pressure control, relief and sampling points are needed at the landing?",
     "These are the topside half of the barrier philosophy.", "Landing P&ID, relief and flare capacity check", "ISO 10418; API RP 14C"),
    ("H4", "Utilities and chemical supply at the host", "Are there hydraulic power, chemical storage, electrical power and deck space for the new subsea system?",
     "Utility limits can cap the number of functions or the injection rate.", "Utility balance, deck layout", ""),
    ("H5", "Allocation metering at the host", "Is production from the new field measured separately before commingling?",
     "Commingled streams cannot be allocated afterwards.", "Allocation metering basis", ""),
    ("H6", "Injection water source and quality", "Where does the injection water come from and what treatment and deaeration does it need?",
     "Water quality sets injectivity, souring, corrosion and scale at the injector.", "Water quality specification, treatment capacity, compatibility test", ""),
    ("H7", "Fire protection at the riser", "Is the riser and its ESD valve inside a fire-protected area and how is it supported?",
     "The riser is a hydrocarbon inventory next to the host.", "Fire and explosion basis for the riser area", "ISO 13702"),
    ("A1", "Hydrate margin and remediation", "How long can the line stay shut in before hydrate formation and what is the response?",
     "No-touch time against the time to depressurise or inject inhibitor decides the shut-in philosophy.", "Cooldown calculation, inhibitor dosing, depressurisation time", ""),
    ("A2", "Wax, asphaltene, scale and corrosion", "Which threats apply and which inhibitors, materials and monitoring are needed?",
     "Each threat adds umbilical lines, pigging or material grade.", "Fluid study, corrosion assessment, inhibitor selection", "NORSOK M-506"),
    ("A3", "Slugging and turndown", "What are the minimum stable rate, terrain slugging and riser slug volume over the field life?",
     "Slug volumes decide the host inlet capacity and the control strategy.", "Transient simulation or screening of terrain and riser slugging", ""),
    ("A4", "Erosion and sand", "Does the velocity stay below the erosional limit with the actual sand risk and material?",
     "The limit sets the line size and the maximum rate.", "Erosional velocity basis, sand management plan", "API RP 14E"),
    ("A5", "Restart after shut-in", "Can the line be restarted cold, and what rate and inhibitor are needed?",
     "Gelled or cold fluid raises the restart pressure.", "Restart analysis", ""),
    ("O1", "Operating modes and valve line-up", "What is the state of every valve in normal flow, planned shut-in, emergency shutdown, depressurisation, pigging and restart?",
     "A line-up table is the base of the cause and effect matrix and the operating procedures.", "Valve line-up by mode, cause and effect matrix", "ISO 10418"),
    ("O2", "Emergency shutdown interface", "Which host signals close which subsea and topside valves, and how fast?",
     "The closing time sets surge and the inventory released.", "ESD philosophy, valve closing times, surge assessment", ""),
    ("O3", "Monitoring and leak detection", "Which pressure, temperature, flow and integrity measurements are available subsea and topside?",
     "Without them hydrate, leak and flow-assurance problems are found late.", "Instrument list, monitoring philosophy", ""),
    ("O4", "Intervention and ROV access", "Can an ROV reach the valves, connectors, chemical stabs and tie-in points?",
     "Access decides the intervention method and the template layout.", "ROV access study, tooling interface", "ISO 13628-8"),
    ("O5", "Injection line overpressure", "Can the injection pump shut-off pressure exceed the injection line and tree design pressure, and what protects it?",
     "An injection line is protected by a relief device or by a design pressure above the shut-off head.", "Pump curve, line design pressure, relief philosophy", ""),
    ("O6", "Simultaneous operations", "Which drilling, installation and production activities overlap near the host and the template?",
     "Overlap limits drilling windows and production rate.", "SIMOPS basis", ""),
    ("I1", "Installation sequence and tie-in method", "In what order are the template, lines, risers and umbilical installed and how are the ends connected (spool, jumper, hub)?",
     "The method sets tolerances, tooling, vessel spread and the number of connection points.", "Installation sequence, tolerance study, connector choice", "ISO 13628-15"),
    ("I2", "Crossing installation", "How are crossings installed, protected and what weather windows apply?",
     "Crossing work is a limiting installation activity.", "Crossing design, installation procedure", "DNV-ST-F101"),
    ("I3", "Pre-commissioning and commissioning", "How are the lines flooded, cleaned, gauged, pressure tested and dewatered, and which fluid fills them (water, MEG)?",
     "Pre-commissioning fluids and the first start-up set chemical and discharge needs.", "Pre-commissioning plan, test pressure, discharge permit", "DNV-ST-F101"),
    ("I4", "Host brownfield modification", "Which hot work, shutdown and deck modifications are needed at the host and when?",
     "A host outage can set the first-oil date.", "Modification scope, shutdown plan", ""),
    ("L1", "Design life and inspection", "What are the design life, corrosion allowance and inspection method (including pig-based inspection)?",
     "The life fixes the wall, material and pigging access.", "Design basis, inspection plan", ""),
    ("L2", "Decommissioning provision", "Is there a plan and cost provision for abandonment of the lines, template and umbilical?",
     "Provision affects the economic case and the regulatory consent.", "Decommissioning basis", ""),
    ("E1", "Fishing and dropped objects", "Is the fishing intensity along the route known and are protection and crossing practices defined?",
     "Third-party interaction drives protection, burial and trenching.", "Fishing-intensity data, protection assessment", ""),
    ("E2", "Discharges and emissions", "Which discharges (MEG, produced water, hydrotest water) and emissions arise during start-up and operation?",
     "Permits and the environmental case depend on them.", "Discharge and emission estimate", ""),
    ("E3", "Consents and approvals", "Which regulatory consents and plan amendments are needed for the new facilities?",
     "A consent can be on the critical path.", "Consent matrix", ""),
    ("X1", "Interface register", "Who owns each interface (reservoir, wells, subsea, host, control system, utilities) and what is exchanged?",
     "Unowned interfaces are where concepts fail late.", "Interface register with owners and dates", ""),
    ("X2", "Evidence and data gaps", "Which statements in the study rest on a document, which on an assumption, and which are unchecked?",
     "A reviewer must see which numbers are evidence.", "Evidence register, data-gap register", ""),
    ("X3", "Decision gates and cost class", "Which decision does this study support, at what maturity, and what cost class applies?",
     "A screening result must not be read as an approved design.", "Decision-gate checklist, cost class statement", ""),
]


def subsea_tie_in_considerations(categories: Optional[Iterable[str]] = None) -> List[Dict[str, str]]:
    """Return the generic checklist, optionally restricted to category letters (for example ``"WSF"``).

    Each item has ``id``, ``category``, ``topic``, ``question``, ``why``, ``evidence`` and ``pointer``.
    """
    wanted = set(categories) if categories is not None else set(CATEGORIES)
    out: List[Dict[str, str]] = []
    for item_id, topic, question, why, evidence, pointer in _ITEMS:
        if item_id[0] in wanted:
            out.append(
                {"id": item_id, "category": CATEGORIES[item_id[0]], "topic": topic, "question": question, "why": why, "evidence": evidence, "pointer": pointer}
            )
    return out


def considerations_register(statuses: Optional[Dict[str, Dict[str, str]]] = None, categories: Optional[Iterable[str]] = None) -> List[Dict[str, str]]:
    """Merge project statuses into the checklist.

    Args:
        statuses: ``{item id: {"status": ..., "finding": ..., "evidence": ..., "action": ..., "owner": ...}}``. ``status`` must be one of
            :data:`STATUSES`; an item without an entry is ``OPEN`` with the finding "not addressed in this study".
        categories: optional category letters to include.

    Returns:
        One row per item with the checklist fields plus ``status``, ``finding``, ``source``, ``action`` and ``owner``.

    Raises:
        ValueError: for an unknown item id or status.
    """
    statuses = statuses or {}
    known = {i[0] for i in _ITEMS}
    for key, rec in statuses.items():
        if key not in known:
            raise ValueError("unknown consideration id %r" % key)
        if rec.get("status") not in STATUSES:
            raise ValueError("%s: status must be one of %s" % (key, ", ".join(STATUSES)))
    rows = []
    for item in subsea_tie_in_considerations(categories):
        rec = statuses.get(item["id"], {})
        rows.append(
            dict(
                item,
                status=rec.get("status", "OPEN"),
                finding=rec.get("finding", "Not addressed in this study."),
                source=rec.get("evidence", ""),
                action=rec.get("action", ""),
                owner=rec.get("owner", ""),
            )
        )
    return rows


def register_summary(rows: Iterable[Dict[str, str]]) -> Dict[str, object]:
    """Count rows by status and by category, and list the open ids."""
    rows = list(rows)
    by_status = {s: sum(1 for r in rows if r["status"] == s) for s in STATUSES}
    by_cat: Dict[str, Dict[str, int]] = {}
    for r in rows:
        by_cat.setdefault(r["category"], {s: 0 for s in STATUSES})[r["status"]] += 1
    return {"total": len(rows), "by_status": by_status, "by_category": by_cat, "open": [r["id"] for r in rows if r["status"] == "OPEN"]}
