"""Screen gas export for a declared pre-salt block and check a host's compression limit."""

import brazil_offshore_infrastructure_market as bim

netback = bim.wellhead_netback(city_gate_usd_mmbtu=11.0)
for co2 in (6.5, 19.5, 34.1):
    print(
        "gas CO2 %.1f mol %% -> remove %.1f %% of gas moles"
        % (co2, 100 * bim.co2_removal_fraction(co2))
    )

upside = bim.gas_export_upside(350.0, 325.0, 0.5, netback, oil_net_price_usd_bbl=65.0)
print("gas export is %.1f %% of oil revenue" % upside["gas_pct_of_oil_revenue"])

check = bim.host_capacity_check(
    220.0, 102.5, compression_limit_kbd=123.0, additional_demand_kbd=30.0
)
print(check["binding_constraint"], check["ullage_kbd"], check["fits"])
print("data age (days):", bim.dataset_age_days())
for _ds, section, entry in bim.unknown_entries()[:3]:
    print("UNKNOWN:", section, entry.get("name") or entry.get("attribute"))
