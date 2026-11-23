"""Tests for the P&ID safeguard placement rules on small synthetic layouts."""

from __future__ import annotations

import json

import pytest
from hazop_node_pack.placement_rules import (
    NOTICE,
    RULE_IDS,
    RULES,
    SEVERITIES,
    Finding,
    check_layout,
    format_findings,
)


def make_layout(nodes, edges, **extra):
    """Layout dictionary from ``(id, kind, tag, text, attrs)`` and ``(a, b, fluid)`` tuples."""
    out_nodes = []
    for i, spec in enumerate(nodes):
        key, kind, tag, text = spec[:4]
        raw = {"id": key, "kind": kind, "tag": tag, "bbox": [10.0 * i, 10.0, 8.0, 8.0]}
        if text:
            raw["texts"] = [{"text": text}]
        if len(spec) > 4:
            raw.update(spec[4])
        out_nodes.append(raw)
    out_edges = []
    for i, (a, b, fluid) in enumerate(edges):
        out_edges.append(
            {"id": f"E{i}", "from": a, "to": b, "fluid": fluid, "points": []}
        )
    layout = {"schema": "neqsim.pfd_layout.v1", "nodes": out_nodes, "edges": out_edges}
    layout.update(extra)
    return layout


def ids(findings):
    return [f.rule_id for f in findings]


# ------------------------------------------------------------------ rule table
def test_rule_table_is_complete_and_states_the_basis():
    assert RULE_IDS == tuple(f"PR-{n:02d}" for n in range(1, 13))
    required = {"id", "title", "applies_to", "check", "rationale", "severity", "basis"}
    for rule in RULES:
        assert required <= set(rule)
        assert rule["severity"] in SEVERITIES
        assert "convention, not verified text" in rule["basis"]
        assert "no compliance claim" in rule["basis"]
    bases = " ".join(rule["basis"] for rule in RULES)
    for name in ("API RP 14C", "API STD 521", "IEC 61511", "NORSOK S-001"):
        assert name in bases
    assert "not prove" in NOTICE


# ------------------------------------------------------------------ PR-01
def _segment(fluid="oil", extra_nodes=(), extra_edges=(), **attrs):
    nodes = [
        ("B1", "boundary", None, "From A"),
        ("V1", "ball_valve", "XV-1", ""),
        ("J", "junction", None, "", attrs),
        ("V2", "gate_valve", "XV-2", ""),
        ("B2", "boundary", None, "To B"),
        *extra_nodes,
    ]
    edges = [
        ("B1", "V1", fluid),
        ("V1", "J", fluid),
        ("J", "V2", fluid),
        ("V2", "B2", fluid),
        *extra_edges,
    ]
    return make_layout(nodes, edges)


def test_pr01_fires_for_isolatable_liquid_segment_without_relief():
    findings = check_layout(_segment("oil"), rules=["PR-01"])
    assert ids(findings) == ["PR-01"]
    assert findings[0].objects == ("V1", "V2")
    assert findings[0].severity == "ERROR" and findings[0].fix


@pytest.mark.parametrize("fluid", ["mixed", "multiphase", "liquid"])
def test_pr01_covers_mixed_and_liquid_fluids(fluid):
    assert ids(check_layout(_segment(fluid), rules=["PR-01"])) == ["PR-01"]


def test_pr01_quiet_with_relief_gas_or_exemption():
    with_psv = _segment("oil", [("PSV", "psv", "PSV-1", "")], [("J", "PSV", "oil")])
    assert check_layout(with_psv, rules=["PR-01"]) == []
    assert check_layout(_segment("gas"), rules=["PR-01"]) == []
    assert check_layout(_segment("oil", exempt="PR-01"), rules=["PR-01"]) == []
    listed = _segment("oil")
    listed["hazop_exemptions"] = [
        {"rule": "PR-01", "objects": ["J"], "reason": "open to a tank"}
    ]
    assert check_layout(listed, rules=["PR-01"]) == []


def test_pr01_ignores_open_segments_and_dead_end_stubs():
    open_end = make_layout(
        [
            ("B1", "boundary", None, ""),
            ("V1", "ball_valve", "XV-1", ""),
            ("J", "junction", None, ""),
        ],
        [("B1", "V1", "oil"), ("V1", "J", "oil")],
    )
    assert check_layout(open_end, rules=["PR-01"]) == []
    stub = make_layout(
        [
            ("B1", "boundary", None, ""),
            ("V1", "ball_valve", "XV-1", ""),
            ("J", "junction", None, ""),
            ("DV", "ball_valve", "DV-1", ""),
            ("B2", "boundary", None, ""),
        ],
        [("B1", "V1", "oil"), ("V1", "J", "oil"), ("J", "DV", "oil")],
    )
    assert (
        check_layout(stub, rules=["PR-01"]) == []
    )  # a dead-end valve does not isolate


def test_pr01_two_valves_in_direct_series_form_a_segment():
    layout = make_layout(
        [
            ("B1", "boundary", None, ""),
            ("V1", "ball_valve", "XV-1", ""),
            ("V2", "check_valve", "NRV-1", ""),
            ("B2", "boundary", None, ""),
        ],
        [("B1", "V1", "oil"), ("V1", "V2", "oil"), ("V2", "B2", "oil")],
    )
    findings = check_layout(layout, rules=["PR-01"])
    assert ids(findings) == ["PR-01"] and findings[0].objects == ("V1", "V2")


# ------------------------------------------------------------------ PR-02
def test_pr02_lists_everything_missing_on_a_bare_receiver():
    layout = make_layout([("RCV", "pig_receiver", "PR-1", "")], [])
    findings = check_layout(layout, rules=["PR-02"])
    assert ids(findings) == ["PR-02"]
    assert "vent, drain, relief/PSV connection, inlet isolation, outlet isolation" in (
        findings[0].message
    )


# ------------------------------------------------------------------ PR-03
def test_pr03_riser_node_needs_an_esd_valve_before_process_equipment():
    bare = make_layout(
        [("RSR", "riser", "RSR-1", ""), ("SEP", "vessel", "V-1", "")],
        [("RSR", "SEP", "gas")],
    )
    assert ids(check_layout(bare, rules=["PR-03"])) == ["PR-03"]
    protected = make_layout(
        [
            ("RSR", "riser", "RSR-1", ""),
            ("ESD", "ball_valve", "ESDV-1", ""),
            ("SEP", "vessel", "V-1", ""),
        ],
        [("RSR", "ESD", "gas"), ("ESD", "SEP", "gas")],
    )
    assert check_layout(protected, rules=["PR-03"]) == []  # recognised by the ESDV tag


def test_pr03_needs_an_import_hint_and_ignores_utility_boundaries():
    plain = make_layout(
        [("B", "boundary", None, "From separator"), ("V", "vessel", "V-1", "")],
        [("B", "V", "gas")],
    )
    assert check_layout(plain, rules=["PR-03"]) == []
    utility = make_layout(
        [
            ("B", "boundary", None, "Platform chemical supply"),
            ("V", "vessel", "V-1", ""),
        ],
        [("B", "V", "gas")],
    )
    assert check_layout(utility, rules=["PR-03"]) == []


# ------------------------------------------------------------------ PR-04
def test_pr04_class_break_without_hipps_is_an_info_prompt():
    layout = make_layout(
        [
            ("A", "vessel", "V-1", ""),
            ("SB", "spec_break", None, ""),
            ("C", "vessel", "V-2", ""),
        ],
        [("A", "SB", "gas"), ("SB", "C", "gas")],
    )
    findings = check_layout(layout, rules=["PR-04"])
    assert ids(findings) == ["PR-04"] and findings[0].severity == "INFO"
    assert findings[0].objects == ("SB",)


def _hipps(pt_taps=("J0", "J1", "J2"), logic=True, valves=2):
    nodes = [("HIPPS", "hipps", "HIPPS-1", "")]
    edges = []
    for n in range(valves):
        nodes.append((f"HV{n}", "hydraulic_valve", f"HV-{n}", ""))
        edges.append(("LS", f"HV{n}", "signal"))
    for n, tap in enumerate(pt_taps):
        nodes += [(f"PT{n}", "transmitter", f"PT-10{n}", "")]
        if tap not in [x[0] for x in nodes]:
            nodes.append((tap, "junction", None, ""))
        edges += [(tap, f"PT{n}", "gas"), ("LS", f"PT{n}", "signal")]
    if logic:
        nodes.append(("LS", "logic_solver", "LS-1", ""))
        edges.append(("LS", "HIPPS", "signal"))
    else:
        nodes.append(("LS", "controller", "XC-1", ""))
        edges.append(("HIPPS", "LS", "signal"))
    return make_layout(nodes, edges)


def test_pr04_complete_hipps_is_quiet():
    assert check_layout(_hipps(), rules=["PR-04"]) == []


def test_pr04_reports_each_missing_element_of_the_function():
    assert [f.message for f in check_layout(_hipps(valves=1), rules=["PR-04"])] == [
        "HIPPS-like function has 1 isolation valve(s); two in series are expected"
    ]
    two_pts = check_layout(_hipps(pt_taps=("J0", "J1")), rules=["PR-04"])
    assert (
        ids(two_pts) == ["PR-04"] and "2 pressure transmitter(s)" in two_pts[0].message
    )
    shared = check_layout(_hipps(pt_taps=("J0", "J0", "J0")), rules=["PR-04"])
    assert ids(shared) == ["PR-04"] and "share taps" in shared[0].message
    no_logic = check_layout(_hipps(logic=False), rules=["PR-04"])
    assert ids(no_logic) == ["PR-04"] and "no logic solver" in no_logic[0].message


# ------------------------------------------------------------------ PR-05
def test_pr05_pump_needs_relief_or_a_transmitter_pair_on_the_discharge():
    base = [
        ("P", "pump", "P-1", ""),
        ("J", "junction", None, ""),
        ("V", "vessel", "V-1", ""),
    ]
    edges = [("P", "J", "oil"), ("J", "V", "oil")]
    assert ids(check_layout(make_layout(base, edges), rules=["PR-05"])) == ["PR-05"]
    relief = make_layout(
        base + [("PSV", "psv", "PSV-1", "")], edges + [("J", "PSV", "oil")]
    )
    assert check_layout(relief, rules=["PR-05"]) == []
    pair = make_layout(
        base + [("PT1", "transmitter", "PT-1", ""), ("PT2", "transmitter", "PT-2", "")],
        edges + [("J", "PT1", "oil"), ("J", "PT2", "oil")],
    )
    assert check_layout(pair, rules=["PR-05"]) == []
    single = make_layout(
        base + [("PT1", "transmitter", "PT-1", "")], edges + [("J", "PT1", "oil")]
    )
    assert ids(check_layout(single, rules=["PR-05"])) == ["PR-05"]


# ------------------------------------------------------------------ PR-06
def _injection(checks, isolation=False):
    nodes = [
        ("TANK", "tank", "T-1", ""),
        ("J", "junction", None, ""),
        ("B1", "boundary", None, "From well"),
        ("B2", "boundary", None, "To process"),
    ]
    edges = [("B1", "J", "gas"), ("J", "B2", "gas")]
    previous = "J"
    chain = []
    for n in range(checks):
        chain.append((f"CV{n}", "check_valve", f"NRV-{n}", ""))
    if isolation:
        chain.append(("IV", "ball_valve", "XV-9", ""))
    for key, kind, tag, text in chain:
        nodes.append((key, kind, tag, text))
        edges.append((key, previous, "chemical"))
        previous = key
    edges.append(("TANK", previous, "chemical"))
    return make_layout(nodes, edges)


def test_pr06_injection_needs_two_checks_or_check_plus_isolation():
    assert ids(check_layout(_injection(0), rules=["PR-06"])) == ["PR-06"]
    assert ids(check_layout(_injection(1), rules=["PR-06"])) == ["PR-06"]
    assert check_layout(_injection(2), rules=["PR-06"]) == []
    assert check_layout(_injection(1, isolation=True), rules=["PR-06"]) == []


# ------------------------------------------------------------------ PR-07
def _edp(orifice=True, destination=True):
    nodes = [("J", "junction", None, ""), ("BDV", "bdv", "BDV-1", "")]
    edges = [("J", "BDV", "gas")]
    last = "BDV"
    if orifice:
        nodes.append(("RO", "restriction_orifice", "RO-1", ""))
        edges.append(("BDV", "RO", "gas"))
        last = "RO"
    if destination:
        nodes.append(("FL", "boundary", None, "To flare"))
        edges.append((last, "FL", "gas"))
    return make_layout(nodes, edges)


def test_pr07_depressurisation_line_needs_orifice_and_destination():
    assert check_layout(_edp(), rules=["PR-07"]) == []
    no_ro = check_layout(_edp(orifice=False), rules=["PR-07"])
    assert ids(no_ro) == ["PR-07"] and "restriction orifice" in no_ro[0].message
    no_dest = check_layout(_edp(destination=False), rules=["PR-07"])
    assert (
        ids(no_dest) == ["PR-07"] and "flare/closed destination" in no_dest[0].message
    )


# ------------------------------------------------------------------ PR-08
def test_pr08_module_needs_two_gas_detectors_and_a_flame_detector():
    equipment = [
        ("SEP", "vessel", "V-1", "", {"module": "M1"}),
        ("B", "boundary", None, ""),
    ]
    edges = [("B", "SEP", "gas")]
    bare = check_layout(make_layout(equipment, edges), rules=["PR-08"])
    assert ids(bare) == ["PR-08"] and bare[0].objects == ("SEP",)
    assert (
        "gas detectors (0 of 2)" in bare[0].message
        and "flame detector" in bare[0].message
    )
    detectors = [
        ("G1", "gas_detector", "AT-1", "", {"module": "M1"}),
        ("G2", "instrument", "AT-2", ""),
        ("F1", "flame_detector", "BE-1", ""),
    ]
    assert (
        check_layout(make_layout(equipment + detectors, edges), rules=["PR-08"]) == []
    )
    one_gas = check_layout(
        make_layout(equipment + detectors[:1] + detectors[2:], edges), rules=["PR-08"]
    )
    assert "gas detectors (1 of 2)" in one_gas[0].message


# ------------------------------------------------------------------ PR-09
def test_pr09_single_transmitter_initiator_is_flagged_unless_voted():
    single = make_layout(
        [("PT1", "transmitter", "PZIT-1", "PAHH to ESD"), ("J", "junction", None, "")],
        [("J", "PT1", "gas")],
    )
    findings = check_layout(single, rules=["PR-09"])
    assert ids(findings) == ["PR-09"] and findings[0].objects == ("PT1",)
    declared = make_layout(
        [("PT1", "transmitter", "PZIT-1", "PAHH to ESD", {"voting": "2oo3"})], []
    )
    assert check_layout(declared, rules=["PR-09"]) == []
    one_oo_one = make_layout(
        [("PT1", "transmitter", "PZIT-1", "PAHH", {"voting": "1oo1"})], []
    )
    assert ids(check_layout(one_oo_one, rules=["PR-09"])) == ["PR-09"]
    voted = make_layout(
        [
            ("PT1", "transmitter", "PZIT-1", "PAHH"),
            ("PT2", "transmitter", "PZIT-2", ""),
            ("PT3", "transmitter", "PZIT-3", ""),
            ("J", "junction", None, ""),
        ],
        [("J", "PT1", "gas"), ("J", "PT2", "gas"), ("J", "PT3", "gas")],
    )
    assert check_layout(voted, rules=["PR-09"]) == []


# ------------------------------------------------------------------ PR-10
def test_pr10_vents_and_drains_must_reach_a_closed_destination():
    to_atmosphere = make_layout(
        [("VV", "ball_valve", "VV-1", ""), ("ATM", "atmosphere", None, "")],
        [("VV", "ATM", "gas")],
    )
    findings = check_layout(to_atmosphere, rules=["PR-10"])
    assert (
        ids(findings) == ["PR-10"] and "discharges to atmosphere" in findings[0].message
    )
    dead_end = make_layout([("DV", "ball_valve", "DV-1", "")], [])
    assert "open end" in check_layout(dead_end, rules=["PR-10"])[0].message
    closed = make_layout(
        [("VV", "ball_valve", "VV-1", ""), ("HDR", "boundary", None, "Vent header")],
        [("VV", "HDR", "gas")],
    )
    assert check_layout(closed, rules=["PR-10"]) == []
    capped = make_layout(
        [("DV", "ball_valve", "DV-1", ""), ("CAP", "blind", None, "")],
        [("DV", "CAP", "oil")],
    )
    assert check_layout(capped, rules=["PR-10"]) == []


# ------------------------------------------------------------------ PR-11
def _choke(**attrs):
    return make_layout(
        [
            ("A", "vessel", "V-1", ""),
            ("CH", "choke", "CH-1", attrs.pop("text", ""), attrs),
            ("SB", "spec_break", None, ""),
            ("B", "vessel", "V-2", ""),
        ],
        [("A", "CH", "gas"), ("CH", "SB", "gas"), ("SB", "B", "gas")],
    )


def test_pr11_choke_at_class_break_needs_a_closing_provision():
    assert ids(check_layout(_choke(), rules=["PR-11"])) == ["PR-11"]
    assert check_layout(_choke(fail_position="closed"), rules=["PR-11"]) == []
    assert check_layout(_choke(text="travel stop 20 %"), rules=["PR-11"]) == []
    assert check_layout(_choke(interlock=True), rules=["PR-11"]) == []
    away = make_layout(
        [
            ("A", "vessel", "V-1", ""),
            ("CH", "choke", "CH-1", ""),
            ("B", "vessel", "V-2", ""),
        ],
        [("A", "CH", "gas"), ("CH", "B", "gas")],
    )
    assert check_layout(away, rules=["PR-11"]) == []  # no class break nearby


# ------------------------------------------------------------------ PR-12
def test_pr12_duplicate_tags_ignore_asterisk_and_case():
    layout = make_layout(
        [
            ("A", "ball_valve", "XV-1", ""),
            ("B", "ball_valve", "xv-1*", ""),
            ("C", "ball_valve", "XV-2", ""),
        ],
        [],
    )
    findings = check_layout(layout, rules=["PR-12"])
    assert ids(findings) == ["PR-12"] and findings[0].objects == ("A", "B")


# ------------------------------------------------------------------ API
def test_check_layout_input_handling(tmp_path):
    layout = _segment("oil")
    path = tmp_path / "layout.json"
    path.write_text(json.dumps(layout), encoding="utf-8")
    assert ids(check_layout(path, rules=["pr-01"])) == [
        "PR-01"
    ]  # path, case-insensitive id
    assert [f.rule_id for f in check_layout(str(path))] == ids(check_layout(layout))
    with pytest.raises(ValueError, match="unknown rule"):
        check_layout(layout, rules=["PR-99"])
    with pytest.raises(ValueError, match="no nodes"):
        check_layout({"schema": "neqsim.pfd_layout.v1", "nodes": []})
    with pytest.raises(ValueError, match="schema"):
        check_layout({"schema": "other.v2", "nodes": [{"id": "A"}]})
    with pytest.raises(TypeError):
        check_layout(42)  # type: ignore[arg-type]


def test_findings_serialise_and_the_report_carries_the_evidence_notice():
    findings = check_layout(_segment("oil"), rules=["PR-01"])
    data = findings[0].to_dict()
    assert data["rule_id"] == "PR-01" and data["objects"] == ["V1", "V2"]
    json.dumps(data)
    assert isinstance(findings[0], Finding)
    report = format_findings(findings)
    assert "PR-01 [ERROR]" in report and report.endswith(f"Note: {NOTICE}")
    assert format_findings([]) == f"Note: {NOTICE}"


# ------------------------------------------------------------------ worked example
def riser_landing(psv=True, esdv=True, pts=3, orifice=True):
    """Small riser-landing layout: import boundary, ESDV, HIPPS, pig receiver and EDP line."""
    nodes = [
        ("B-RSR", "boundary", None, "From riser"),
        ("J0", "junction", None, ""),
        ("HV0", "hydraulic_valve", "HV-1", ""),
        ("J1", "junction", None, ""),
        ("HV1", "hydraulic_valve", "HV-2", ""),
        ("J2", "junction", None, ""),
        ("RCV", "pig_receiver", "PR-101", "Pig receiver"),
        ("XVO", "ball_valve", "XV-OUT", ""),
        ("B-OUT", "boundary", None, "To process"),
        ("HIPPS", "hipps", "HIPPS-1", ""),
        ("LS", "logic_solver", "LS-1", ""),
        ("VV", "ball_valve", "VV-101", ""),
        ("B-VNT", "boundary", None, "Vent header"),
        ("DV", "ball_valve", "DV-101", ""),
        ("B-DRN", "boundary", None, "Closed drain"),
        ("BDV", "bdv", "BDV-101", ""),
        ("B-FL", "boundary", None, "To flare"),
        ("GD1", "gas_detector", "AT-101", ""),
        ("GD2", "gas_detector", "AT-102", ""),
        ("FD1", "flame_detector", "BE-101", ""),
    ]
    edges = [
        ("B-RSR", "J0", "gas"),
        ("J0", "HV0", "gas"),
        ("HV0", "J1", "gas"),
        ("J1", "HV1", "gas"),
        ("HV1", "J2", "gas"),
        ("J2", "RCV", "gas"),
        ("RCV", "XVO", "gas"),
        ("XVO", "B-OUT", "gas"),
        ("RCV", "VV", "gas"),
        ("VV", "B-VNT", "gas"),
        ("RCV", "DV", "gas"),
        ("DV", "B-DRN", "gas"),
        ("J2", "BDV", "gas"),
        ("HIPPS", "LS", "signal"),
        ("LS", "HV0", "signal"),
        ("LS", "HV1", "signal"),
    ]
    if esdv:
        nodes.append(("ESDV", "esdv", "ESDV-101", ""))
        edges = [e for e in edges if e[:2] != ("B-RSR", "J0")]
        edges += [("B-RSR", "ESDV", "gas"), ("ESDV", "J0", "gas")]
    if psv:
        nodes.append(("PSV", "psv", "PSV-101", ""))
        edges.append(("RCV", "PSV", "gas"))
    for n, junction in enumerate(["J0", "J1", "J2"][:pts]):
        nodes.append((f"PT{n}", "transmitter", f"PT-10{n}", ""))
        edges += [(junction, f"PT{n}", "gas"), ("LS", f"PT{n}", "signal")]
    if orifice:
        nodes.append(("RO", "restriction_orifice", "RO-101", ""))
        edges += [("BDV", "RO", "gas"), ("RO", "B-FL", "gas")]
    else:
        edges.append(("BDV", "B-FL", "gas"))
    return make_layout(nodes, edges)


def test_worked_example_riser_landing_finding_ids():
    assert check_layout(riser_landing()) == []
    assert ids(check_layout(riser_landing(psv=False))) == ["PR-02"]
    assert ids(check_layout(riser_landing(esdv=False))) == ["PR-03"]
    assert ids(check_layout(riser_landing(pts=2))) == ["PR-04"]
    assert ids(check_layout(riser_landing(orifice=False))) == ["PR-07"]
    combined = check_layout(riser_landing(psv=False, esdv=False, pts=2, orifice=False))
    assert ids(combined) == ["PR-02", "PR-03", "PR-04", "PR-07"]
    pr02 = next(f for f in combined if f.rule_id == "PR-02")
    assert pr02.objects == ("RCV",) and "relief/PSV connection" in pr02.message
    pr03 = next(f for f in combined if f.rule_id == "PR-03")
    assert pr03.objects == ("B-RSR",)
    pr07 = next(f for f in combined if f.rule_id == "PR-07")
    assert pr07.objects == ("BDV",) and "restriction orifice" in pr07.message
