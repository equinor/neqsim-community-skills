import json
from pathlib import Path

import pytest

from technology_assessment import (
    StepOutItem,
    TechnologyAssessment,
    TechnologyElement,
    categorize,
    classify_role,
    from_dict,
)

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "example_novel_technology.json"


@pytest.mark.parametrize(
    "novelty,area,qualified_by,label",
    [
        ("proven", "known", "none", "1"),
        ("limited_history", "known", "company", "2a"),
        ("proven", "limited_knowledge", "others", "2b"),
        ("limited_history", "known", "none", "2c"),
        ("limited_history", "limited_knowledge", "none", "3"),
        ("new", "known", "none", "3"),
        ("proven", "new", "none", "3"),
        ("new", "limited_knowledge", "none", "4"),
        ("limited_history", "new", "none", "4"),
        ("new", "new", "none", "4"),
    ],
)
def test_categorize_matrix(novelty, area, qualified_by, label):
    assert categorize(novelty, area, qualified_by).label == label


def test_category_one_and_2a_need_no_qualification():
    assert not categorize("proven", "known").qualification_required
    assert not categorize("limited_history", "known", "company").qualification_required
    assert categorize("new", "new").qualification_required


def test_categorize_rejects_unknown_values():
    with pytest.raises(ValueError):
        categorize("novel", "known")
    with pytest.raises(ValueError):
        categorize("proven", "known", "vendor")


def test_role_classification():
    assert classify_role(True, False)["role"] == "enabling"
    assert classify_role(True, True)["role"] == "enhancing"
    assert classify_role(False, False)["role"] == "enhancing"


def _basic():
    ta = TechnologyAssessment("Demo")
    ta.add_element(TechnologyElement("A", "System", technology_novelty="new", trl=2, evidence=("x",)))
    ta.add_element(TechnologyElement("B", "Part", parent_id="A", technology_novelty="proven", trl=7))
    return ta


def test_system_trl_is_minimum_of_elements():
    assert _basic().assess()["summary"]["system_trl"] == 2


def test_interfaces_untested_lowers_system_trl():
    ta = TechnologyAssessment("Demo", interfaces_untested=True)
    ta.add_element(TechnologyElement("A", "S", technology_novelty="new", trl=3, evidence=("x",)))
    assert ta.assess()["summary"]["system_trl"] == 2


def test_system_trl_override_cannot_exceed_minimum():
    ta = TechnologyAssessment("Demo", system_trl_override=5, system_trl_override_rationale="r")
    ta.add_element(TechnologyElement("A", "S", technology_novelty="new", trl=3))
    with pytest.raises(ValueError):
        ta.assess()


def test_override_requires_rationale():
    with pytest.raises(ValueError):
        TechnologyAssessment("Demo", system_trl_override=1)


def test_duplicate_and_invalid_elements_rejected():
    ta = _basic()
    with pytest.raises(ValueError):
        ta.add_element(TechnologyElement("A", "dup"))
    with pytest.raises(ValueError):
        ta.add_element(TechnologyElement("C", "bad", trl=8))
    with pytest.raises(ValueError):
        ta.add_element(TechnologyElement("D", "bad", technology_novelty="odd"))


def test_unknown_parent_and_cycle_detected():
    ta = TechnologyAssessment("Demo")
    ta.add_element(TechnologyElement("A", "A", parent_id="Z"))
    with pytest.raises(ValueError):
        ta.assess()
    ta = TechnologyAssessment("Demo")
    ta.add_element(TechnologyElement("A", "A", parent_id="B"))
    ta.add_element(TechnologyElement("B", "B", parent_id="A"))
    with pytest.raises(ValueError):
        ta.assess()


def test_empty_assessment_rejected():
    with pytest.raises(ValueError):
        TechnologyAssessment("Demo").assess()


def test_consistency_flags():
    ta = TechnologyAssessment("Demo")
    ta.add_element(TechnologyElement("P", "proven low trl", technology_novelty="proven", trl=3))
    ta.add_element(TechnologyElement("N", "novel trl7", technology_novelty="new", trl=7, evidence=("e",)))
    ta.add_element(TechnologyElement("E", "novel no evidence", technology_novelty="new", trl=1))
    flags = " ".join(ta.assess()["flags"])
    assert "P: Category 1 (proven) but TRL < 7" in flags
    assert "N: TRL 7 but novelty category >= 2" in flags
    assert "E: Novel element without documented evidence" in flags


def test_step_out_max_and_min_directions():
    ta = _basic()
    ta.add_step_out(StepOutItem("design", reference_value=10, proposed_value=20, unit="m"))
    ta.add_step_out(
        StepOutItem("operating_conditions", reference_value=-5, proposed_value=-20, direction="min")
    )
    ta.add_step_out(StepOutItem("fluids", reference_value=100, proposed_value=80))
    ta.add_step_out(StepOutItem("lifetime", proposed="25 years"))
    rows = {r["dimension"]: r for r in ta.assess()["step_out"]}
    assert rows["design"]["status"] == "step-out beyond experience"
    assert rows["design"]["ratio"] == pytest.approx(2.0)
    assert rows["operating_conditions"]["status"] == "step-out beyond experience"
    assert rows["fluids"]["status"] == "within experience"
    assert rows["lifetime"]["status"].startswith("qualitative")


def test_step_out_without_documented_experience_is_a_data_gap():
    ta = _basic()
    ta.add_step_out(StepOutItem("fluids", proposed="43 mol% CO2", experience_documented=False))
    ta.add_step_out(StepOutItem("design", reference_value=10, proposed_value=5, experience_documented=False))
    result = ta.assess()
    rows = {r["dimension"]: r for r in result["step_out"]}
    assert rows["fluids"]["status"] == "no documented experience basis"
    assert rows["design"]["status"] == "within experience"  # numeric comparison wins
    gaps = " ".join(result["data_gaps"])
    assert "Step-out fluids: no documented experience basis" in gaps
    assert "Step-out design: no documented experience basis" in gaps


def test_from_dict_reads_experience_documented():
    spec = {
        "technology": "T",
        "elements": [{"id": "A", "name": "A"}],
        "step_out": [{"dimension": "lifetime", "experience_documented": False}],
    }
    row = from_dict(spec).assess()["step_out"][0]
    assert row["experience_documented"] is False and row["status"] == "no documented experience basis"


def test_data_gaps_list_missing_step_out_dimensions_and_basis():
    gaps = " ".join(_basic().assess()["data_gaps"])
    assert "No step-out defined for installation" in gaps
    assert "No benefits recorded" in gaps
    assert "Qualification basis: technology description missing" in gaps


def test_qualification_outline_skips_proven_and_targets_trl4():
    outline = _basic().assess()["qualification_outline"]
    assert [o["element_id"] for o in outline] == ["A"]
    assert outline[0]["target_trl"] == 4
    assert outline[0]["activities"]


def test_example_json_round_trip():
    spec = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    result = from_dict(spec).assess()
    summary = result["summary"]
    assert result["schema_version"] == "technology_assessment.v1"
    assert summary["role"] == "enabling"
    assert summary["highest_category"] == 4
    assert summary["system_trl"] == 1  # min 2 minus one for untested interfaces
    labels = {e["id"]: e["category_label"] for e in result["elements"]}
    assert labels == {"S": "3", "S.1": "2b", "S.2": "4", "S.3": "1", "S.4": "2a"}
    statuses = {r["dimension"]: r["status"] for r in result["step_out"]}
    assert statuses["design"] == "step-out beyond experience"
    json.dumps(result)


def test_from_dict_requires_technology():
    with pytest.raises(ValueError):
        from_dict({})
