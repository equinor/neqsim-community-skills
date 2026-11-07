"""Build a reviewable jurisdiction block for a study from the public profiles."""

from .profiles import ALIASES, PROFILES


def resolve_profile(country):
    """Return the profile key for a country, code or area name, or None if unknown.

    Args:
        country: free text such as "Norway", "UKCS", "Gulf of Mexico" or "BR".

    Returns:
        The profile key ("NO", "GB", "US", "BR", "EU") or None.
    """
    if not country or not str(country).strip():
        return None
    return ALIASES.get(str(country).strip().upper())


def jurisdiction_block(country, facility_scope="", user_confirmed=False):
    """Build the jurisdiction block that a study records in its assumptions.

    The block never claims compliance. An unknown or unconfirmed jurisdiction is
    reported as a data gap so the report cannot imply that local law was checked.

    Args:
        country: country, area or code of the evaluated asset.
        facility_scope: short scope such as "offshore production platform".
        user_confirmed: True when the user stated the jurisdiction explicitly.

    Returns:
        Dict with schema, status, profile content, assumptions and data gaps.
    """
    key = resolve_profile(country)
    block = {
        "schema": "jurisdiction_basis.v1",
        "requested": country,
        "facility_scope": facility_scope,
        "user_confirmed": bool(user_confirmed),
        "assumptions": [],
        "data_gaps": [],
    }
    if key is None:
        block["status"] = "unknown-jurisdiction"
        block["profile"] = None
        block["data_gaps"].append(
            "Jurisdiction not identified: local laws and regulations were NOT considered; "
            "only international and industry standards were applied."
        )
        return block
    block["status"] = "profile-selected-not-verified"
    block["profile_key"] = key
    block["profile"] = PROFILES[key]
    block["data_gaps"].append(
        "Regulation text and current revision were not checked against the authority source; "
        "compliance statements require review by a qualified person."
    )
    if not user_confirmed:
        block["assumptions"].append(
            "Jurisdiction %s was inferred from the request and not confirmed by the user." % key
        )
    return block
