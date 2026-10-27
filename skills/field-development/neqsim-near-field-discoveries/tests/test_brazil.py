import datetime as dt

from near_field_discoveries import (
    brazil_records,
    classify_well_result,
    discovery_candidates,
    evaluation_area_records,
    hosts_from_production_units,
)
from near_field_discoveries.brazil import parse_date

AS_OF = dt.date(2026, 10, 27)


def square(lon, lat, half=0.2):
    return {"type": "MultiPolygon", "coordinates": [[[[lon - half, lat - half], [lon + half, lat - half], [lon + half, lat + half],
                                                       [lon - half, lat + half], [lon - half, lat - half]]]]}


def well(name, lon, lat, result, cat="Pioneiro", tipo="Exploratório", **kw):
    p = {"name": name, "latitude": lat, "longitude": lon, "reclassificacao": result, "categoria": cat, "tipo": tipo,
         "nome_campo": None, "lamina_dagua": 2000, "operador": "Op A", "dat_conclusao": "01/02/2020"}
    p.update(kw)
    return {"type": "Feature", "properties": p, "geometry": {"type": "Point", "coordinates": [lon, lat]}}


def test_classify_well_result_handles_accents_and_fluids() -> None:
    assert classify_well_result("DESCOBRIDOR DE CAMPO COM PETRÓLEO") == ("discovery", "oil")
    assert classify_well_result("PRODUTOR SUBCOMERCIAL DE GÁS NATURAL E CONDENSADO") == ("subcommercial", "gas-condensate")
    assert classify_well_result("PORTADOR DE PETRÓLEO E GÁS NATURAL") == ("bearing", "oil+gas")
    assert classify_well_result("SECO COM INDÃCIOS DE PETRÓLEO")[0] == "shows"
    assert classify_well_result("SECO SEM INDÍCIOS") == ("dry", None)
    assert classify_well_result(None) == ("other", None)


def test_parse_date_styles() -> None:
    assert parse_date("2022-08-25") == dt.date(2022, 8, 25)
    assert parse_date("05/11/2014 00:00:00") == dt.date(2014, 11, 5)
    assert parse_date("31-05-2023") == dt.date(2023, 5, 31)
    assert parse_date("2027-01-0") == dt.date(2027, 1, 1)
    assert parse_date("") is None


def test_candidates_cluster_wells_and_skip_field_wells() -> None:
    wells = [
        well("1-AAA-1-RJS", -42.00, -25.00, "DESCOBRIDOR DE CAMPO COM PETRÓLEO"),
        well("3-AAA-2-RJS", -42.02, -25.01, "PORTADOR DE PETRÓLEO", cat="Pioneiro Adjacente"),
        well("1-BBB-1-SPS", -41.00, -25.00, "PRODUTOR SUBCOMERCIAL DE GÁS NATURAL"),
        well("1-CCC-1-SPS", -40.00, -24.00, "SECO SEM INDÍCIOS"),
        well("1-DDD-1-SPS", -43.00, -25.00, "DESCOBRIDOR DE CAMPO COM PETRÓLEO", nome_campo="FIELDX"),
        well("7-EEE-1-SPS", -44.00, -25.00, "PORTADOR DE PETRÓLEO", cat="Desenvolvimento", tipo="Explotatório"),
    ]
    fields = [{"type": "Feature", "properties": {"name": "FIELDX", "etapa": "Produção", "fluido_pri": "ÓLEO"}, "geometry": square(-43.0, -25.0, 0.1)}]
    recs = discovery_candidates(wells, fields, as_of=AS_OF)
    assert [r.name for r in recs] == ["1-AAA-1-RJS", "1-BBB-1-SPS"]
    first = recs[0]
    assert first.n_wells == 2 and first.hc_type == "OIL"
    assert first.position_basis == "approximate-derived-from-ANP-wells"
    assert first.stage == "not_evaluated"
    assert any("volumes" in g for g in first.gaps)
    assert recs[1].position_basis == "wellhead" and recs[1].hc_type == "GAS"


def test_stage_from_evaluation_plan_and_returned_block() -> None:
    wells = [well("1-RUN-1", -42.0, -25.0, "DESCOBRIDOR DE CAMPO COM PETRÓLEO"),
             well("1-OLD-1", -41.0, -25.0, "PORTADOR DE PETRÓLEO"),
             well("1-RET-1", -40.0, -25.0, "PORTADOR DE PETRÓLEO")]
    plans = [
        {"type": "Feature", "properties": {"NOME_PAD": "PAD-RUN", "DAT_INICIO": "2024-01-01", "DAT_TERM": "2027-12-31", "IN_PL_ATIV": "A"}, "geometry": square(-42.0, -25.0)},
        {"type": "Feature", "properties": {"NOME_PAD": "PAD-OLD", "DAT_INICIO": "2010-01-01", "DAT_TERM": "2020-12-31", "IN_PL_ATIV": "D"}, "geometry": square(-41.0, -25.0)},
    ]
    blocks = [{"type": "Feature", "properties": {"NOM_BLOCO": "S-M-1", "NOM_BACIA": "Santos", "NUM_DESCOB": 3, "OPERADOR_C": "Op B"}, "geometry": square(-42.0, -25.0, 0.5)}]
    returned = [{"type": "Feature", "properties": {"BLOCO": "X"}, "geometry": square(-40.0, -25.0)}]
    recs = {r.name: r for r in discovery_candidates(wells, None, plans, blocks, returned, as_of=AS_OF)}
    assert recs["1-RUN-1"].stage == "in_clarification"
    assert recs["1-RUN-1"].linked["evaluation_plan"] == "PAD-RUN"
    assert recs["1-RUN-1"].linked["block_notified_discoveries"] == 3
    assert recs["1-OLD-1"].stage == "unknown" and "ended" in recs["1-OLD-1"].plan_note
    assert recs["1-RET-1"].stage == "unlikely"


def test_alias_and_known_volumes_remove_gaps() -> None:
    wells = [well("1-NAM-1", -42.0, -25.0, "DESCOBRIDOR DE CAMPO COM PETRÓLEO")]
    recs = discovery_candidates(wells, aliases={"1-NAM-1": "Turmalina"}, known_volumes={"1-NAM-1": {"oil_mmbbl": 300, "source": "operator release"}}, as_of=AS_OF)
    r = recs[0]
    assert r.name == "Turmalina"
    assert r.volumes["oil_mmbbl"] == 300
    assert r.gaps == []


def test_brazil_records_adds_fields_and_evaluation_areas() -> None:
    layers = {
        "wells": [well("1-AAA-1", -42.0, -25.0, "PORTADOR DE PETRÓLEO")],
        "fields": [{"type": "Feature", "properties": {"name": "ABC", "etapa": "Desenvolvimento", "dat_descob": "2015-03-02", "fluido_pri": "ÓLEO"}, "geometry": square(-41.0, -25.0)}],
        "evaluation_plans": [{"type": "Feature", "properties": {"NOME_PAD": "PAD-1", "DAT_TERM": "2030-01-01", "DAT_INICIO": "2024-01-01"}, "geometry": square(-42.0, -25.0)}],
    }
    recs = brazil_records(layers, as_of=AS_OF)
    kinds = sorted(r.kind for r in recs)
    assert kinds == ["discovery", "evaluation_area", "field"]
    field = next(r for r in recs if r.kind == "field")
    assert field.stage == "in_development" and field.discovery_year == 2015 and field.hc_type == "oil"
    area = evaluation_area_records(layers["evaluation_plans"], AS_OF)[0]
    assert area.stage == "in_clarification"


def test_hosts_from_production_units() -> None:
    units = [{"type": "Feature", "properties": {"NOM_INSTALACAO": "FPSO X", "DESC_TIPO_UEP": "FPSO", "NOM_PROPRIETARIO": "Op", "MED_DISTANCIA_LAMINA": "2000"},
              "geometry": {"type": "Point", "coordinates": [-42.5, -25.2]}}]
    hosts = hosts_from_production_units(units)
    assert hosts[0]["name"] == "FPSO X" and hosts[0]["water_depth_m"] == 2000.0
