import json
import os

import pytest

from subsea_slot_tee_reuse import (
    INVENTORY_SCHEMA,
    free_slot_table,
    handoff,
    items_from_sodir,
    lifetime_check,
    normalize_item,
    rank_reuse_options,
    reusable_lines,
    screening_dp_bar,
    summarize,
    validate_inventory,
)
from subsea_slot_tee_reuse.__main__ import main as cli_main
from subsea_slot_tee_reuse.inventory import schema_path

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLES = os.path.join(os.path.dirname(HERE), "examples")


def load(name):
    with open(os.path.join(EXAMPLES, name), encoding="utf-8") as fh:
        return json.load(fh)


def test_example_inventory_is_valid_and_summarised():
    inv = load("example_inventory.json")
    issues = validate_inventory(inv, 2026)
    assert not [i for i in issues if i["level"] == "error"]
    # the estimated free slot and the "believed spare" line must be flagged, not accepted silently
    messages = " ".join(i["message"] for i in issues)
    assert "not documented" in messages and "spare claimed without" not in messages
    s = summarize(inv, 2026)
    assert s["by_status"]["spare"] == 2 and s["free_slots_by_verification"] == {"documented": 3, "estimated": 1}
    assert s["spare_line_km_by_service"]["oil"] == 9.5


def test_free_slot_table_only_documented_slots_are_usable_as_free():
    rows = {r["id"]: r for r in free_slot_table(load("example_inventory.json"), 2026)}
    assert rows["TMPL-1"]["usable_as_free"] and rows["TMPL-1"]["in_use_slots"] == 4
    assert not rows["TMPL-2"]["usable_as_free"]


def test_validation_errors():
    bad = {"schema": INVENTORY_SCHEMA, "items": [{"id": "T", "kind": "template", "status": "spare", "total_slots": 2, "free_slots": 5, "verification": "nonsense"},
                                                 {"id": "T", "kind": "pipeline", "status": "maybe"}]}
    msgs = [i["message"] for i in validate_inventory(bad, 2026) if i["level"] == "error"]
    assert any("duplicate" in m for m in msgs) and any("exceeds" in m for m in msgs) and any("verification" in m for m in msgs) and any("status" in m for m in msgs)
    assert validate_inventory({"schema": "x", "items": []})[0]["level"] == "error"


def test_schema_file_validates_example_inventory():
    jsonschema = pytest.importorskip("jsonschema")
    with open(schema_path(), encoding="utf-8") as fh:
        schema = json.load(fh)
    jsonschema.validate(load("example_inventory.json"), schema)
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate({"schema": INVENTORY_SCHEMA, "items": [{"id": "x", "kind": "teleporter", "status": "spare", "verification": "documented", "source": "s"}]}, schema)


def test_remaining_life_is_derived_and_lifetime_actions():
    it = normalize_item({"id": "L", "kind": "flowline", "install_year": 1995, "design_life_years": 25}, 2026)
    assert it["remaining_life_years"] == -6.0
    assert lifetime_check(normalize_item({"id": "a", "remaining_life_years": 30}, 2026), 2045, 2026)["action"] == "ok"
    assert lifetime_check(normalize_item({"id": "b", "remaining_life_years": 20}, 2026), 2045, 2026)["action"] == "monitor"
    assert lifetime_check(normalize_item({"id": "c", "remaining_life_years": 12}, 2026), 2045, 2026)["action"] == "life-extend"
    assert lifetime_check(normalize_item({"id": "d", "remaining_life_years": 2}, 2026), 2045, 2026)["action"] == "refurbish"
    assert lifetime_check(normalize_item({"id": "e", "remaining_life_years": -6}, 2026), 2045, 2026)["action"] == "replace"
    assert lifetime_check(normalize_item({"id": "f"}, 2026), 2045, 2026)["action"] == "data-gap"
    assert lifetime_check(normalize_item({"id": "g", "remaining_life_years": 17, "condition": "poor"}, 2026), 2045, 2026)["action"] == "refurbish"


def test_dp_screening_scales_with_length_and_size():
    rate = {"value": 3000, "unit": "Sm3/d"}
    a = screening_dp_bar("oil", rate, 8, 10)
    assert a == pytest.approx(screening_dp_bar("oil", rate, 8, 20) / 2)
    assert screening_dp_bar("oil", rate, 12, 10) < a / 5
    assert screening_dp_bar("oil", rate, None, 10) is None


def test_ranking_prefers_documented_slot_over_estimated_and_reports_lifetime():
    ranking = rank_reuse_options(load("example_inventory.json"), load("example_target.json"), 2026)
    ids = [r["id"] for r in ranking]
    assert "new-build" in ids and ids[0] != "new-build"
    by = {r["id"]: r for r in ranking}
    assert by["TMPL-1"]["score"] > by["TMPL-2"]["score"]  # nearer, documented, longer life
    assert any("confirm with the owner" in f for f in by["TMPL-2"]["flags"])
    assert by["FL-OLD"]["lifetime"]["action"] in ("replace", "refurbish")  # 1995 + 25 years is past the horizon
    assert by["FL-OLD"]["option_type"] == "reuse_line"
    assert by["TMPL-1"]["advantage_vs_new_build"] > 0
    assert all(r["rank"] == i + 1 for i, r in enumerate(sorted(ranking, key=lambda r: r["rank"])))


def test_service_conversion_and_rating_flags():
    inv = load("example_inventory.json")
    target = load("example_target.json")
    target["design_pressure_bar"] = 450
    ranking = {r["id"]: r for r in rank_reuse_options(inv, target, 2026)}
    assert any("rating" in f for f in ranking["WI-1"]["flags"])
    assert any("conversion" in f for f in ranking["WI-1"]["flags"])
    assert ranking["WI-1"]["components"]["compatibility"] < 0.3


def test_arrival_pressure_penalises_long_small_lines():
    inv = load("example_inventory.json")
    target = load("example_target.json")
    target["rate"] = {"value": 20000, "unit": "Sm3/d"}
    target["source_pressure_bar"] = 40
    ranking = {r["id"]: r for r in rank_reuse_options(inv, target, 2026)}
    assert ranking["GL-1"]["components"]["hydraulics"] <= ranking["FL-OLD"]["components"]["hydraulics"]
    assert any("arrival pressure" in f or "erosional" in f for f in ranking["GL-1"]["flags"])


def test_handoffs_have_consumer_specific_content():
    inv, target = load("example_inventory.json"), load("example_target.json")
    ranking = rank_reuse_options(inv, target, 2026)
    assert handoff(ranking, target, "export-tie-in-concept")["candidate_landing_points"]
    assert "reused_equipment" in handoff(ranking, target, "surf-design-study")
    assert "flow_assurance_flags" in handoff(ranking, target, "tie-in-screening")
    h = handoff(ranking, target, "area-development")
    assert h["human_review_required"] and h["options"][0]["cost_class"].startswith("AACE class 5")
    with pytest.raises(ValueError):
        handoff(ranking, target, "nobody")


def test_sodir_adapter_never_calls_open_data_spare():
    facilities = [{"fclName": "Template X", "fclKind": "SUBSEA TEMPLATE", "fclPhase": "IN SERVICE", "fclWaterDepth": 300, "fclStartupDate": "2004-05-01"},
                  {"fclName": "Platform P", "fclKind": "FIXED", "fclPhase": "IN SERVICE"}]
    pipelines = [{"pplName": "Line 1", "pplMedium": "GAS", "pplDimension": 12, "fclNameFrom": "Template X", "fclNameTo": "Platform P", "pplCurrentPhase": "IN SERVICE"},
                 {"pplName": "Line 0", "pplMedium": "OIL", "pplDimension": 10, "pplCurrentPhase": "SHUT DOWN"}]
    items = items_from_sodir(facilities, pipelines, wells_per_facility={"Template X": 3}, nominal_slots={"Template X": 4}, as_of_year=2026)
    by = {i["id"]: i for i in items}
    assert set(by) == {"Template X", "Line 1", "Line 0"}
    assert by["Template X"]["free_slots"] == 1 and by["Template X"]["verification"] == "estimated"
    assert by["Line 1"]["status"] == "in_use" and by["Line 0"]["status"] == "abandoned"
    assert not [i for i in items if i["status"] == "spare"]
    assert by["Template X"]["remaining_life_years"] is None  # no design life published: data gap, not a guess
    assert reusable_lines({"items": items}, 2026, statuses=("abandoned",))[0]["id"] == "Line 0"


def test_cli(capsys):
    assert cli_main([os.path.join(EXAMPLES, "example_inventory.json"), os.path.join(EXAMPLES, "example_target.json"), "--consumer", "area-development", "--year", "2026"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ranking"][0]["rank"] == 1 and out["handoff"]["consumer"] == "area-development"
