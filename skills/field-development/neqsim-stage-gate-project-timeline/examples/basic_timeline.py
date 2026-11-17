"""Plan a two-prospect tie-in portfolio with one host modification and a life-extension window, and print the Gantt rows."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from stage_gate_project_timeline import (
    life_extension_timeline,
    portfolio_plan,
    project_timeline,
    prospect_timeline,
)

prospects = [{"name": "Discovery A", "status": "discovered"}, {"name": "Prospect B", "status": "undrilled"}]
for p in prospects:
    tl = prospect_timeline(p, decision_year=2026)
    print("{:12s} earliest first oil {}  (DG3 {})".format(p["name"], tl["first_production_year"], tl["sanction_year"]))

project = {"id": "oil_train", "name": "Oil train debottleneck", "capex_musd": 60.0, "opex_musd_per_year": 1.0,
           "study_years": 1, "concept_years": 1, "execution_years": 2}
for needed in (None, 2036):
    tl = project_timeline(project, 2026, needed_by=needed, horizon_year=2045)
    print("project {:13s} available {}  cost by year {}".format(tl["timing"], tl["available_year"],
          {y: round(v, 1) for y, v in tl["cost_by_year_musd"].items() if v > 1.0}))

le = life_extension_timeline(2050, {2040: 207.0, 2044: 279.0}, decision_year=2026)
print("life extension decision deadline", le["decision_deadline"])

chosen = [{"prospect": "Discovery A", "start_year": 2033, "last_year": 2046}, {"prospect": "Prospect B", "start_year": 2036, "last_year": 2050}]
plan = portfolio_plan(chosen, prospects, ["oil_train"], [project], life_extension=le, decision_year=2026)
for r in plan["rows"]:
    print(r["item"], [(p["phase"], p["start"], p["end"]) for p in r["phases"]])
print(json.dumps(plan["milestones"]))
