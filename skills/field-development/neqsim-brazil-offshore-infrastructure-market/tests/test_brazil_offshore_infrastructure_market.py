from datetime import date

import pytest

import brazil_offshore_infrastructure_market as bim


def test_datasets_load_with_sources_and_as_of() -> None:
    infra, market = bim.load_infrastructure(), bim.load_market()
    assert (
        infra["meta"]["as_of"] == "2026-10-14"
        and market["meta"]["as_of"] == "2026-10-14"
    )
    assert len(infra["pipelines"]) >= 8 and len(infra["plants"]) >= 4
    assert market["marketing"] and market["cost_benchmarks"] and market["declared"]


def test_every_source_id_resolves_and_is_prefixed() -> None:
    known = bim.sources()
    for _ds, _sec, entry in bim.iter_entries():
        raw = entry.get("source_id")
        for sid in [raw] if isinstance(raw, str) else (raw or []):
            assert sid.startswith(("INF-S", "MKT-S")), sid
            assert sid in known, sid
    assert bim.source_url("INF-S14").startswith("http")
    assert bim.source_url(None) is None and bim.source_url("INF-S999") is None


def test_every_entry_has_confidence_and_as_of() -> None:
    for _ds, sec, entry in bim.iter_entries():
        assert entry.get("confidence"), (sec, entry)
        assert entry.get("as_of") == "2026-10-14" or sec == "declared", (sec, entry)


def test_unknowns_are_explicit_not_zero() -> None:
    unknown = bim.unknown_entries()
    labels = " | ".join(
        str(e.get("name") or e.get("attribute")) for _d, _s, e in unknown
    )
    assert "Numeric Rota 1/2/3 offshore export tariff" in labels
    assert "Numeric UTGCA/UTGCAB/Boaventura processing tariff" in labels
    tariff = bim.find("Numeric Rota 1/2/3", section="tariffs")[0][2]
    assert tariff["value"] is None and bim.is_unknown(tariff)
    assert not bim.is_unknown(bim.find("Rota 2", section="pipelines")[0][2])


def test_key_public_facts() -> None:
    co2 = bim.find("CO2 max", section="market")[0][2]
    assert co2["value"] == 3.0 and co2["unit"] == "mol %"
    share = bim.find("Escoamento plus processing share", section="tariffs")[0][2]
    assert share["value"] == 46
    rota3 = bim.find("Rota 3", section="pipelines")[0][2]
    assert rota3["capacity"]["value"] == 18
    bac = bim.find("fpso_oil_capacity", section="fields")[0][2]
    assert bac["value"] == 220000


def test_dataset_age_flags_stale_data() -> None:
    assert bim.dataset_age_days(date(2026, 10, 14)) == 0
    assert bim.dataset_age_days(date(2027, 1, 12)) == 90


def test_co2_removal_fraction() -> None:
    assert bim.co2_removal_fraction(19.5) == pytest.approx((0.195 - 0.03) / 0.97)
    assert bim.co2_removal_fraction(2.0) == 0.0
    assert bim.co2_removal_fraction(34.1, spec_mol_pct=3.0) == pytest.approx(
        0.3206, abs=1e-3
    )
    with pytest.raises(ValueError):
        bim.co2_removal_fraction(120.0)


def test_wellhead_netback_uses_mme_share() -> None:
    assert bim.wellhead_netback(11.0) == pytest.approx(5.94)
    assert bim.wellhead_netback(11.0, 0.0) == 11.0
    with pytest.raises(ValueError):
        bim.wellhead_netback(11.0, 1.5)


def test_gas_export_upside_is_small_vs_oil() -> None:
    r = bim.gas_export_upside(
        350.0, 325.0, 0.5, bim.wellhead_netback(11.0), oil_net_price_usd_bbl=65.0
    )
    assert r["gas_produced_gsm3"] == pytest.approx(350e6 * 0.158987 * 325 / 1e9)
    assert 5.0 < r["gas_pct_of_oil_revenue"] < 12.0
    assert bim.gas_export_upside(0.0, 325.0, 0.5, 5.9)["gross_gas_revenue_musd"] == 0.0
    with pytest.raises(ValueError):
        bim.gas_export_upside(100.0, 300.0, 1.5, 5.0)


def test_host_capacity_compression_binds_before_nameplate() -> None:
    plain = bim.host_capacity_check(220.0, 102.5)
    assert plain["binding_constraint"] == "oil_nameplate" and plain[
        "ullage_kbd"
    ] == pytest.approx(117.5)
    limited = bim.host_capacity_check(
        220.0, 102.5, compression_limit_kbd=123.0, additional_demand_kbd=30.0
    )
    assert limited["binding_constraint"] == "gas_compression"
    assert limited["ullage_kbd"] == pytest.approx(20.5)
    assert limited["ullage_overstatement_kbd"] == pytest.approx(97.0)
    assert limited["fits"] is False
    assert bim.host_capacity_check(220.0, 300.0)["ullage_kbd"] == 0.0
    # a limit above nameplate does not relax nameplate
    assert (
        bim.host_capacity_check(100.0, 50.0, compression_limit_kbd=500.0)[
            "effective_limit_kbd"
        ]
        == 100.0
    )
