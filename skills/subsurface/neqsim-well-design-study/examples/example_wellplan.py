"""Well-plan example with synthetic numbers only: schematic sheet, BOP and barrier sketches, Gantt, risk matrix, decision tree and a professional report.

Run: python examples/example_wellplan.py OUTPUT_FOLDER
Nothing here refers to a real well; all values are placeholders for the layout.
"""

import datetime as dt
import sys
from pathlib import Path

import numpy as np

from well_design_study import wellplan_charts as wc
from well_design_study import wellplan_graphics as wg
from well_design_study.report import WellPlanReport

out = Path(sys.argv[1] if len(sys.argv) > 1 else "wellplan_example")
out.mkdir(parents=True, exist_ok=True)
z = np.arange(400.0, 4100.0, 50.0)
strings = [
    {"name": '36" conductor', "casing_od_in": 36.0, "hole_in": 42.0, "hole_label": "26 in x 42 in", "top_tvd_m": 374.0, "hole_top_tvd_m": 374.0, "shoe_tvd_m": 450.0, "toc_tvd_m": 375.0,
     "mud_type": "seawater", "mud_sg": 1.03, "riserless": True, "status": "ASSUMED", "pipe": "example grade"},
    {"name": '20" casing', "casing_od_in": 20.0, "hole_in": 26.0, "top_tvd_m": 374.0, "hole_top_tvd_m": 450.0, "shoe_tvd_m": 1300.0, "toc_tvd_m": 375.0, "mud_type": "WBM", "mud_sg": 1.20,
     "status": "DERIVED", "pipe": "example grade", "riserless": True},
    {"name": '13 3/8" liner', "casing_od_in": 13.375, "hole_in": 17.5, "top_tvd_m": 1250.0, "hole_top_tvd_m": 1300.0, "shoe_tvd_m": 2600.0, "toc_tvd_m": 1250.0, "liner": True, "mud_type": "OBM",
     "mud_sg": 1.40, "status": "VERIFIED", "pipe": "example grade"},
    {"name": "8 1/2 in open hole", "casing_od_in": None, "hole_in": 8.5, "top_tvd_m": 2600.0, "hole_top_tvd_m": 2600.0, "shoe_tvd_m": 4000.0, "mud_type": "OBM", "mud_sg": 1.60, "status": "UNVERIFIED-SOURCE"},
]
spec = {
    "well": "SYN-1 WELL SCHEMATIC", "subtitle": "synthetic example, not a real well", "rig": "semi-submersible (example)", "water_depth_m": 350.0, "air_gap_m": 25.0, "td_md_m": 4000.0,
    "td_tvd_m": 4000.0, "strings": strings, "tops": [("Top A", 1800.0), ("Top B", 2900.0), ("Top C", 3500.0)], "target": ("Reservoir\n(example)", 3800.0),
    "tracks": {"z": z, "pore_low": np.full_like(z, 1.03), "pore_base": np.linspace(1.03, 1.25, z.size), "pore_high": np.linspace(1.03, 1.4, z.size), "frac_low": np.linspace(1.4, 1.8, z.size),
               "frac_base": np.linspace(1.5, 1.9, z.size), "frac_high": np.linspace(1.6, 2.0, z.size)},
    "bop": {"label": "BOP stack\n(example)"}, "notes": ["All numbers are synthetic placeholders.", "Status colours show VERIFIED / UNVERIFIED-SOURCE / DERIVED / ASSUMED."],
    "title_block": {"title": "WELL SCHEMATIC - SYN-1", "subtitle": "example", "doc_id": "SYN-WPLAN-001", "rev": "A", "date": "2026-01-01", "status": "DRAFT", "classification": "PUBLIC"},
    "revisions": [("A", "2026-01-01", "first issue", "")],
}
sheet = wg.well_schematic_sheet(spec, out / "sheet.png")
risks = [{"id": f"R{i:02d}", "short": f"example risk {i}", "event": f"example risk {i}", "likelihood": 1 + i % 5, "severity": 1 + (2 * i) % 5, "res_likelihood": max(1, i % 5), "res_severity": 1 + (2 * i) % 5}
         for i in range(1, 7)]
rm = wc.risk_matrix(risks, out / "risk.png")
gantt = wc.gantt_chart([{"name": "Section A", "p50": 6, "p10": 5, "p90": 9}, {"name": "Section B", "p50": 12, "p10": 9, "p90": 18}, {"name": "NPT allowance", "p50": 4, "p10": 0, "p90": 14, "kind": "npt"}],
                       out / "gantt.png", spud_date=dt.date(2027, 5, 1), total={"p10": 18, "p50": 24, "p90": 38})
rep = WellPlanReport("Well Plan", "SYN-1 (synthetic example)", "SYN-WPLAN-001", "A", "2026-01-01", "DRAFT", "PUBLIC", organisation="Example Co", notice="Synthetic example; no real data.")
rep.h1("Summary and key data", page_break=False)
rep.key_data_box("Key data", [("Well", "SYN-1"), ("Water depth", "350 m [ASSUMED]"), ("TD", "4000 m [ASSUMED]"), ("Days P10/P50/P90", "18 / 24 / 38 [DERIVED]")])
rep.table([["Section", "Hole (in)", "Shoe (m)"], ["conductor", "42", "450"], ["casing", "26", "1300"]], "Hole sections", note="synthetic")
rep.figure(gantt, "Operations plan", "provenance: synthetic")
rep.figure(rm, "Risk matrix", "provenance: synthetic")
rep.sheet_page(sheet, "Well schematic sheet", "provenance: synthetic")
print(rep.save(out / "wellplan_example.docx"))
