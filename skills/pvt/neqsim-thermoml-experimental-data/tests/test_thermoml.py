import os

import pytest

from thermoml_experimental_data import (
    ThermomlClient, ThermomlUnavailable, compare_points, parse_thermoml, pressure_to_bara, split_name_unit,
    thermoml_url, validate_doi,
)

# Synthetic document in the ThermoML 2.0 schema (not real measurements).
FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<DataReport xmlns="http://www.iupac.org/namespaces/ThermoML">
  <Citation><sAuthor>Doe, J.</sAuthor><sPubName>Synthetic J.</sPubName><yrPubYr>2020</yrPubYr>
    <sTitle>Synthetic density of a binary</sTitle><sDOI>10.9999/synthetic.1</sDOI></Citation>
  <Compound><RegNum><nOrgNum>1</nOrgNum></RegNum><sCommonName>methane</sCommonName><sStandardInChIKey>VNWKTOKETHGBQD-UHFFFAOYSA-N</sStandardInChIKey><sFormulaMolec>CH4</sFormulaMolec></Compound>
  <Compound><RegNum><nOrgNum>2</nOrgNum></RegNum><sCommonName>ethane</sCommonName><sCommonName>R-170</sCommonName></Compound>
  <PureOrMixtureData>
    <nPureOrMixtureDataNumber>1</nPureOrMixtureDataNumber>
    <Component><RegNum><nOrgNum>1</nOrgNum></RegNum></Component>
    <Component><RegNum><nOrgNum>2</nOrgNum></RegNum></Component>
    <Property><nPropNumber>1</nPropNumber>
      <Property-MethodID><PropertyGroup><VolumetricProp><ePropName>Mass density, kg/m3</ePropName></VolumetricProp></PropertyGroup></Property-MethodID>
      <PropPhaseID><ePropPhase>Gas</ePropPhase></PropPhaseID></Property>
    <Constraint><nConstraintNumber>1</nConstraintNumber>
      <ConstraintID><ConstraintType><ePressure>Pressure, kPa</ePressure></ConstraintType></ConstraintID>
      <nConstraintValue>5000</nConstraintValue></Constraint>
    <Variable><nVarNumber>1</nVarNumber><VariableID><VariableType><eTemperature>Temperature, K</eTemperature></VariableType></VariableID></Variable>
    <Variable><nVarNumber>2</nVarNumber><VariableID><VariableType><eComponentComposition>Mole fraction</eComponentComposition></VariableType><RegNum><nOrgNum>1</nOrgNum></RegNum></VariableID></Variable>
    <NumValues>
      <VariableValue><nVarNumber>1</nVarNumber><nVarValue>300</nVarValue></VariableValue>
      <VariableValue><nVarNumber>2</nVarNumber><nVarValue>0.8</nVarValue></VariableValue>
      <PropertyValue><nPropNumber>1</nPropNumber><nPropValue>40</nPropValue><CombinedUncertainty><nCombExpandUncertValue>0.5</nCombExpandUncertValue></CombinedUncertainty></PropertyValue>
    </NumValues>
    <NumValues>
      <VariableValue><nVarNumber>1</nVarNumber><nVarValue>320</nVarValue></VariableValue>
      <VariableValue><nVarNumber>2</nVarNumber><nVarValue>0.8</nVarValue></VariableValue>
      <PropertyValue><nPropNumber>1</nPropNumber><nPropValue>36</nPropValue></PropertyValue>
    </NumValues>
  </PureOrMixtureData>
</DataReport>
"""


def test_parse_flattens_state_and_uncertainty():
    report = parse_thermoml(FIXTURE)
    assert report.doi == "10.9999/synthetic.1" and report.compounds[1].inchikey.startswith("VNWKTOKE")
    points = list(report.points(property_contains="density"))
    assert len(points) == 2
    first = points[0]
    assert (first.temperature_k, first.pressure_bara, first.unit, first.phase) == (300.0, 50.0, "kg/m3", "Gas")
    assert first.mole_fractions["methane"] == 0.8 and first.mole_fractions["ethane"] == pytest.approx(0.2)
    assert first.uncertainty == 0.5 and points[1].uncertainty is None
    assert list(report.points(component="R-170"))  # alias match
    assert not list(report.points(property_contains="viscosity"))


def test_parse_rejects_other_xml():
    with pytest.raises(ValueError):
        parse_thermoml("<html/>")


def test_units():
    assert split_name_unit("Mass density, kg/m3") == ("Mass density", "kg/m3")
    assert split_name_unit("Mole fraction") == ("Mole fraction", "")
    assert pressure_to_bara(5000, "kPa") == 50.0 and pressure_to_bara(1, "furlong") is None


def test_compare_summary_and_skipped_failures():
    points = list(parse_thermoml(FIXTURE).points(property_contains="density"))

    def model(point):
        if point.temperature_k > 310:
            raise ValueError("flash failed")
        return 40.4

    summary = compare_points(points, model, tolerance_pct=2.0)
    assert summary.n_points == 1 and summary.n_skipped == 1 and summary.status == "PASS"
    assert summary.aad_pct == pytest.approx(1.0) and summary.fraction_within_uncertainty == 1.0
    assert compare_points(points, lambda p: 80.0).status == "FAIL"
    assert compare_points([], lambda p: 1.0).status == "FAIL"
    assert summary.to_dict()["rows"][0]["T_K"] == 300.0


@pytest.mark.parametrize("bad", ["", "10.1021/../etc", "https://x/y", "10.1021/a?b=1", "abc"])
def test_doi_validation_blocks_path_tricks(bad):
    with pytest.raises(ValueError):
        validate_doi(bad)


def test_client_caches_and_records_provenance(tmp_path):
    calls = []

    def fake(url, timeout):
        calls.append(url)
        return FIXTURE.encode()

    client = ThermomlClient(fake, cache_dir=tmp_path)
    assert client.get_report("10.9999/synthetic.1").doi == "10.9999/synthetic.1"
    client.get_report("10.9999/synthetic.1")
    assert calls == [thermoml_url("10.9999/synthetic.1")]
    assert [r["cached"] for r in client.provenance()] == [False, True]


def test_client_request_cap_and_search_errors():
    client = ThermomlClient(lambda u, t: FIXTURE.encode(), max_requests=1)
    client.get_xml("10.9999/a.1")
    with pytest.raises(RuntimeError):
        client.get_xml("10.9999/a.2")

    def down(url, timeout):
        raise ThermomlUnavailable("HTTP 503")

    with pytest.raises(ThermomlUnavailable):
        ThermomlClient(down).search("methane")
    with pytest.raises(ValueError):
        ThermomlClient(down).search("a & b")


def test_search_parses_results():
    body = (b'{"size":1,"results":[{"content":{"Citation":{"sDOI":"10.1/x","sTitle":"T","yrPubYr":"2001","sPubName":"J"},'
            b'"Compound":[{"sCommonName":["methane"]}]}}]}')
    hits = ThermomlClient(lambda u, t: body).search("methane")
    assert hits == [{"doi": "10.1/x", "title": "T", "year": "2001", "journal": "J", "compounds": ["methane"]}]


@pytest.mark.skipif(os.environ.get("NEQSIM_SKILLS_LIVE") != "1", reason="live network test; set NEQSIM_SKILLS_LIVE=1")
def test_live_archive_fetch_without_login():
    report = ThermomlClient().get_report("10.1021/je3001427")
    points = list(report.points(property_contains="density"))
    assert report.doi == "10.1021/je3001427" and len(points) >= 3
    assert all(p.temperature_k and p.pressure_bara for p in points)
