import pytest

from digital_twin_validation import (
    ChannelSpec,
    Tolerance,
    ValidationReport,
    check_tolerance,
    evaluate_point,
)


def _specs() -> list[ChannelSpec]:
    return [
        ChannelSpec("p", Tolerance(0.5, "abs"), unit="bara"),
        ChannelSpec("t", Tolerance(2.0, "abs"), unit="C"),
        ChannelSpec("power", Tolerance(5.0, "pct"), unit="MW"),
    ]


def test_check_tolerance_absolute_pass_and_fail() -> None:
    passed, diff, rel = check_tolerance(60.0, 60.3, Tolerance(0.5, "abs"))
    assert passed is True
    assert diff == pytest.approx(0.3)

    failed, _, _ = check_tolerance(60.0, 61.0, Tolerance(0.5, "abs"))
    assert failed is False


def test_check_tolerance_percent() -> None:
    passed, _, rel = check_tolerance(12.0, 12.4, Tolerance(5.0, "pct"))
    assert passed is True
    assert rel == pytest.approx(0.4 / 12.0 * 100)

    failed, _, _ = check_tolerance(12.0, 13.0, Tolerance(5.0, "pct"))
    assert failed is False


def test_point_passes_when_all_decided_channels_pass() -> None:
    point = evaluate_point(
        "A",
        measured={"p": 60.0, "t": 95.0, "power": 12.0},
        simulated={"p": 60.3, "t": 96.2, "power": 12.4},
        specs=_specs(),
    )
    assert point.status == "PASS"


def test_missing_simulated_channel_is_skipped_not_failed() -> None:
    point = evaluate_point(
        "B",
        measured={"p": 58.0, "t": 90.0, "power": 11.0},
        simulated={"p": 59.2, "t": 90.5},  # power missing
        specs=_specs(),
    )
    # p within 0.5? 1.2 -> FAIL actually. Use a passing p instead.
    assert point.status == "FAIL"
    power_ch = next(c for c in point.channels if c.channel == "power")
    assert power_ch.passed is None


def test_point_skip_when_no_channel_decided() -> None:
    point = evaluate_point(
        "C",
        measured={"p": 58.0},
        simulated={},
        specs=_specs(),
    )
    assert point.status == "SKIP"


def test_report_pass_rate_and_status() -> None:
    report = ValidationReport(name="demo")
    report.add(evaluate_point(
        "A",
        measured={"p": 60.0, "t": 95.0, "power": 12.0},
        simulated={"p": 60.3, "t": 96.2, "power": 12.4},
        specs=_specs(),
    ))
    report.add(evaluate_point(
        "B",
        measured={"p": 58.0, "t": 90.0, "power": 11.0},
        simulated={"p": 62.0, "t": 90.5, "power": 11.1},  # p fails
        specs=_specs(),
    ))
    assert report.pass_rate() == pytest.approx(0.5)
    assert report.status == "FAIL"


def test_report_html_contains_table_and_verdicts() -> None:
    report = ValidationReport(name="demo")
    report.add(evaluate_point(
        "A",
        measured={"p": 60.0, "t": 95.0, "power": 12.0},
        simulated={"p": 60.3, "t": 96.2, "power": 12.4},
        specs=_specs(),
    ))
    html = report.to_html()
    assert "<table" in html
    assert "PASS" in html
    assert "demo" in html


def test_tolerance_rejects_non_positive_value() -> None:
    with pytest.raises(ValueError):
        Tolerance(0.0, "abs")


def test_tolerance_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError):
        Tolerance(1.0, "relative")
