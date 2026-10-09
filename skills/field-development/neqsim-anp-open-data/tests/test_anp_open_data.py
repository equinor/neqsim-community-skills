import math

import pytest

from anp_open_data import (
    OIL_M3_TO_BBL,
    check_crs,
    gas_volume,
    haversine_km,
    load_table,
    monthly_to_daily,
    oil_volume,
)


def test_oil_and_gas_unit_conversion() -> None:
    assert oil_volume(1.0, "m3", "bbl") == pytest.approx(OIL_M3_TO_BBL)
    assert oil_volume(OIL_M3_TO_BBL, "bbl", "m3") == pytest.approx(1.0)
    assert gas_volume(1.0, "thousand_m3", "sm3") == pytest.approx(1000.0)
    assert gas_volume(1.0e6, "sm3", "million_m3") == pytest.approx(1.0)
    with pytest.raises(ValueError):
        oil_volume(1.0, "barrels", "m3")
    with pytest.raises(ValueError):
        gas_volume(1.0, "m4", "sm3")


def test_monthly_to_daily_uses_real_month_length() -> None:
    assert monthly_to_daily(310.0, 2026, 1) == pytest.approx(10.0)
    assert monthly_to_daily(280.0, 2026, 2) == pytest.approx(10.0)
    assert monthly_to_daily(290.0, 2024, 2) == pytest.approx(10.0)
    with pytest.raises(ValueError):
        monthly_to_daily(1.0, 2026, 13)


def test_haversine_known_distance() -> None:
    # one degree of latitude is about 111.2 km
    assert haversine_km(0.0, 0.0, 0.0, 1.0) == pytest.approx(111.19, abs=0.1)
    assert haversine_km(-43.0, -24.0, -43.0, -24.0) == 0.0


def test_check_crs() -> None:
    assert check_crs(None)["status"] == "unknown"
    assert check_crs("epsg:4674")["status"] == "geographic"
    assert check_crs("EPSG:31983")["status"] == "other"


def test_load_table_maps_columns_and_decimals(tmp_path) -> None:
    f = tmp_path / "prod.csv"
    f.write_text("CAMPO;MES;OLEO\nA;1;1.234,5\nB;2;10,25\n", encoding="utf-8")
    rows = load_table(str(f), {"field": "CAMPO", "month": "MES", "oil": "OLEO"}, numeric=["month", "oil"])
    assert rows[0]["oil"] == pytest.approx(1234.5)
    assert rows[1]["oil"] == pytest.approx(10.25)
    assert rows[1]["field"] == "B"


def test_load_table_fails_loudly_on_renamed_header(tmp_path) -> None:
    f = tmp_path / "prod.csv"
    f.write_text("CAMPO;MES\nA;1\n", encoding="utf-8")
    with pytest.raises(KeyError):
        load_table(str(f), {"field": "CAMPO", "oil": "OLEO"})
    f2 = tmp_path / "blank.csv"
    f2.write_text("CAMPO;OLEO\nA;\n", encoding="utf-8")
    rows = load_table(str(f2), {"oil": "OLEO"}, numeric=["oil"])
    assert math.isnan(rows[0]["oil"])
