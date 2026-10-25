"""Tests for the concept long-list / short-list screening skill."""

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from concept_longlist_shortlist import (  # noqa: E402
    COST,
    READINESS_LABEL,
    detect_capacity_variants,
    generate_long_list,
    normalise_scores,
    normalise_weights,
    pareto_front,
    run_screening,
    screen_must_pass,
    select_short_list,
    weight_crossovers,
    weight_robustness,
    weighted_ranking,
)


def _c(cid, **choices):
    return {"id": cid, "choices": choices}


def test_default_long_list_applies_rules():
    out = generate_long_list()
    ids = {c["id"] for c in out["concepts"]}
    assert out["n_combinations"] == len(out["concepts"]) + len(out["excluded"])
    assert not any(c["choices"]["host"] == "fpso" and c["choices"]["wells"] == "dry_tree"
                   for c in out["concepts"])
    assert not any(c["choices"]["host"] == "subsea_tieback"
                   and c["choices"]["oil_export"] != "via_host" for c in out["concepts"])
    assert all(e["reasons"] for e in out["excluded"])
    assert ids


def test_givens_fix_elements_and_reject_unknown_option():
    out = generate_long_list(givens={"drive": "water_injection", "power": "power_from_shore"})
    assert {c["choices"]["drive"] for c in out["concepts"]} == {"water_injection"}
    with pytest.raises(ValueError):
        generate_long_list(givens={"host": "flying_saucer"})


def test_capacity_variants_single_topology_warns():
    topo = dict(host="fpso", wells="subsea", oil_export="shuttle_tanker")
    concepts = [dict(_c(f"fpso_{q}", **topo), sizing={"plateau_kbopd": q}) for q in (100, 150, 200)]
    out = detect_capacity_variants(concepts)
    assert out["n_distinct_topologies"] == 1
    assert out["variant_groups"] == [["fpso_100", "fpso_150", "fpso_200"]]
    assert any("single topology" in w for w in out["warnings"])


def test_must_pass_needs_evidence_to_eliminate():
    concepts = [_c("a"), _c("b"), _c("c")]
    crit = [{"id": "depth", "name": "Water depth feasible"}]
    ass = {
        "a": {"depth": {"result": "pass", "evidence": "ok"}},
        "b": {"depth": {"result": "fail", "evidence": "TLP limit 1500 m < 2100 m"}},
        "c": {"depth": {"result": "fail"}},
    }
    out = screen_must_pass(concepts, crit, ass)
    assert out["passed"] == ["a"]
    assert [e["concept"] for e in out["eliminated"]] == ["b"]
    assert out["pending"][0]["concept"] == "c"
    assert "without evidence" in out["pending"][0]["open"][0]["open_question"]
    with pytest.raises(ValueError):
        screen_must_pass(concepts, crit, {"a": {"depth": {"result": "maybe"}}})


def test_normalisation_direction_and_weights():
    crit = [{"id": "npv", "weight": 3}, {"id": "capex", "weight": 1, "direction": COST}]
    w = normalise_weights(crit)
    assert w == pytest.approx({"npv": 0.75, "capex": 0.25})
    n = normalise_scores(["a", "b"], crit, {"a": {"npv": 10, "capex": 5}, "b": {"npv": 20, "capex": 9}})
    assert n["normalised"]["b"]["npv"] == 1.0 and n["normalised"]["a"]["capex"] == 1.0
    flat = normalise_scores(["a", "b"], crit, {"a": {"npv": 1, "capex": 1}, "b": {"npv": 1, "capex": 2}})
    assert flat["normalised"]["a"]["npv"] == 0.5 and flat["warnings"]
    with pytest.raises(ValueError):
        normalise_weights([{"id": "x", "weight": -1}])


def test_pareto_front():
    n = {"a": {"x": 1.0, "y": 0.0}, "b": {"x": 0.0, "y": 1.0}, "c": {"x": 0.5, "y": 0.5},
         "d": {"x": 0.4, "y": 0.4}}
    assert pareto_front(n) == ["a", "b", "c"]


def test_robustness_is_deterministic_and_sums():
    n = {"a": {"x": 1.0, "y": 0.0}, "b": {"x": 0.0, "y": 1.0}, "c": {"x": 0.6, "y": 0.6}}
    w = {"x": 0.5, "y": 0.5}
    r1 = weight_robustness(n, w, top_k=2, n_samples=300, seed=7)
    r2 = weight_robustness(n, w, top_k=2, n_samples=300, seed=7)
    assert r1 == r2
    assert sum(r1["p_first"].values()) == pytest.approx(1.0)
    assert sum(r1["p_top_k"].values()) == pytest.approx(2.0)


def test_crossover_found():
    n = {"a": {"x": 1.0, "y": 0.0}, "b": {"x": 0.0, "y": 1.0}}
    rows = {r["criterion"]: r for r in weight_crossovers(n, {"x": 0.7, "y": 0.3})}
    assert rows["y"]["new_leader"] == "b"
    assert 0.49 <= rows["y"]["crossover_weight"] <= 0.52


def test_short_list_diversity_reference_and_variants():
    concepts = [
        _c("fpso_100", host="fpso"), _c("fpso_150", host="fpso"),
        _c("semi", host="semi_submersible"), _c("tieback", host="subsea_tieback"),
    ]
    variants = detect_capacity_variants(concepts)
    ranking = weighted_ranking(
        {"fpso_100": {"x": 0.9}, "fpso_150": {"x": 0.95}, "semi": {"x": 0.5}, "tieback": {"x": 0.2}},
        {"x": 1.0},
    )
    out = select_short_list(ranking, None, size=3, concepts=concepts, reference_ids=["tieback"],
                            family_of=variants["family_of"])
    ids = [s["concept"] for s in out["short_list"]]
    assert ids[0] == "fpso_150"
    assert "fpso_100" not in ids  # capacity variant occupies one slot
    assert "semi" in ids and "tieback" in ids


def _study():
    return {
        "givens": {"drive": "water_injection"},
        "elements": {
            "host": ["fpso", "semi_submersible", "subsea_tieback"],
            "wells": ["subsea"],
            "oil_export": ["shuttle_tanker", "via_host"],
            "gas_disposal": ["reinjection", "via_host"],
            "drive": ["water_injection"],
            "power": ["gas_turbine", "power_from_host"],
        },
        "must_pass": [{"id": "host_reach", "name": "Host within reach"}],
        "assessments": {
            "subsea_tieback|subsea|via_host|via_host|water_injection|power_from_host": {
                "host_reach": {"result": "fail", "evidence": "Nearest host 180 km, step-out limit 50 km"}
            }
        },
        "criteria": [
            {"id": "npv", "weight": 0.5},
            {"id": "capex", "weight": 0.3, "direction": "cost"},
            {"id": "co2", "weight": 0.2, "direction": "cost"},
        ],
        "scores": {
            "fpso|subsea|shuttle_tanker|reinjection|water_injection|gas_turbine":
                {"npv": 5.0, "capex": 6.0, "co2": 12},
            "semi_submersible|subsea|shuttle_tanker|reinjection|water_injection|gas_turbine":
                {"npv": 4.2, "capex": 5.5, "co2": 11},
        },
        "reference": ["fpso|subsea|shuttle_tanker|reinjection|water_injection|gas_turbine"],
        "short_list_size": 2,
        "robustness": {"n_samples": 200, "seed": 3},
    }


def test_run_screening_end_to_end():
    out = run_screening(_study())
    assert out["readiness"] == READINESS_LABEL
    assert out["human_review_required"] is True
    assert len(out["long_list"]) == 3
    assert any(e["stage"] == "must_pass" for e in out["elimination_log"])
    assert {s["concept"] for s in out["short_list"]} == set(out["decision_matrix"])
    assert out["crossovers"] and out["robustness"]["n_samples"] == 200
    assert out["excluded_by_rules"]


def test_coverage_warns_only_for_undecided_elements():
    from concept_longlist_shortlist import coverage_report

    concepts = [_c("a", host="fpso", wells="subsea"), _c("b", host="semi", wells="subsea")]
    framed = coverage_report(concepts, {"host": ["fpso", "semi"], "wells": ["subsea"]})
    assert framed["warnings"] == []
    open_frame = coverage_report(concepts, {"host": ["fpso", "semi"], "wells": ["subsea", "dry_tree"]})
    assert open_frame["missing"] == {"wells": ["dry_tree"]}
    assert any("wells" in w for w in open_frame["warnings"])


def test_contenders_do_not_overflow_short_list():
    n = {c: {"x": v} for c, v in zip("abcdef", (0.9, 0.89, 0.88, 0.87, 0.86, 0.1))}
    ranking = weighted_ranking(n, {"x": 1.0})
    robust = {"p_top_k": {c: 0.9 for c in n}, "top_k": 3}
    out = select_short_list(ranking, robust, size=3, reference_ids=["f"])
    assert [s["concept"] for s in out["short_list"]] == ["a", "b", "f"]
    assert out["warnings"] == [] or all("single topology" in w for w in out["warnings"])
