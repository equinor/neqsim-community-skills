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
