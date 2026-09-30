"""Offline tests for SodirFacilityLocator using an injected fake fetch (no network)."""

from __future__ import annotations

import json

from weather_data.ncs_facilities import SodirFacilityLocator


def _facility_page(names):
    features = []
    for idx, name in enumerate(names):
        features.append(
            {
                "attributes": {"fclName": name, "fclKind": "PRODUCTION"},
                "geometry": {"x": 3.7 + idx * 0.1, "y": 60.6 + idx * 0.1},
            }
        )
    return json.dumps({"features": features}).encode("utf-8")


def test_find_matches_by_substring_case_insensitive():
    payload = _facility_page(["TROLL A", "TROLL B", "EKOFISK 2/4 A"])

    def fetch(url: str, timeout: float) -> bytes:
        return payload

    locator = SodirFacilityLocator(fetch=fetch)
    matches = locator.find("troll")

    assert len(matches) == 2
    names = sorted(match.name for match in matches)
    assert names == ["TROLL A", "TROLL B"]
    assert matches[0].latitude != 0
    assert matches[0].longitude != 0


def test_find_returns_empty_for_no_match():
    payload = _facility_page(["TROLL A"])

    def fetch(url: str, timeout: float) -> bytes:
        return payload

    locator = SodirFacilityLocator(fetch=fetch)
    assert locator.find("nonexistent-installation") == []


def test_find_caches_the_page_across_calls():
    calls = {"count": 0}
    payload = _facility_page(["TROLL A"])

    def fetch(url: str, timeout: float) -> bytes:
        calls["count"] += 1
        return payload

    locator = SodirFacilityLocator(fetch=fetch)
    locator.find("troll")
    locator.find("troll")

    assert calls["count"] == 1


def test_find_skips_features_missing_geometry():
    payload = json.dumps(
        {"features": [{"attributes": {"fclName": "NO GEOMETRY"}, "geometry": {}}]}
    ).encode("utf-8")

    def fetch(url: str, timeout: float) -> bytes:
        return payload

    locator = SodirFacilityLocator(fetch=fetch)
    assert locator.find("no geometry") == []
