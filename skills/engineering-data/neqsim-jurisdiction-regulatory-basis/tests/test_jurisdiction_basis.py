import pytest

from jurisdiction_basis import jurisdiction_block, resolve_profile
from jurisdiction_basis.profiles import ALIASES, PROFILES


@pytest.mark.parametrize(
    "text,key",
    [("Norway", "NO"), (" ncs ", "NO"), ("UKCS", "GB"), ("Gulf of Mexico", "US"), ("brasil", "BR"), ("Denmark", "EU")],
)
def test_resolve_profile_aliases(text, key):
    assert resolve_profile(text) == key


@pytest.mark.parametrize("text", [None, "", "  ", "Atlantis"])
def test_resolve_profile_unknown(text):
    assert resolve_profile(text) is None


def test_every_alias_points_to_a_profile():
    assert set(ALIASES.values()) <= set(PROFILES)


def test_profiles_have_required_fields():
    for profile in PROFILES.values():
        for field in ("authorities", "laws", "safety_regulations", "recognised_standards", "data_sources"):
            assert profile[field], field


def test_unknown_jurisdiction_is_a_data_gap():
    block = jurisdiction_block("Atlantis")
    assert block["status"] == "unknown-jurisdiction"
    assert "NOT considered" in block["data_gaps"][0]


def test_inferred_jurisdiction_is_flagged_and_never_claims_compliance():
    block = jurisdiction_block("Norway", "offshore platform")
    assert block["status"] == "profile-selected-not-verified"
    assert block["assumptions"] and block["data_gaps"]
    assert any("Havtil" in a for a in block["profile"]["authorities"])


def test_confirmed_jurisdiction_has_no_inference_assumption():
    assert jurisdiction_block("UK", user_confirmed=True)["assumptions"] == []


from jurisdiction_basis import activity_basis
from jurisdiction_basis.activity_register import ACTIVITY_TOPICS, REGISTER, TOPICS


def test_new_country_aliases():
    assert resolve_profile("Angola") == "AO"
    assert resolve_profile("Newfoundland") == "CA"
    assert resolve_profile("NL") == "EU"  # Netherlands, not Newfoundland


def test_register_topics_and_countries_are_consistent():
    assert set(REGISTER) <= set(PROFILES)
    for topics in REGISTER.values():
        assert set(topics) <= set(TOPICS)
    for topic_list in ACTIVITY_TOPICS.values():
        assert set(topic_list) <= set(TOPICS)


def test_every_row_has_instrument_layer_and_status():
    for topics in REGISTER.values():
        for rows in topics.values():
            for row in rows:
                assert row["instrument"] and row["layer"] and row["authority"]
                if row["status"] == "verified-public-source":
                    assert row["verified_on"] and row["source"]


def test_activity_basis_norway_well_and_surf():
    block = activity_basis("Norway", ("well", "surf"), user_confirmed=True)
    assert block["schema"] == "jurisdiction_activity_basis.v1"
    well = block["activities"]["well"]["well_design_integrity"]["instruments"]
    assert any("NORSOK D-010" in r["instrument"] for r in well)
    risers = block["activities"]["surf"]["risers"]["instruments"]
    assert any("N-003" in r["instrument"] for r in risers)
    assert "strictest" in block["layer_rule"]


def test_activity_basis_us_has_verified_part_250_rows():
    block = activity_basis("Gulf of Mexico", ("well",))
    rows = block["activities"]["well"]["well_design_integrity"]["instruments"]
    assert any(r["status"] == "verified-public-source" and "Subpart D" in r["instrument"] for r in rows)


def test_gaps_are_reported_not_hidden():
    block = activity_basis("Angola", ("surf",))
    assert block["coverage_gaps"]
    assert any("No " in g for g in block["data_gaps"])


def test_unknown_country_returns_no_activities_and_a_gap():
    block = activity_basis("Atlantis", ("well",))
    assert block["activities"] == {}
    assert "NOT considered" in block["data_gaps"][0]


def test_partner_operated_asset_is_recorded_as_assumption():
    block = activity_basis("Angola", ("well",), operator="ExxonMobil")
    assert any("operator's design basis" in a for a in block["assumptions"])


def test_invalid_activity_raises():
    with pytest.raises(ValueError):
        activity_basis("Norway", ("seismic",))
