import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from stage_gate_project_timeline import (
    discounted,
    life_extension_timeline,
    next_turnaround,
    portfolio_plan,
    project_timeline,
    prospect_timeline,
)


def test_undrilled_prospect_cannot_produce_before_six_years_and_lands_on_a_turnaround():
    tl = prospect_timeline({"name": "P", "status": "undrilled"}, decision_year=2026)
    assert [p["phase"] for p in tl["phases"]] == ["exploration well", "appraisal", "DG1-DG2 concept", "DG3 FEED", "execution"]
    assert tl["exploration_year"] == 2027
    assert tl["phases"][-1]["end"] == 2032
    assert tl["first_production_year"] == 2033  # next biennial turnaround after 2033 is 2033
    assert tl["sanction_year"] == 2030


def test_discovered_prospect_skips_exploration_and_overrides_apply():
    tl = prospect_timeline({"name": "D", "status": "discovered", "phase_years": {"execution": 3}}, decision_year=2026)
    assert tl["exploration_year"] is None
    assert tl["phases"][-1]["end"] == 2032
    floor = prospect_timeline({"name": "D", "status": "sanctioned", "earliest_start_year": 2040}, decision_year=2026)
    assert floor["first_production_year"] == 2040


def test_project_asap_vs_just_in_time_moves_cost_later_but_not_earlier_than_asap():
    p = {"id": "x", "capex_musd": 60.0, "opex_musd_per_year": 1.0, "study_years": 1, "concept_years": 1, "execution_years": 2}
    asap = project_timeline(p, 2026, horizon_year=2040)
    assert asap["timing"] == "asap" and asap["available_year"] == 2031
    jit = project_timeline(p, 2026, needed_by=2036, horizon_year=2040)
    assert jit["timing"] == "just_in_time" and jit["available_year"] == 2035
    assert discounted(jit["cost_by_year_musd"], 0.08) < discounted(asap["cost_by_year_musd"], 0.08)
    early = project_timeline(p, 2026, needed_by=2029, horizon_year=2040)
    assert early["timing"] == "asap" and early["available_year"] == 2031
    # study cost in the study phase, the rest of capex in execution, opex from availability
    assert abs(asap["cost_by_year_musd"][2027] - 3.0) < 1e-9
    assert abs(sum(v for y, v in asap["cost_by_year_musd"].items() if 2029 <= y <= 2030) - 57.0) < 1e-9
    assert abs(asap["cost_by_year_musd"][2040] - 1.0) < 1e-9


def test_no_shutdown_project_is_available_right_after_execution():
    p = {"id": "w", "capex_musd": 10.0, "requires_shutdown": False, "execution_years": 1}
    assert project_timeline(p, 2026)["available_year"] == 2030


def test_life_extension_deadline_is_lead_years_before_programme_end_or_first_action():
    le = life_extension_timeline(2050, {2040: 207.0, 2044: 279.0}, decision_year=2026)
    assert le["decision_deadline"] == 2039
    assert le["phases"][0]["start"] == 2035 and le["phases"][1]["end"] == 2044
    empty = life_extension_timeline(2050, {}, decision_year=2026)
    assert empty["decision_deadline"] == 2045 and empty["phases"] == []


def test_portfolio_plan_slides_development_but_keeps_exploration_and_schedules_project_just_in_time():
    prospects = [{"name": "A", "status": "undrilled"}, {"name": "B", "status": "discovered"}]
    chosen = [{"prospect": "A", "start_year": 2037, "profile": {2037: {}, 2045: {}}}, {"prospect": "B", "start_year": 2033, "last_year": 2047}]
    projects = [{"id": "x", "capex_musd": 60.0}]
    plan = portfolio_plan(chosen, prospects, ["x"], projects, decision_year=2026)
    a = next(r for r in plan["rows"] if r["item"] == "A")
    assert a["exploration_year"] == 2027 and a["deferred_years"] == 4
    assert a["phases"][-2]["end"] == 2036 and a["phases"][-1] == {"phase": "production", "start": 2037, "end": 2045}
    x = next(r for r in plan["rows"] if r.get("kind") == "host_project")
    assert x["timing"] == "just_in_time" and x["available_year"] == 2033
    assert plan["capex_calendar_musd"] and any(m["milestone"].startswith("DG3") for m in plan["milestones"])


def test_next_turnaround_uses_custom_calendar():
    assert next_turnaround(2030, [2029, 2032]) == 2032
    assert next_turnaround(2033, [2029, 2032]) == 2033
