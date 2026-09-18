import pytest

from norwegian_continental_shelf_data import (
    NcsDataset,
    load_dataset,
    rank_fields_by_remaining,
    remaining_reserves_by_area,
    sodir_download_plan,
    refresh_instructions,
    NORSKPETROLEUM_QUICK_DOWNLOADS,
    SODIR_FACTPAGES,
)


def test_seed_fields_have_no_invented_reserves() -> None:
    ds = load_dataset()
    for f in ds.fields():
        assert f.recoverable_oe_mill_sm3 is None
        assert f.remaining_oe_mill_sm3 is None
        assert f.cumulative_produced_oe_mill_sm3 is None


def test_ngl_tonne_conversion() -> None:
    # 1 tonne NGL = 1.9 Sm3 o.e.; 10 mill tonne => 19 mill Sm3 o.e.
    assert NcsDataset.ngl_tonne_to_sm3_oe(10.0) == pytest.approx(19.0)


def test_ingest_field_reserves_overlay_and_derived_produced() -> None:
    ds = load_dataset()
    added = ds.ingest_field_reserves(
        [
            {
                "name": "Johan Sverdrup",
                "recoverable_oe_mill_sm3": 430.0,
                "remaining_oe_mill_sm3": 300.0,
            }
        ]
    )
    assert added == 1
    js = ds.find_field("johan sverdrup")
    assert js is not None
    assert js.recoverable_oe_mill_sm3 == pytest.approx(430.0)
    assert js.remaining_oe_mill_sm3 == pytest.approx(300.0)
    # produced derived when both present
    assert js.cumulative_produced_oe_mill_sm3 == pytest.approx(130.0)


def test_ingest_field_reserves_requires_name() -> None:
    with pytest.raises(ValueError):
        load_dataset().ingest_field_reserves([{"remaining_oe_mill_sm3": 10.0}])


def test_ingest_sodir_field_reserves_csv_with_components(tmp_path) -> None:
    csv_text = (
        "fldName,fldRecoverableOil,fldRecoverableGas,fldRecoverableNGL,"
        "fldRecoverableCondensate,fldRemainingOE\n"
        "Troll,120.0,1000.0,20.0,5.0,900.0\n"
    )
    path = tmp_path / "reserves.csv"
    path.write_text(csv_text, encoding="utf-8")
    ds = load_dataset()
    added = ds.ingest_sodir_field_reserves_csv(str(path))
    assert added == 1
    troll = ds.find_field("Troll")
    assert troll is not None
    # recoverable oe = oil + gas(bill=oe) + ngl_tonne*1.9 + condensate
    expected = 120.0 + 1000.0 + 20.0 * 1.9 + 5.0
    assert troll.recoverable_oe_mill_sm3 == pytest.approx(expected)
    assert troll.remaining_oe_mill_sm3 == pytest.approx(900.0)


def test_rank_and_aggregate_remaining_reserves() -> None:
    ds = load_dataset()
    ds.ingest_field_reserves(
        [
            {"name": "Troll", "remaining_oe_mill_sm3": 900.0},
            {"name": "Johan Sverdrup", "remaining_oe_mill_sm3": 300.0},
            {"name": "Snohvit", "remaining_oe_mill_sm3": 120.0},
        ]
    )
    ranked = rank_fields_by_remaining(ds.fields(), top=2)
    assert [f.name for f in ranked] == ["Troll", "Johan Sverdrup"]

    totals = remaining_reserves_by_area(ds.fields())
    assert totals["north_sea"] == pytest.approx(1200.0)  # Troll + Sverdrup
    assert totals["barents_sea"] == pytest.approx(120.0)  # Snohvit


def test_download_plan_and_refresh_instructions() -> None:
    plan = sodir_download_plan()
    datasets = {t.dataset for t in plan}
    assert {"field_production_yearly", "field_reserves"} <= datasets
    reserves = next(t for t in plan if t.dataset == "field_reserves")
    assert "ingest_sodir_field_reserves_csv" in reserves.ingest_with
    assert reserves.factpages_page_url.startswith("https://factpages.sodir.no/")

    text = refresh_instructions()
    assert NORSKPETROLEUM_QUICK_DOWNLOADS in text
    assert SODIR_FACTPAGES in text
    assert "attribution" in text.lower()
