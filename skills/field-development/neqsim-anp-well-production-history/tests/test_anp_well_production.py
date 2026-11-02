"""Tests for anp_well_production using excerpts of public ANP rows (verified 2026-11-02)."""

import datetime as dt
import json
import zipfile

import pytest

from anp_well_production import (
    BBL_TO_M3,
    aggregate,
    completeness,
    cumulative,
    decline_series,
    detect_schema,
    download,
    expected_latest_period,
    extract_links,
    fluid_basis,
    latest_fluid_basis,
    merge_environments,
    normalize,
    oil_density_kg_m3,
    parse_number,
    parse_period,
    producing_rate,
    ratios,
    read_table_bytes,
    read_zip,
    readiness,
    reconcile,
    well_flags,
    well_history,
)

RATE_HEADER = (
    "Estado;Bacia;Nome Poço ANP;Nome Poço Operador;Campo;Operador;Número do Contrato;Período;"
    "Óleo (bbl/dia);Condensado (bbl/dia);Petróleo (bbl/dia);Gás Natural (Mm³/dia) Assoc;"
    "Gás Natural (Mm³/dia) N Assoc;Gás Natural (Mm³/dia) Total;Volume Gás Royalties (m³/mês);"
    "Água (bbl/dia);Instalação Destino;Tipo Instalação;Tempo de Produção (hs por mês);"
    "Período da Carga;Corrente;Grau API;Fração de Destilados|Lev|Cort;% em Volumes Metano;"
    "% em Volumes Etano;% em Volumes Propano;% em Volumes Iso-Butano;% em Volumes Butano;"
    "% em Volumes Iso-Pentano;% em Volumes n-Pentano;% em Volumes Hexanos;% em Volumes Heptanos;"
    "% em Volumes Octanos;% em Volumes Nonanos;% em Volumes Decanos;% em Volumes Undecanos;"
    "% em Volumes Oxigênio;% em Volumes Nitrogênio;% em Volumes Gás Carbônico;PCS GP(kJ/m³);"
    "Data de atualização"
)
PAPA = (
    "Rio de Janeiro;Campos;7-PPT-50HP-RJS;7PPT50HPRJS;PAPA-TERRA;3R Petroleum;480000035569771;2023/12;"
    "4841,6358;0;4841,6358;31,0802;0;31,0802;961,627;1449,9353;PETROBRAS 61;UEP;729;;;;< ºC;"
    "85,876;5,696;4,268;,878;1,287;,377;,353;,247;,148;,051;,006;0;0;0;,514;,299;39173,7195;26/11/2025"
)
MERO = (
    "Rio de Janeiro;Santos;7-MRO-10B-RJS;7-MRO-10B-RJS;AnC_MERO;Petrobras;48610011150201310;2023/12;"
    "1615,7229;0;1615,7229;104,0994;0;104,0994;279,639;2,2651;FPSO GUANABARA;UEP;718;2023/02;MERO;29,6;"
    "32,92%;43,434;6,89;4,223;,578;1,338;,285;,31;,119;,019;,003;0;0;0;2,592;40,14;,069;22539,3063;26/11/2025"
)

VOL_HEADER = (
    "[Ano],[Mês/Ano],[Estado],[Bacia],[Campo],[Poço],[Ambiente],[Instalação],[Produção de Óleo (m³)],"
    "[Produção de Condensado (m³)],[Produção de Gás Associado (Mm³)],[Produção de Gás Não Associado (Mm³)],"
    "[Produção de Água (m³)],[Injeção de Gás (Mm³)],[Injeção de Água para Recuperação Secundária (m³)],"
    "[Injeção de Água para Descarte (m³)],[Injeção de Gás Carbônico (Mm³)],[Injeção de Nitrogênio (Mm³)],"
    "[Injeção de Vapor de Água (t)],[Injeção de Polímeros (m³)],[Injeção de Outros Fluidos (m³)]"
)
VOL_PAPA = (
    '2023,12/2023,Rio de Janeiro,Campos,PAPA-TERRA,7-PPT-50HP-RJS,MAR,Plataforma 3R-2,"23862,519",0,'
    '"963,486",0,"7146,161",,,,,,,,'
)

ZONE_HEADER = (
    "Zona,Nome poço ANP,Campo,Bacia,Ambiente,Data,Óleo (m³/d),Condensado (m³/d),Petróleo (m³/d),"
    "Gás associado (Mil m³/d),Gás não associado (Mil m³/d),Gás total (Mil m³/d),Água (m³/d),"
    "Água injetada para descarte (m³/d),Água injetada para rec. secundária (m³/d),Vapor injetado (t/d),"
    "Gás injetado (Mil m³/d),CO2 injetado (Mil m³/d),N2 injetado (Mil m³/d),Outros fluidos injetados (m³/d)"
)
ZONE_ROW = (
    '28URUC-04,1-IMET-28-ES,BATUÍRA,Espírito Santo,TERRA,01/08/2026,"1,25","0,00","1,25","0,04","0,00",'
    '"0,04","0,35","0,00","0,00","0,00","0,00","0,00","0,00","0,00"'
)

STATUS_HEADER = (
    "Nome_poço_anp,Campo,Bacia,Operador_atual,Data_início_perfuração,Data_término_perfuração,"
    "Data_conclusão_poço,Data_início_operação_(mês/ano),Data_última_operação_(mês/ano),"
    "Data_início_produção_(mês/ano),Data_última_produçaõ_(mês/ano),Data_início_injeção_(mês/ano),"
    "Data_última_injeção_(mês/ano),Em_operação_(produção_ou_injeção),Ambiente,Latitude_da_base,"
    "Longitude_da_base,Estado,Data_de_referência_situação,Data_atualização_da_situação,Situação_do_poço,"
    "Método_de_elevação,Última_intervenção,Data_última_intervenção"
)
STATUS_ROW = (
    '1-BAS-85-BAS,ÁREA DO BAS-85,ESPÍRITO SANTO,,10/02/1989,11/04/1989,11/04/1989, , , , , , ,NÃO,MAR,'
    '"-18:22:40,186","-39:31:29,808",BAHIA,06/06/2013,02/07/2013,ABANDONADO PERMANENTEMENTE,'
    'SEM MÉTODO DE ELEVAÇÃO, , '
)


def rate_records(*rows, header=RATE_HEADER, enc="cp1252"):
    raw = (header + "\n" + "\n".join(rows) + "\n").encode(enc)
    h, r, meta = read_table_bytes(raw)
    return normalize(h, r)


def month_record(period, liquid, gas, water, hours=None, well="W-1", field="F"):
    y, m = parse_period(period)
    days = [31, 29 if y % 4 == 0 else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]
    return {
        "well": well, "field": field, "installation": "I", "period": period, "year": y, "month": m,
        "days": days, "liquid_m3d": liquid, "oil_m3d": liquid, "gas_total_km3d": gas, "water_m3d": water,
        "gas_assoc_km3d": gas, "gas_nonassoc_km3d": 0.0, "condensate_m3d": 0.0, "hours_on": hours,
    }


def test_parse_number_brazilian_forms():
    assert parse_number("4841,6358") == pytest.approx(4841.6358)
    assert parse_number(",878") == pytest.approx(0.878)
    assert parse_number("3.127,441") == pytest.approx(3127.441)
    assert parse_number("1.234.567") == 1234567.0
    assert parse_number("85,876") == pytest.approx(85.876)
    assert parse_number("26/11/2025") is None
    assert parse_number("< ºC") is None
    assert parse_number("  ") is None


@pytest.mark.parametrize(
    "text,expected",
    [("2023/12", (2023, 12)), ("01/2026", (2026, 1)), ("01/08/2026", (2026, 8)), ("2026-08-01", (2026, 8))],
)
def test_parse_period(text, expected):
    assert parse_period(text) == expected


def test_parse_period_rejects_garbage():
    with pytest.raises(ValueError):
        parse_period("Dec 2023")
    with pytest.raises(ValueError):
        parse_period("2023/13")


def test_rate_family_units_and_fluid_fields():
    recs = rate_records(PAPA, MERO)
    assert detect_schema(read_table_bytes(RATE_HEADER.encode("cp1252"))[0]) == "well_monthly_rates"
    papa = recs[0]
    assert papa["family"] == "well_monthly_rates"
    assert papa["liquid_m3d"] == pytest.approx(4841.6358 * BBL_TO_M3)
    assert papa["gas_total_km3d"] == pytest.approx(31.0802)
    assert papa["water_m3d"] == pytest.approx(1449.9353 * BBL_TO_M3)
    assert papa["hours_on"] == 729
    assert papa["period"] == "2023-12" and papa["days"] == 31
    assert papa["gas_composition_pct"]["methane"] == pytest.approx(85.876)
    assert papa["gas_composition_pct"]["propane"] == pytest.approx(4.268)
    assert papa["gcv_kj_m3"] == pytest.approx(39173.7195)
    assert recs[1]["api"] == pytest.approx(29.6)
    assert recs[1]["analysis_period"] == "2023/02"


def test_damaged_headers_still_resolve():
    damaged = RATE_HEADER.replace("ç", "\ufffd").replace("ã", "\ufffd").replace("á", "\ufffd")
    h, r, _ = read_table_bytes((damaged + "\n" + PAPA + "\n").encode("utf-8"))
    rec = normalize(h, r)[0]
    assert rec["well"] == "7-PPT-50HP-RJS"
    assert rec["liquid_m3d"] > 0


def test_cp1252_and_utf8_both_read():
    for enc in ("cp1252", "utf-8"):
        h, r, meta = read_table_bytes((RATE_HEADER + "\n" + PAPA + "\n").encode(enc))
        assert meta["delimiter"] == ";" and meta["encoding"] == ("utf-8" if enc == "utf-8" else "cp1252")
        assert normalize(h, r)[0]["field"] == "PAPA-TERRA"


def test_volume_family_gives_rates_by_calendar_days():
    h, r, meta = read_table_bytes((VOL_HEADER + "\n" + VOL_PAPA + "\n").encode("utf-8"))
    assert meta["delimiter"] == ","
    rec = normalize(h, r)[0]
    assert rec["family"] == "well_monthly_volumes"
    assert rec["liquid_m3d"] == pytest.approx(23862.519 / 31)
    assert rec["gas_total_km3d"] == pytest.approx(963.486 / 31)
    assert rec["gas_inj_km3d"] is None


def test_rate_and_volume_files_reconcile_for_same_well_month():
    rates = rate_records(PAPA)
    h, r, _ = read_table_bytes((VOL_HEADER + "\n" + VOL_PAPA + "\n").encode("utf-8"))
    vols = normalize(h, r)
    assert reconcile(rates, vols) == []
    vols[0]["gas_total_km3d"] *= 1.5
    bad = reconcile(rates, vols)
    assert len(bad) == 1 and bad[0]["field"] == "gas_total_km3d"


def test_zone_and_status_families():
    h, r, _ = read_table_bytes((ZONE_HEADER + "\n" + ZONE_ROW + "\n").encode("utf-8"))
    z = normalize(h, r)[0]
    assert z["family"] == "zone_daily_rates" and z["zone"] == "28URUC-04"
    assert z["liquid_m3d"] == pytest.approx(1.25) and z["period"] == "2026-08"
    h, r, _ = read_table_bytes((STATUS_HEADER + "\n" + STATUS_ROW + "\n").encode("utf-8"))
    s = normalize(h, r)[0]
    assert s["status"] == "ABANDONADO PERMANENTEMENTE" and s["lift_method"] == "SEM MÉTODO DE ELEVAÇÃO"
    assert s["latitude_dms"] == "-18:22:40,186"


def test_missing_required_header_fails_loudly():
    bad = RATE_HEADER.replace("Petróleo (bbl/dia)", "Petroleo total")
    h, r, _ = read_table_bytes((bad + "\n" + PAPA + "\n").encode("utf-8"))
    with pytest.raises(KeyError, match="liquid_bbld"):
        normalize(h, r, family="well_monthly_rates")
    with pytest.raises(ValueError):
        detect_schema(["a", "b"])


def test_merge_environments_does_not_double_count_presalt():
    mar = rate_records(PAPA, MERO)
    presalt = rate_records(MERO)
    merged, rep = merge_environments({"Mar": mar, "PreSal": presalt})
    assert len(merged) == 2 and rep["n_overlap"] == 1 and rep["presalt_is_subset"]
    assert [m for m in merged if m["well"] == "7-MRO-10B-RJS"][0]["presalt"] is True
    naive = mar + presalt
    with pytest.raises(ValueError, match="Duplicate"):
        aggregate(naive, by=("field",))
    assert sum(a["liquid_m3d"] for a in aggregate(merged, by=("field",))) == pytest.approx(
        (4841.6358 + 1615.7229) * BBL_TO_M3
    )


def test_merge_warns_on_presalt_only_and_missing_offshore():
    presalt = rate_records(MERO)
    _, rep = merge_environments({"PreSal": presalt})
    assert rep["warnings"]
    _, rep = merge_environments({"Mar": rate_records(PAPA), "PreSal": presalt})
    assert not rep["presalt_is_subset"] and rep["presalt_only"] == [("7-MRO-10B-RJS", "2023-12")]


def test_ratios_and_aggregate_by_field():
    a = month_record("2024-01", 100.0, 20.0, 100.0, well="A")
    b = month_record("2024-01", 300.0, 60.0, 100.0, well="B")
    agg = aggregate([a, b], by=("field",))
    assert len(agg) == 1 and agg[0]["n_wells"] == 2
    assert agg[0]["liquid_m3d"] == 400.0
    assert agg[0]["gor_sm3_sm3"] == pytest.approx(200.0)
    assert agg[0]["water_cut"] == pytest.approx(200.0 / 600.0)
    assert ratios({"liquid_m3d": 0, "gas_total_km3d": 5, "water_m3d": 0})["gor_sm3_sm3"] is None


def test_gor_of_papa_terra_is_physical():
    rec = rate_records(PAPA)[0]
    assert ratios(rec)["gor_sm3_sm3"] == pytest.approx(40.4, abs=0.2)


def test_producing_rate_uses_hours_on_stream():
    rec = month_record("2023-12", 100.0, 10.0, 0.0, hours=372.0)
    assert producing_rate(rec) == pytest.approx(200.0)
    assert producing_rate(month_record("2023-12", 100.0, 10.0, 0.0, hours=0.0)) is None
    assert producing_rate(month_record("2023-12", 100.0, 10.0, 0.0)) is None


def test_completeness_gaps_and_publication_lag():
    recs = [month_record(p, 10, 1, 1) for p in ("2024-01", "2024-02", "2024-04")]
    c = completeness(recs, today=dt.date(2024, 7, 10))
    assert c["missing"] == ["2024-03"] and c["last"] == "2024-04"
    assert c["expected_latest"] == "2024-05" and c["behind_expected_months"] == 1
    assert expected_latest_period(dt.date(2026, 1, 15)) == (2025, 11)
    assert expected_latest_period(dt.date(2026, 3, 1)) == (2026, 1)


def test_well_flags():
    hist = [
        month_record("2024-01", 100, 10, 1, hours=744),
        month_record("2024-02", 0, 0, 0, hours=0),
        month_record("2024-04", 90, 9, 1, hours=200),
        month_record("2024-05", 80, 8, 1, hours=744),
        month_record("2024-06", 80, 8, 1, hours=0),
        month_record("2024-07", 80, 900, 1, hours=744),
    ]
    f = well_flags(hist)
    assert f["shut_in"] == ["2024-02"] and f["partial"] == ["2024-04"]
    assert f["hours_conflict"] == ["2024-06"] and f["gaps"] == ["2024-03"]
    assert f["gor_outliers"] == ["2024-07"]


def test_decline_series_drops_shut_in_and_feeds_fit():
    hist = [month_record("2024-%02d" % m, q, 1, 1) for m, q in enumerate([100, 90, 0, 72, 65, 58], start=1)]
    s = decline_series(hist)
    assert len(s) == 5 and s[0][0] == pytest.approx(2024 + 0.5 / 12)
    nsc = pytest.importorskip("norwegian_continental_shelf_data.decline")
    fit = nsc.fit_arps_decline(s)
    assert fit.decline_rate_per_year > 0


def test_cumulative_uses_calendar_days():
    hist = [month_record("2024-01", 10.0, 1.0, 0.0), month_record("2024-02", 20.0, 1.0, 0.0)]
    cum = cumulative(hist)
    assert cum[-1][1] == pytest.approx(10 * 31 + 20 * 29)


def test_well_history_sorted_with_ratios():
    recs = [month_record("2024-02", 10, 1, 0, well="W"), month_record("2024-01", 10, 2, 0, well="W"),
            month_record("2024-01", 5, 1, 0, well="X")]
    hist = well_history(recs, "W")
    assert [h["period"] for h in hist] == ["2024-01", "2024-02"]
    assert hist[0]["gor_sm3_sm3"] == pytest.approx(200.0)


def test_fluid_basis_from_real_row():
    rec = rate_records(MERO)[0]
    fb = fluid_basis(rec)
    assert fb["api"] == pytest.approx(29.6)
    assert fb["stock_tank_density_kg_m3"] == pytest.approx(oil_density_kg_m3(29.6))
    assert 870 < fb["stock_tank_density_kg_m3"] < 885
    assert fb["gor_sm3_sm3"] == pytest.approx(104099.4 / (1615.7229 * BBL_TO_M3), rel=1e-6)
    comp = fb["gas"]["mole_fraction"]
    assert sum(comp.values()) == pytest.approx(1.0)
    assert comp["methane"] == pytest.approx(0.43434) and "i-butane" in comp
    assert fb["gas"]["closure_ok"] and fb["gcv_kj_m3"] == pytest.approx(22539.3063)
    assert any("not a wellstream" in w for w in fb["warnings"])
    assert any("Oxygen above" in w for w in fb["warnings"])
    assert not any("Oxygen above" in w for w in fluid_basis(rate_records(PAPA)[0])["warnings"])


def test_latest_fluid_basis_skips_records_without_fluid():
    full = rate_records(MERO)[0]
    newer = dict(full, period="2024-01", api=None, gas_composition_pct=None)
    fb = latest_fluid_basis([full, newer])
    assert fb["period"] == "2023-12"
    assert latest_fluid_basis([newer]) is None


def test_extract_links_and_download_cache(tmp_path):
    page = (
        '<a href="/anp/arquivos/arquivos-producao-de-petroleo-e-gas-natural-por-poco/2023/producao-12.zip">Dez</a>'
        '<a href="/anp/arquivos/arquivos-producao-de-petroleo-e-gas-natural-por-poco/meta.pdf">meta</a>'
        '<a href="/anp/arquivos/arquivos-producao-de-petroleo-e-gas-natural-por-poco/2023/producao-12.zip">dup</a>'
        '<a href="/other/file.zip">x</a>'
    )
    links = extract_links(page, "well_monthly_rates", base="https://example.org/page")
    assert [l["name"] for l in links] == ["producao-12.zip"]
    assert links[0]["url"].startswith("https://example.org/anp/")

    calls = []

    def getter(url, timeout):
        calls.append(url)
        return b"abc"

    path, log = download(links[0]["url"], tmp_path, getter=getter)
    assert log["status"] == "downloaded" and log["bytes"] == 3 and path.read_bytes() == b"abc"
    path2, log2 = download(links[0]["url"], tmp_path, getter=getter)
    assert log2["status"] == "cache" and calls == [links[0]["url"]] and path2 == path
    assert json.loads(path.with_name(path.name + ".log.json").read_text())["sha256"]
    with pytest.raises(FileNotFoundError):
        download("https://example.org/missing.zip", tmp_path, offline=True)


def test_read_zip_returns_csv_members(tmp_path):
    z = tmp_path / "p.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("2023_12_producao_Mar.csv", RATE_HEADER + "\n" + PAPA + "\n")
        zf.writestr("readme.txt", "x")
    members = read_zip(z)
    assert list(members) == ["2023_12_producao_Mar.csv"]


def test_well_split_over_fields_is_not_a_duplicate_and_sums_in_history():
    a = month_record("2023-12", 1.0, 0.03, 0.1, hours=374, well="7-SDM-19-RN", field="ANGICO")
    b = month_record("2023-12", 4.0, 0.29, 0.2, hours=374, well="7-SDM-19-RN", field="JANDUÍ")
    agg = aggregate([a, b], by=("field",))
    assert len(agg) == 2
    with pytest.raises(ValueError, match="Duplicate"):
        aggregate([a, dict(a)], by=("field",))
    hist = well_history([a, b], "7-SDM-19-RN")
    assert len(hist) == 1 and hist[0]["n_rows"] == 2 and hist[0]["liquid_m3d"] == pytest.approx(5.0)
    assert hist[0]["field"] == "ANGICO+JANDUÍ" and hist[0]["hours_on"] == 374


def test_mixed_encoding_file_keeps_valid_lines():
    header = RATE_HEADER.encode("cp1252")
    good = PAPA.replace("PAPA-TERRA", "CARMÓPOLIS").encode("utf-8")
    cut = PAPA.replace("PAPA-TERRA", "BALEIA ANÃ").encode("utf-8").replace("BALEIA ANÃ".encode("utf-8"), b"BALEIA AN\xc3")
    h, r, meta = read_table_bytes(header + b"\n" + good + b"\n" + cut + b"\n")
    recs = normalize(h, r)
    assert meta["encoding"] == "mixed" and len(recs) == 2
    assert recs[0]["field"] == "CARMÓPOLIS" and recs[1]["field"].startswith("BALEIA AN")


def test_environment_label_is_set_from_file_label():
    merged, _ = merge_environments({"Terra": rate_records(PAPA)})
    assert merged[0]["environment"] == "TERRA"


def test_readiness_lists_what_is_missing():
    r = readiness("material_balance")
    assert "reservoir pressure" in " ".join(r["missing"])
    with pytest.raises(KeyError, match="known"):
        readiness("nope")
