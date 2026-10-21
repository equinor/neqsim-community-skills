"""Synthetic end-to-end JV cost-control example (no operator data)."""

import logging

import pandas as pd

from jv_cost_control import (
    check_subtotals,
    interest_share_check,
    parse_hierarchical_rows,
    price_volume_split,
    reconcile_tables,
    variance_commentary,
    variance_table,
)

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("jv_example")

rows = [
    ["Area A", "EXPENDITURES", "Drilling", None, 10.0, 100.0, 1.2, 12.0],
    [None, None, None, None, 20.0, 200.0, 2.4, 24.0],
    [None, None, "TOTAL Drilling", None, 30.0, 300.0, 3.6, 36.0],
    [None, None, "Operations", None, 8.0, 60.0, 1.0, 7.2],
    [None, None, "TOTAL Operations", None, 8.0, 60.0, 1.0, 7.2],
    [None, "TOTAL EXPENDITURES", None, None, 38.0, 360.0, 4.6, 43.2],
]
values = {"cm": 4, "ytd": 5, "cm_sh": 6, "ytd_sh": 7}
parsed = parse_hierarchical_rows(rows, range(4), values)
log.info("totals that do not tie: %d", len(check_subtotals(parsed)))

detail = parsed.detail.assign(budget=[90.0, 150.0, 40.0])
table = variance_table(detail, "ytd", "budget", ["L2"], abs_threshold=10.0, pct_threshold=0.1)
for item in variance_commentary(table, ["L2"], "ytd", "budget", unit="MUSD"):
    log.info(item["fact"])

pi = interest_share_check(detail, "cm", "cm_sh", [0.12, 0.12 / 0.9])
log.info("lines outside the expected PI: %d", len(pi))

other = pd.DataFrame({"L2": ["Drilling", "Operations"], "ytd": [300.0, 55.0]})
recon = reconcile_tables(detail, other, ["L2"], "ytd", "ytd", names=("jib", "report"))
log.info("reconciliation:\n%s", recon.to_string(index=False))
log.info("unit-cost split: %s", price_volume_split(415.6, 38.4, 360.9, 40.3))
