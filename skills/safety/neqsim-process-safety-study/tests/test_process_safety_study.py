import pytest
from process_safety_study import (
    STEPS,
    agents_for,
    claim_gate,
    conservatism_gate,
    evidence_gate,
    hand_calc_gate,
    profile_gate,
    reconcile_values,
    skills_for,
    step,
    tag_anchor_gate,
    workflow,
)


def test_workflow_order_and_content():
    ids = [s["id"] for s in workflow()]
    assert ids == [f"S{i:02d}" for i in range(len(STEPS))]
    for item in workflow():
        assert (
            item["skills"]
            and item["agents"]
            and item["evidence"]
            and item["gate"]
            and item["traps"]
        )
    assert "neqsim-cfd-coupling" in step("S08")["skills"]
    assert "olga-simulation-agent" in agents_for(["S06"])
    assert "neqsim-hazop-node-pack" in skills_for(["S10"])
    with pytest.raises(KeyError):
        step("S99")


def test_evidence_gate_turns_unread_documents_into_gaps():
    register = [
        {
            "topic": "criteria",
            "document": "DOC-A",
            "status": "READ",
            "clauses": ["4.1"],
        },
        {"topic": "models", "document": "DOC-B", "status": "PARTLY"},
        {"topic": "rates", "document": "DOC-C", "status": "NOT_READ"},
    ]
    gate = evidence_gate(register)
    assert gate["status"] == "UNVERIFIED_SCREENING"
    assert not gate["compliance_claims_allowed"]
    assert [g["source"] for g in gate["data_gaps"]] == ["models", "rates"]
    assert evidence_gate(register[:1])["status"] == "READY_FOR_REVIEW"
    assert evidence_gate([])["status"] == "UNVERIFIED_SCREENING"


def test_claim_gate_needs_read_document_and_clause():
    register = [
        {"document": "DOC-A", "status": "READ", "clauses": ["4.1", 5]},
        {"document": "DOC-B", "status": "PARTLY", "clauses": ["2"]},
    ]
    claims = [
        {"claim": "criterion met", "document": "DOC-A", "clause": "4.1"},
        {"claim": "other clause", "document": "DOC-A", "clause": "9"},
        {"claim": "partly read", "document": "DOC-B", "clause": "2"},
        {"claim": "unknown", "document": "DOC-Z", "clause": "1"},
    ]
    decisions = [c["decision"] for c in claim_gate(claims, register)]
    assert decisions == ["ALLOWED", "REJECTED", "REJECTED", "REJECTED"]


def test_profile_gate_detects_superseded_profile():
    source = [(0.0, 260.0), (10000.0, 200.0), (20000.0, 120.0)]
    good = [(0.0, 260.0), (5000.0, 230.0), (20000.0, 120.0)]
    old = [(0.0, 392.0), (20000.0, 120.0)]
    assert profile_gate(good, source, "design case rev 02")["status"] == "MATCH"
    bad = profile_gate(old, source, "design case rev 02")
    assert bad["status"] == "MISMATCH"
    assert bad["max_rel_diff"] == pytest.approx(392.0 / 260.0 - 1.0)
    assert profile_gate(good, source, "")["status"] == "NO_SOURCE"
    assert profile_gate([(25000.0, 100.0)], source, "rev 02")["status"] == "MISMATCH"


def test_hand_calc_gate():
    assert hand_calc_gate(464.1, 449.0)["status"] == "MATCH"
    wrong = hand_calc_gate(1106.3, 449.0, label="choke failed open")
    assert wrong["status"] == "MISMATCH" and not wrong["usable_as_basis"]
    assert wrong["ratio"] == pytest.approx(2.464, rel=1e-3)
    none = hand_calc_gate(100.0, None)
    assert none["status"] == "NO_HAND_CALC" and not none["usable_as_basis"]


def test_conservatism_gate_for_transient_verification():
    surge = conservatism_gate(9.6, 55.0)
    assert surge["verdict"] == "NON_CONSERVATIVE" and surge["ratio"] == pytest.approx(
        0.1745, rel=1e-3
    )
    assert conservatism_gate(46.0, 37.0)["verdict"] == "CONSERVATIVE"
    assert conservatism_gate(36.0, 36.5)["verdict"] == "CONSISTENT"
    assert (
        conservatism_gate(60.0, 100.0, higher_is_conservative=False)["verdict"]
        == "CONSERVATIVE"
    )
    with pytest.raises(ValueError):
        conservatism_gate(1.0, 0.0)


def test_tag_anchor_gate_separates_orphans_and_proposals():
    pid_tags = ["PZV-101", "xv-201", "PT-301"]
    items = [
        {"id": "SIF-1 sensor", "tag": "PT-301"},
        {"id": "SIF-1 final", "tag": "XV-201"},
        {"id": "SIF-2 sensor", "tag": "PT-999"},
        {"id": "new valve", "tag": "XV-NEW", "proposed": True},
    ]
    gate = tag_anchor_gate(items, pid_tags)
    assert gate["status"] == "ORPHANS"
    assert [o["id"] for o in gate["orphans"]] == ["SIF-2 sensor"]
    assert [p["id"] for p in gate["proposed_markups"]] == ["new valve"]
    assert tag_anchor_gate(items[:2], pid_tags)["status"] == "ANCHORED"


def test_reconcile_values_flags_changed_numbers():
    values = [
        {"name": "segment volume", "workstream": "ws1", "value": 100.0, "unit": "m3"},
        {"name": "segment volume", "workstream": "ws4", "value": 131.0, "unit": "m3"},
        {"name": "test interval", "workstream": "ws3", "value": 6.0, "unit": "month"},
        {"name": "test interval", "workstream": "ws6", "value": 6.0, "unit": "month"},
        {"name": "flare load", "workstream": "ws3", "value": 250.0, "unit": "t/h"},
        {"name": "flare load", "workstream": "ws5", "value": 250.0, "unit": "kg/s"},
    ]
    conflicts = reconcile_values(values)
    assert [c["name"] for c in conflicts] == ["flare load", "segment volume"]
    assert conflicts[1]["spread"] == pytest.approx(31.0 / 131.0)


def test_worked_example_gates_chain_to_an_honest_status():
    register = [
        {"topic": "criteria", "document": "DOC-A", "status": "READ", "clauses": ["4.1"]}
    ]
    claims = [{"claim": "tolerable", "document": "DOC-A", "clause": "4.1"}]
    assert claim_gate(claims, register)[0]["decision"] == "ALLOWED"
    register.append({"topic": "rates", "document": "DOC-C", "status": "NOT_READ"})
    gate = evidence_gate(register)
    assert gate["status"] == "UNVERIFIED_SCREENING"
    assert gate["data_gaps"][0]["assumed"] == "conventions applied"
