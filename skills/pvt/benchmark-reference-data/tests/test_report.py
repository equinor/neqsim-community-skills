from __future__ import annotations

import pytest

from benchmark_reference_data.comparison import STATUS_FAIL, STATUS_PASS, STATUS_WARN, compare
from benchmark_reference_data.reference_data import find_anchor
from benchmark_reference_data.report import BenchmarkReport


def _passing_report(count: int = 3) -> BenchmarkReport:
    report = BenchmarkReport(description="anchor set")
    anchors = [
        ("CO2 Tc", find_anchor("co2", "critical_temperature")),
        ("Methane Tc", find_anchor("methane", "critical_temperature")),
        ("Nitrogen Tc", find_anchor("nitrogen", "critical_temperature")),
        ("Ethane Tc", find_anchor("ethane", "critical_temperature")),
    ]
    for name, point in anchors[:count]:
        report.add(compare(name, point.value, point))
    return report


def test_overall_status_is_pass_when_all_cases_pass():
    assert _passing_report().overall_status == STATUS_PASS


def test_a_single_failure_dominates_the_overall_status():
    report = _passing_report()
    point = find_anchor("water", "critical_temperature")
    report.add(compare("Water Tc", 900.0, point))
    assert report.overall_status == STATUS_FAIL


def test_warn_dominates_pass_but_not_fail():
    report = _passing_report()
    point = find_anchor("water", "critical_temperature")
    report.add(compare("Water Tc", 647.096 * 1.015, point, tolerance_pct=1.0))
    assert report.overall_status == STATUS_WARN


def test_empty_report_is_informational():
    assert BenchmarkReport().overall_status == "INFO"


def test_minimum_points_gate_blocks_a_thin_benchmark():
    thin = _passing_report(count=2)
    assert not thin.meets_minimum_points()
    assert any("graded comparison" in b for b in thin.blockers())
    assert _passing_report(count=3).meets_minimum_points()


def test_blockers_report_failed_cases_by_name():
    report = _passing_report()
    report.add(compare("Water Tc", 900.0, find_anchor("water", "critical_temperature")))
    assert any("Water Tc" in b for b in report.blockers())


def test_dependent_reference_is_flagged_as_a_blocker():
    report = _passing_report()
    point = find_anchor("water", "critical_temperature")
    report.add(compare("Water Tc", point.value, point, model_tier="primary_standard"))
    assert any("not independent" in b for b in report.blockers())


def test_results_json_block_is_keyed_and_carries_a_summary():
    block = _passing_report().to_results_json()
    assert "co2_tc" in block
    summary = block["summary"]
    assert summary["status"] == STATUS_PASS
    assert summary["points"] == 3
    assert summary["graded_points"] == 3
    assert summary["passed"] == 3
    assert summary["failed"] == 0
    assert summary["blockers"] == "none"
    assert "span_wagner_co2" in summary["sources"]


def test_summary_fields_stay_scalar_for_the_report_renderer():
    summary = _passing_report().to_results_json()["summary"]
    for key, value in summary.items():
        assert isinstance(value, (str, int, float)), key


def test_duplicate_case_names_do_not_collide_in_the_block():
    report = BenchmarkReport()
    point = find_anchor("co2", "critical_temperature")
    report.add(compare("CO2 Tc", point.value, point))
    report.add(compare("CO2 Tc", point.value, point))
    block = report.to_results_json()
    assert "co2_tc" in block
    assert "co2_tc_2" in block


def test_results_json_list_form_names_each_entry():
    entries = _passing_report().to_results_json_list()
    assert [e["what"] for e in entries][0] == "CO2 Tc"


def test_citations_are_deduplicated():
    report = BenchmarkReport()
    point = find_anchor("co2", "critical_temperature")
    report.add(compare("a", point.value, point))
    report.add(compare("b", point.value, point))
    assert len(report.citations()) == 1


def test_markdown_table_has_a_row_per_case_and_a_status_line():
    text = _passing_report().to_markdown()
    assert text.count("| CO2 Tc |") == 1
    assert "Overall: **PASS**" in text


def test_markdown_lists_blockers_when_present():
    text = _passing_report(count=2).to_markdown()
    assert "Blockers:" in text


def test_counts_tally_every_status_bucket():
    counts = _passing_report().counts()
    assert counts[STATUS_PASS] == 3
    assert counts[STATUS_FAIL] == 0


def test_extend_appends_a_batch():
    report = BenchmarkReport()
    point = find_anchor("co2", "critical_pressure")
    report.extend([compare("p1", point.value, point), compare("p2", point.value, point)])
    assert len(report.results) == 2


def test_report_block_passes_the_task_gate_status_vocabulary():
    block = _passing_report().to_results_json()
    for key, value in block.items():
        if key == "summary":
            continue
        assert value["status"] in ("PASS", "FAIL", "WARN", "INFO")


def test_deviation_percent_is_rendered_for_a_non_exact_case():
    report = BenchmarkReport()
    point = find_anchor("co2", "critical_temperature")
    report.add(compare("CO2 Tc", point.value * 1.001, point))
    assert "+0.1" in report.to_markdown()
    assert report.results[0].deviation_pct == pytest.approx(0.1, abs=1e-6)
