import io
import os
import zipfile
from datetime import date

import pytest

from open_incident_data import (
    BseeClient, SourceError, annual_counts, estimate_rate, label_counts, parse_date, parse_investigations,
    parse_structures, poisson_interval, split_labels, structure_years,
)
from open_incident_data.sources import SOURCES

INV = (
    '"DATE_OCCURRED","MILITARY_TIME","LEASE_NUMBER","AREA_BLOCK","ACCIDENT_TYPE","PANEL_DISTRICT","STATUS"\n'
    '4/13/2016,"3:15","G17001","WR 508","- Fire - Required Muster ","DISTRICT","Complete"\n'
    '2/27/2016,"4:20","G17001","WR 508","- Crane - Dropped Object","DISTRICT","Complete"\n'
    '1/5/2017,"1:00","G00001","GC 10","- Fire ","DISTRICT","Complete"\n'
    '1/5/2018,"1:00","G00002","MC 20","- Explosion - Fire ","DISTRICT","Pending"\n'
    'bad-date,"1:00","G00002","MC 20","- Fire ","DISTRICT","Pending"\n'
)
STRUCT_HEADER = ('"AREA_CODE","BLOCK_NUMBER","STRUCTURE_NUMBER","STRUC_TYPE_CODE","MAJ_STRUC_FLAG","INSTALL_DATE",'
                 '"REMOVAL_DATE","WATER_DEPTH","MANNED_24_HR_FL"\n')
STRUCT = STRUCT_HEADER + (
    '"WR","508","1","FIXED","Y","1/1/2010","","1500","Y"\n'
    '"GC","10","2","CAIS","N","7/1/2016","6/30/2017","60","N"\n'
    '"MC","20","3","FIXED","Y","1/1/2019","","80","N"\n'
)


def make_zip(member, text, folder=""):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(folder + member, text)
    return buffer.getvalue()


def test_label_and_date_parsing():
    assert split_labels("- Fire - Required Muster ") == ("Fire", "Required Muster")
    assert split_labels("- LTA (>3 days) - Required Evacuation - Crane") == ("LTA (>3 days)", "Required Evacuation", "Crane")
    assert split_labels("") == ()
    assert parse_date("4/13/2016") == date(2016, 4, 13) and parse_date("") is None and parse_date("x") is None


def test_parse_drops_bad_rows_and_checks_columns():
    investigations = parse_investigations(INV)
    assert len(investigations) == 4 and investigations[0].area == "WR" and investigations[0].block == "508"
    assert label_counts(investigations, 2016, 2018)[0] == ("Fire", 3)
    assert annual_counts(investigations, ["fire"]) == {2016: 1, 2017: 1, 2018: 1}
    with pytest.raises(ValueError):
        parse_investigations("A,B\n1,2\n")
    assert len(parse_structures(STRUCT)) == 3


def test_poisson_interval_matches_published_garwood_values():
    low, high = poisson_interval(10, 0.95)
    assert low == pytest.approx(4.7954, abs=1e-3) and high == pytest.approx(18.3904, abs=1e-3)
    low0, high0 = poisson_interval(0, 0.95)
    assert low0 == 0.0 and high0 == pytest.approx(3.6889, abs=1e-3)
    low1, high1 = poisson_interval(1, 0.90)
    assert low1 == pytest.approx(0.05129, abs=1e-3) and high1 == pytest.approx(4.7439, abs=1e-3)
    with pytest.raises(ValueError):
        poisson_interval(-1)


def test_structure_years_overlap_and_filters():
    structures = parse_structures(STRUCT)
    full_2017 = structure_years(structures, date(2017, 1, 1), date(2017, 12, 31))
    assert full_2017 == pytest.approx((365 + 181) / 365.25)
    assert structure_years(structures, date(2017, 1, 1), date(2017, 12, 31), major_only=True) == pytest.approx(365 / 365.25)
    assert structure_years(structures, date(2017, 1, 1), date(2017, 12, 31), areas=["gc"]) == pytest.approx(181 / 365.25)
    assert structure_years(structures, date(2000, 1, 1), date(2001, 12, 31)) == 0.0
    assert structure_years(structures, date(2017, 1, 1), date(2017, 12, 31), manned_only=True) == pytest.approx(365 / 365.25)


def test_estimate_rate_and_zero_exposure():
    investigations, structures = parse_investigations(INV), parse_structures(STRUCT)
    estimate = estimate_rate(investigations, structures, ["Fire"], 2016, 2018, major_only=True)
    assert estimate.count == 3 and estimate.rate_per_structure_year == pytest.approx(3 / estimate.structure_years)
    assert estimate.lower < estimate.rate_per_structure_year < estimate.upper and estimate.caveats
    deep = estimate_rate(investigations, structures, ["Fire"], 2016, 2018, areas=["GC"])
    assert deep.count == 1 and deep.filters["areas"] == ["GC"]
    none = estimate_rate(investigations, structures, ["Fire"], 1990, 1991)
    assert none.rate_per_structure_year is None and none.to_dict()["count"] == 0


def test_client_unpacks_caches_and_rejects_html(tmp_path):
    calls = []

    def fake(url, timeout, max_bytes):
        calls.append(url)
        return make_zip(SOURCES["investigations"]["member"], INV, folder="export/")

    client = BseeClient(fake, cache_dir=tmp_path)
    assert len(parse_investigations(client.get_text("investigations"))) == 4
    client.get_text("investigations")
    assert len(calls) == 1 and [r["cached"] for r in client.provenance()] == [False, True]
    assert calls[0] == "https://www.data.bsee.gov/Other/Files/IncInvRawData.zip"
    with pytest.raises(KeyError):
        client.get_text("anything-else")
    with pytest.raises(SourceError):
        BseeClient(lambda u, t, m: b"<html>not found</html>").get_text("structures")
    with pytest.raises(SourceError):
        BseeClient(lambda u, t, m: make_zip("other.txt", "x")).get_text("structures")


@pytest.mark.skipif(os.environ.get("NEQSIM_SKILLS_LIVE") != "1", reason="live network test; set NEQSIM_SKILLS_LIVE=1")
def test_live_bsee_download_without_login():
    client = BseeClient()
    investigations = parse_investigations(client.get_text("investigations"))
    structures = parse_structures(client.get_text("structures"))
    assert len(investigations) > 1500 and len(structures) > 5000
    estimate = estimate_rate(investigations, structures, ["Fire"], 2010, 2024, major_only=True)
    assert estimate.count > 10 and estimate.structure_years > 1000
    assert estimate.lower <= estimate.rate_per_structure_year <= estimate.upper
    assert dict(label_counts(investigations, 2000, 2024))["Fire"] > 50
