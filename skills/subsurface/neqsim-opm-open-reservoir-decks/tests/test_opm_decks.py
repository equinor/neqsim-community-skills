import os

import pytest

from opm_open_decks import (
    CASES, OpmDataClient, TooLargeError, case_names, expand_repeats, get_case, include_paths, keyword_blocks,
    keyword_records, resolve_include, summarize_deck, to_floats,
)

DECK = """-- header comment with / slash
RUNSPEC
TITLE
   Test deck
DIMENS
   10 10 3 /
OIL
GAS
WATER
DISGAS
FIELD
START
   1 'JAN' 2015 /
GRID
INCLUDE
   './INCLUDE/GRID/GRID.INC' /
PROPS
PVTO
-- Rs  Pg  Bo  mu
  0.1  500  1.2  0.2
       1000 1.1  0.3 /
  0.2  500  1.3  0.2 /
/
DENSITY
  53.0 64.0 0.05 /
SCHEDULE
WELSPECS
  'INJ' 'G' 1 1 1* 'GAS' /
  'PROD' 'G' 10 10 1* 'OIL' /
/
TSTEP
  3*30 /
WELSPECS
  'NEW1' 'G' 5 5 1* 'OIL' /
/
DATES
  1 'FEB' 2015 /
  1 'MAR' 2015 /
/
"""


def test_summary_reads_all_schedule_occurrences():
    summary = summarize_deck(DECK)
    assert summary["dimens"] == [10, 10, 3] and summary["cells"] == 300
    assert summary["units"] == "FIELD" and summary["phases"] == ["OIL", "GAS", "WATER", "DISGAS"]
    assert summary["wells"] == ["INJ", "PROD", "NEW1"]
    assert summary["start"] == "1 JAN 2015"
    assert summary["pvt_keywords"] == ["PVTO", "DENSITY"]
    assert summary["n_dates_records"] == 2 and summary["includes"] == ["./INCLUDE/GRID/GRID.INC"]
    assert summary["sections"] == ["RUNSPEC", "GRID", "PROPS", "SCHEDULE"]


def test_keyword_records_pvto_structure_and_repeats():
    records = keyword_records(DECK, "PVTO")
    assert records == [["0.1", "500", "1.2", "0.2", "1000", "1.1", "0.3"], ["0.2", "500", "1.3", "0.2"]]
    assert to_floats(records[1]) == [0.2, 500.0, 1.3, 0.2]
    assert expand_repeats(["3*30", "5"]) == ["30", "30", "30", "5"]
    assert keyword_records(DECK, "SGOF") == [] and len(keyword_blocks(DECK, "WELSPECS")) == 2


def test_include_resolution_blocks_escape():
    assert resolve_include("norne/NORNE.DATA", "./INCLUDE/GRID/G.INC") == "norne/INCLUDE/GRID/G.INC"
    for bad in ("../../etc/passwd", "/abs/path", "a b.inc", "..\\x"):
        with pytest.raises(ValueError):
            resolve_include("NORNE.DATA", bad)
    assert include_paths("IMPORT\n  'a.grdecl' /\n") == ["a.grdecl"]


def test_catalog_is_consistent():
    assert set(case_names()) == {"norne", "sleipner", "spe1", "spe10model1", "spe10model2", "spe3", "spe5", "spe9"}
    for name, entry in CASES.items():
        assert entry["directory"] == name and entry["decks"] and entry["licence"]
    assert "Open Database" not in CASES["sleipner"]["licence"] and "sold" in CASES["sleipner"]["licence"]
    with pytest.raises(KeyError):
        get_case("spe2")


def test_client_guards_cache_and_provenance(tmp_path):
    calls = []

    def fake(url, timeout, max_bytes):
        calls.append(url)
        return DECK.encode()

    client = OpmDataClient(fake, cache_dir=tmp_path, ref="abc123")
    assert client.summary("spe1")["wells"] == ["INJ", "PROD", "NEW1"]
    client.get_text("spe1", "SPE1CASE1.DATA")
    assert len(calls) == 1 and [r["cached"] for r in client.provenance()] == [False, True]
    assert calls[0] == "https://raw.githubusercontent.com/OPM/opm-data/abc123/spe1/SPE1CASE1.DATA"
    assert client.provenance()[0]["sha256"] and "Open Database" in client.provenance()[0]["licence"]
    with pytest.raises(TooLargeError):
        client.get_text("spe10model2", "SPE10MODEL2_PERM.INC")
    for bad in ("../x", "/etc/passwd", "a?b", "a/../b"):
        with pytest.raises(ValueError):
            client.url("spe1", bad)
    with pytest.raises(ValueError):
        OpmDataClient(fake, ref="main; rm")


def test_summary_follows_schedule_includes_and_skips_oversize():
    main = "DIMENS\n 2 2 2 /\nSCHEDULE\nINCLUDE\n  './INCLUDE/HIST.SCH' /\nINCLUDE\n  './INCLUDE/HUGE.SCH' /\n"
    files = {"norne/NORNE.DATA": main, "norne/INCLUDE/HIST.SCH": "WELSPECS\n 'B-1H' 'G' 1 1 1* 'OIL' /\n/\nTSTEP\n 5*1 /\n"}

    def fake(url, timeout, max_bytes):
        key = url.split("/master/", 1)[1]
        if key.endswith("HUGE.SCH"):
            raise TooLargeError(url)
        return files[key].encode()

    summary = OpmDataClient(fake).summary("norne", "NORNE.DATA")
    assert summary["wells"] == ["B-1H"] and summary["n_tstep_records"] == 1
    assert summary["schedule_includes_skipped"] == ["INCLUDE/HUGE.SCH"]


def test_resolve_ref_pins_sha():
    client = OpmDataClient(lambda u, t, m: b'{"sha": "eaa2261683a97027e057c2bc49612ad1c86390b3"}')
    assert client.resolve_ref().startswith("eaa22616") and client.ref.startswith("eaa22616")


@pytest.mark.skipif(os.environ.get("NEQSIM_SKILLS_LIVE") != "1", reason="live network test; set NEQSIM_SKILLS_LIVE=1")
def test_live_catalog_matches_published_decks():
    client = OpmDataClient()
    expected = {"spe1": [10, 10, 3], "spe9": [24, 25, 15], "spe10model1": [100, 1, 20], "norne": [46, 112, 22]}
    for case, dims in expected.items():
        assert client.summary(case)["dimens"] == dims, case
    spe3 = client.summary("spe3")
    assert "PVTO" in spe3["pvt_keywords"] and "PVTG" in spe3["pvt_keywords"]
    first_rs = float(keyword_records(client.get_text("spe3", "SPE3CASE1.DATA"), "PVTO")[0][0])
    assert first_rs == pytest.approx(0.189473)
    assert client.summary("norne")["wells"]
    assert client.summary("norne")["n_dates_records"] > 100
