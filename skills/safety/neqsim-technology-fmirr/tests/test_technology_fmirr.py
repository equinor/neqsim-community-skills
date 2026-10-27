import json
from pathlib import Path

import pytest

from technology_fmirr import (
    DEFAULT_MATRIX,
    FailureModeEntry,
    FmirrRegister,
    from_dict,
    risk_level,
)

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "example_fmirr.json"


def _entry(eid="1", **kw):
    base = dict(
        entry_id=eid,
        item="Seal",
        function="Contain gas",
        failure_mode="External leakage",
        failure_mechanism="Fatigue",
        consequence_class=3,
        probability_class=3,
    )
    base.update(kw)
    return FailureModeEntry(**base)


def test_matrix_is_monotonic_in_both_axes():
    order = {"Low": 0, "Medium": 1, "High": 2}
    for p in range(1, 6):
        for c in range(1, 5):
            assert order[DEFAULT_MATRIX[p][c]] >= order[DEFAULT_MATRIX[p][c - 1]]
    for c in range(5):
        for p in range(1, 5):
            assert order[DEFAULT_MATRIX[p + 1][c]] >= order[DEFAULT_MATRIX[p][c]]


@pytest.mark.parametrize(
    "cons,prob,expected",
    [(1, 1, "Low"), (3, 3, "Medium"), (5, 5, "High"), (4, 4, "High"), (2, 2, "Low")],
)
def test_risk_level(cons, prob, expected):
    assert risk_level(cons, prob) == expected


def test_high_consequence_floor_prevents_low():
    assert risk_level(5, 1) == "Medium"
    assert risk_level(5, 1, high_consequence_floor=False) == "Low"


def test_risk_level_rejects_out_of_range():
    with pytest.raises(ValueError):
        risk_level(0, 3)
    with pytest.raises(ValueError):
        risk_level(3, 6)
    with pytest.raises(ValueError):
        risk_level(True, 3)


def test_malformed_matrix_rejected():
    with pytest.raises(ValueError):
        risk_level(3, 3, matrix={3: ("Low",)})
    with pytest.raises(ValueError):
        risk_level(3, 3, matrix={3: ("Low", "Low", "Bad", "Low", "Low")})


def test_register_basic_flow():
    reg = FmirrRegister("Demo")
    reg.add(_entry("1", consequence_class=4, probability_class=4))
    reg.add(_entry("2", consequence_class=1, probability_class=1))
    result = reg.evaluate()
    assert result["summary"]["counts"] == {"Low": 1, "Medium": 0, "High": 1}
    assert result["summary"]["critical_ids"] == ["1"]
    assert result["risk_matrix"]["rows_probability_5_to_1"]["4"][3] == 1


def test_low_risk_modes_stay_in_register():
    reg = FmirrRegister("Demo")
    reg.add(_entry("1", consequence_class=1, probability_class=1))
    assert len(reg.evaluate()["rows"]) == 1


def test_validation_errors():
    reg = FmirrRegister("Demo")
    reg.add(_entry("1"))
    with pytest.raises(ValueError):
        reg.add(_entry("1"))
    with pytest.raises(ValueError):
        reg.add(_entry("2", item=" "))
    with pytest.raises(ValueError):
        reg.add(_entry("3", probability_class=9))
    with pytest.raises(ValueError):
        FmirrRegister(" ")
    with pytest.raises(ValueError):
        FmirrRegister("Demo").evaluate()


def test_critical_without_test_or_detection_is_a_gap():
    reg = FmirrRegister("Demo")
    reg.add(_entry("1", consequence_class=4, probability_class=4))
    gaps = [f["text"] for f in reg.evaluate()["findings"] if f["level"] == "gap"]
    assert any("no qualification activity" in g for g in gaps)
    assert any("no detection method" in g for g in gaps)


def test_item_mode_mechanism_cause_separation_warnings():
    reg = FmirrRegister("Demo")
    reg.add(_entry("1", item="Valve", failure_mode="Valve"))
    reg.add(_entry("2", failure_mode="Leak due to fatigue"))
    texts = " ".join(f["text"] for f in reg.evaluate()["findings"])
    assert "repeats the failed item" in texts
    assert "mixes in a mechanism or cause" in texts


def test_unknown_classes_warn():
    reg = FmirrRegister("Demo")
    reg.add(_entry("1", failure_mechanism_class="Weird", failure_cause_class="Odd"))
    texts = " ".join(f["text"] for f in reg.evaluate()["findings"])
    assert "Mechanism class" in texts and "Cause class" in texts


def test_rerate_keeps_history_and_requires_basis():
    reg = FmirrRegister("Demo")
    reg.add(_entry("1", consequence_class=4, probability_class=4))
    with pytest.raises(ValueError):
        reg.rerate("1", probability_class=2, basis=" ")
    with pytest.raises(KeyError):
        reg.rerate("9", probability_class=2, basis="test")
    reg.rerate("1", probability_class=2, basis="Test report TR-1 shows margin")
    result = reg.evaluate()
    assert result["rows"][0]["probability_class"] == 2
    assert result["history"][0]["risk"] == "High"
    assert result["history"][0]["probability_class"] == 4


def test_next_iteration_recorded():
    reg = FmirrRegister("Demo")
    reg.add(_entry("1"))
    reg.next_iteration()
    assert reg.evaluate()["iteration"] == 2


def test_lifecycle_gaps_listed():
    reg = FmirrRegister("Demo")
    reg.add(_entry("1", lifecycle_phase="design"))
    gaps = [f["text"] for f in reg.evaluate()["findings"] if "life-cycle phase" in f["text"]]
    assert len(gaps) == 6


def test_example_round_trip():
    result = from_dict(json.loads(EXAMPLE.read_text(encoding="utf-8"))).evaluate()
    summary = result["summary"]
    assert summary["total"] == 5
    assert summary["critical_ids"] == ["1.1.1", "1.2.1", "1.1.2"]
    assert summary["critical_without_test"] == 1
    json.dumps(result)


def test_from_dict_requires_technology():
    with pytest.raises(ValueError):
        from_dict({})
