"""Tests for the concept screening figures."""

import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("matplotlib")

from concept_longlist_shortlist import (  # noqa: E402
    funnel_counts,
    plot_concept_schematic,
    render_screening_figures,
    run_screening,
)

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "basic_screening.py"


def _example_result():
    spec = importlib.util.spec_from_file_location("basic_screening_fig", EXAMPLE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod, run_screening(mod.study)


def test_funnel_counts_are_monotonic_and_match_result():
    _, result = _example_result()
    counts = [c for _, c in funnel_counts(result)]
    assert counts == sorted(counts, reverse=True)
    assert counts[0] == result["n_combinations"]
    assert counts[-1] == len(result["short_list"])


def test_render_screening_figures_writes_traceable_entries(tmp_path):
    mod, result = _example_result()
    entries = render_screening_figures(result, tmp_path, elements=list(mod.ELEMENTS))
    ids = {e["id"] for e in entries}
    assert {"fig_concept_funnel", "fig_decision_matrix", "fig_pareto"} <= ids
    assert sum(i.startswith("fig_concept_schematic_") for i in ids) == len(
        result["short_list"]
    )
    for e in entries:
        assert Path(e["path"]).stat().st_size > 1000
        assert e["caption"] and e["linked_results"]


def test_schematic_rejects_wrong_element_count():
    with pytest.raises(ValueError):
        plot_concept_schematic("fpso|subsea", ["host", "wells", "power"])


def test_schematic_accepts_mapping_and_key_facts(tmp_path):
    out = tmp_path / "s.png"
    plot_concept_schematic(
        {"host": "fpso", "wells": "subsea", "power": "power_from_shore"},
        key_facts=[("Plateau", "from results")],
        path=out,
    )
    assert out.stat().st_size > 1000
