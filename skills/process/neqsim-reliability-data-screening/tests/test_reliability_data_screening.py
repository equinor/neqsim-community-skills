import pytest

from reliability_data_screening import ReliabilityDataModel


def test_mtbf_from_failure_rate():
    model = ReliabilityDataModel()
    result = model.evaluate(failure_rate_per_year=0.5)
    assert result.mtbf_years == pytest.approx(2.0, rel=1e-6)
    assert result.mtbf_h == pytest.approx(17520.0, rel=1e-6)


def test_single_unit_availability():
    model = ReliabilityDataModel()
    result = model.evaluate(
        failure_rate_per_year=1.0,
        mean_time_to_repair_h=24.0,
        redundancy=1,
    )
    # A = 8760 / (8760 + 24) ~= 0.99727
    assert result.unit_availability == pytest.approx(8760.0 / (8760.0 + 24.0), rel=1e-6)
    assert result.system_availability == pytest.approx(result.unit_availability, rel=1e-6)


def test_redundancy_improves_availability():
    model = ReliabilityDataModel()
    single = model.evaluate(failure_rate_per_year=2.0, mean_time_to_repair_h=100.0, redundancy=1)
    dual = model.evaluate(failure_rate_per_year=2.0, mean_time_to_repair_h=100.0, redundancy=2)
    assert dual.system_availability > single.system_availability


def test_planned_downtime_reduces_availability():
    model = ReliabilityDataModel()
    without = model.evaluate(failure_rate_per_year=0.5, planned_downtime_h_per_year=0.0)
    with_dt = model.evaluate(failure_rate_per_year=0.5, planned_downtime_h_per_year=87.6)
    assert with_dt.system_availability < without.system_availability


def test_low_availability_warning():
    model = ReliabilityDataModel()
    result = model.evaluate(failure_rate_per_year=10.0, mean_time_to_repair_h=200.0)
    assert result.system_availability < 0.95
    assert result.availability_warning == "low-availability"


def test_assumptions_present():
    model = ReliabilityDataModel()
    result = model.evaluate(failure_rate_per_year=0.5)
    assert result.assumptions
    assert any("screening" in line.lower() for line in result.assumptions)


def test_invalid_redundancy_raises():
    model = ReliabilityDataModel()
    with pytest.raises(ValueError, match="redundancy"):
        model.evaluate(failure_rate_per_year=0.5, redundancy=0)


def test_invalid_planned_downtime_raises():
    model = ReliabilityDataModel()
    with pytest.raises(ValueError, match=r"\[0, 8760\)"):
        model.evaluate(failure_rate_per_year=0.5, planned_downtime_h_per_year=9000.0)
