"""Basic concept long-list to short-list screening example."""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from concept_longlist_shortlist import generate_long_list, run_screening  # noqa: E402

ELEMENTS = {
    "host": ["fpso", "semi_submersible", "subsea_tieback", "subsea_to_shore"],
    "wells": ["subsea"],
    "oil_export": ["shuttle_tanker", "pipeline", "via_host"],
    "gas_disposal": ["reinjection", "export_pipeline", "via_host"],
    "drive": ["water_injection"],
    "power": ["gas_turbine", "power_from_shore", "power_from_host"],
}

long_list = generate_long_list(ELEMENTS, givens={"drive": "water_injection"})
ids = [c["id"] for c in long_list["concepts"]]

# Illustrative screening-level scores; replace with results from the
# capex-opex, npv and energy-emissions screening skills.
scores = {}
for i, cid in enumerate(ids):
    scores[cid] = {
        "npv": 3.0 + (i % 5) * 0.6,
        "capex": 4.0 + (i % 4) * 0.8,
        "co2": 20.0 - (5.0 if "power_from_shore" in cid else 0.0) - i % 3,
        "maturity": 3 if "fpso" in cid else 2,
    }

study = {
    "elements": ELEMENTS,
    "givens": {"drive": "water_injection"},
    "must_pass": [{"id": "host_reach", "name": "Existing host within tie-back reach"}],
    "assessments": {
        cid: {
            "host_reach": (
                {"result": "fail", "evidence": "No host within 60 km (illustrative)"}
                if cid.startswith("subsea_tieback")
                else {"result": "pass", "evidence": "Standalone concept, no host needed"}
            )
        }
        for cid in ids
    },
    "criteria": [
        {"id": "npv", "weight": 0.4},
        {"id": "capex", "weight": 0.2, "direction": "cost"},
        {"id": "co2", "weight": 0.2, "direction": "cost"},
        {"id": "maturity", "weight": 0.2},
    ],
    "scores": scores,
    "reference": [ids[0]],
    "short_list_size": 3,
}

result = run_screening(study)
print(json.dumps({k: result[k] for k in ("readiness", "short_list", "warnings")}, indent=2))
