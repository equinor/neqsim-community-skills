"""Build a reviewable jurisdiction block for a study from the public profiles."""

from .activity_register import ACTIVITY_TOPICS, DESIGN_QUESTIONS, ORIENTATION, REGISTER, TOPICS
from .profiles import ALIASES, PROFILES

LAYER_RULE = (
    "Apply three layers and keep them separate: (1) law and regulation of the jurisdiction, "
    "(2) recognised standards the regulation or contract names, (3) company and project requirements. "
    "The strictest applicable requirement governs; a company or vendor value never relaxes a "
    "regulatory requirement, and a regulation never excuses a stricter company requirement."
)


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


def activity_basis(country, activities=("well", "surf"), facility_scope="", user_confirmed=False, operator=""):
    """Build the well and SURF regulatory basis for a country.

    Extends :func:`jurisdiction_block` with the instruments to check per design topic, the
    design questions that decide the method, and the topics for which no instrument is
    registered yet. The block never claims compliance.

    Args:
        country: country, area or code of the evaluated asset.
        activities: any of ``"well"`` and ``"surf"``.
        facility_scope: short scope such as "subsea tie-back with four producers".
        user_confirmed: True when the user stated the jurisdiction explicitly.
        operator: operator of the asset when known; a partner operator means its design
            basis and authority interface govern the design.

    Returns:
        Dict with schema ``jurisdiction_activity_basis.v1``, the jurisdiction block fields,
        ``layer_rule``, ``activities`` (topic to instruments and questions), ``coverage_gaps``
        and merged ``assumptions`` and ``data_gaps``.

    Raises:
        ValueError: if an activity is not ``"well"`` or ``"surf"``.
    """
    for activity in activities:
        if activity not in ACTIVITY_TOPICS:
            raise ValueError("activity must be one of %s, got %r" % (sorted(ACTIVITY_TOPICS), activity))
    block = jurisdiction_block(country, facility_scope, user_confirmed)
    block["schema"] = "jurisdiction_activity_basis.v1"
    block["layer_rule"] = LAYER_RULE
    block["operator"] = operator
    block["activities"] = {}
    block["coverage_gaps"] = []
    key = block.get("profile_key")
    if key is None:
        return block
    rows_by_topic = REGISTER.get(key, {})
    for activity in activities:
        topics = {}
        for topic in ACTIVITY_TOPICS[activity]:
            rows = rows_by_topic.get(topic, [])
            topics[topic] = {
                "title": TOPICS[topic],
                "instruments": [dict(row) for row in rows],
                "design_questions": list(DESIGN_QUESTIONS.get(topic, [])),
            }
            if not rows:
                gap = "No %s instrument is registered for %s (%s): research the authority source before design." % (
                    TOPICS[topic].lower(), key, activity)
                block["coverage_gaps"].append(gap)
        block["activities"][activity] = topics
    unverified = sum(
        1 for act in block["activities"].values() for t in act.values() for r in t["instruments"] if r["status"] == ORIENTATION
    )
    if unverified:
        block["data_gaps"].append(
            "%d registered instruments are orientation entries; fetch the current text at the source before quoting them." % unverified
        )
    block["data_gaps"].extend(block["coverage_gaps"])
    if operator and "equinor" not in operator.lower():
        block["assumptions"].append(
            "Asset operated by %s: the operator's design basis and authority interface govern; Equinor requirements apply as a partner review basis only." % operator
        )
    return block
