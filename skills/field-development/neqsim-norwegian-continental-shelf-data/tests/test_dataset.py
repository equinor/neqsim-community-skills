import io

import pytest

from norwegian_continental_shelf_data import NcsDataset, load_dataset


def test_load_has_meta_and_attribution() -> None:
    ds = load_dataset()
    assert "norskpetroleum.no" in ds.attribution.lower()
    assert ds.snapshot_date
    assert "license" in ds.meta


def test_national_kpis_present_with_sources() -> None:
    ds = load_dataset()
    summary = ds.national_summary()
    assert "annual_production_oe" in summary
    prod = ds.national_kpi("annual_production_oe")
    assert prod["value"] == pytest.approx(239.2)
    assert prod["unit"] == "mill Sm3 o.e."
    assert prod["source_url"].startswith("https://www.norskpetroleum.no")


def test_unknown_national_kpi_raises() -> None:
    with pytest.raises(KeyError):
        load_dataset().national_kpi("no_such_kpi")


def test_resource_accounting_fractions_sum_to_one() -> None:
    ds = load_dataset()
    ra = ds.resource_accounting()
    produced = ra["produced_sold_delivered_fraction"]["value"]
    remaining = ra["remaining_fraction"]["value"]
    assert produced + remaining == pytest.approx(1.0, abs=1e-6)


def test_fields_load_and_filter() -> None:
    ds = load_dataset()
    fields = ds.fields()
    assert len(fields) >= 20
    barents = ds.list_fields(sea_area="barents_sea")
    assert {f.name for f in barents} >= {"Snohvit", "Goliat", "Johan Castberg"}
    gas = ds.list_fields(main_product="gas")
    assert all(f.main_product == "gas" for f in gas)


def test_filter_accepts_display_area_name() -> None:
    ds = load_dataset()
    by_id = ds.list_fields(sea_area="north_sea")
    by_name = ds.list_fields(sea_area="North Sea")
    assert {f.name for f in by_id} == {f.name for f in by_name}


def test_find_field_case_insensitive() -> None:
    ds = load_dataset()
    field = ds.find_field("johan sverdrup")
    assert field is not None
    assert field.operator == "Equinor"
    assert field.sea_area == "north_sea"
    assert ds.find_field("Not A Field") is None


def test_field_counts_totals_match() -> None:
    ds = load_dataset()
    counts = ds.field_counts()
    total_fields = len(ds.fields())
    assert sum(counts["by_sea_area"].values()) == total_fields
    assert sum(counts["by_main_product"].values()) == total_fields


def test_invalid_product_filter_raises() -> None:
    with pytest.raises(ValueError):
        load_dataset().list_fields(main_product="condensate")


def test_invalid_sea_area_raises() -> None:
    with pytest.raises(ValueError):
        load_dataset().list_fields(sea_area="atlantic")


def test_seed_annual_production_present() -> None:
    ds = load_dataset()
    series = ds.annual_production()
    assert series
    rec2025 = ds.production_for_year(2025)
    assert rec2025 is not None
    assert rec2025.oe_mill_sm3 == pytest.approx(239.2)


def test_ingest_annual_rows_and_derive_oe() -> None:
    ds = load_dataset()
    added = ds.ingest_annual_production(
        [
            {"year": 2000, "oil_mill_sm3": 181.2, "gas_bill_sm3": 49.7,
             "ngl_mill_sm3_oe": 10.0, "condensate_mill_sm3": 5.0},
        ]
    )
    assert added == 1
    rec = ds.production_for_year(2000)
    assert rec is not None
    # oe = oil + gas(bill=mill oe) + ngl + condensate
    assert rec.oe_mill_sm3 == pytest.approx(181.2 + 49.7 + 10.0 + 5.0)


def test_ingest_annual_requires_year() -> None:
    with pytest.raises(ValueError):
        load_dataset().ingest_annual_production([{"oe_mill_sm3": 100.0}])


def test_ingest_sodir_csv(tmp_path) -> None:
    csv_text = (
        "prfYear,prfPrdOilNetMillSm3,prfPrdGasNetBillSm3,"
        "prfPrdNGLNetMillSm3,prfPrdCondensateNetMillSm3,prfPrdOeNetMillSm3\n"
        "2010,90.0,106.0,15.0,3.0,214.0\n"
        "2011,88.0,101.0,14.0,2.5,205.5\n"
    )
    path = tmp_path / "prod.csv"
    path.write_text(csv_text, encoding="utf-8")
    ds = load_dataset()
    added = ds.ingest_sodir_production_csv(str(path))
    assert added == 2
    rec = ds.production_for_year(2010)
    assert rec is not None
    # prefers the provided o.e. column
    assert rec.oe_mill_sm3 == pytest.approx(214.0)
    assert rec.gas_bill_sm3 == pytest.approx(106.0)


def test_oil_equivalent_convention() -> None:
    oe = NcsDataset.oil_equivalent_mill_sm3(
        oil_mill_sm3=100.0,
        gas_bill_sm3=120.0,
        ngl_mill_sm3_oe=10.0,
        condensate_mill_sm3=5.0,
    )
    assert oe == pytest.approx(235.0)
