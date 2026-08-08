from __future__ import annotations

import math

import pytest

from uncertainty_quantification.distributions import (
    Deterministic,
    DistributionError,
    LogNormal,
    Normal,
    Triangular,
    Uniform,
    from_spec,
)


def test_uniform_inverse_cdf_is_linear():
    dist = Uniform(name="p", low=10.0, high=20.0)
    assert dist.ppf(0.0) == pytest.approx(10.0, abs=1e-6)
    assert dist.ppf(0.5) == pytest.approx(15.0)
    assert dist.ppf(1.0) == pytest.approx(20.0, abs=1e-6)


def test_uniform_rejects_inverted_bounds():
    with pytest.raises(DistributionError):
        Uniform(name="p", low=20.0, high=10.0)


def test_triangular_is_monotonic_and_spans_its_support():
    dist = Triangular(name="p", low=0.0, base_value=0.3, high=1.0)
    values = [dist.ppf(u / 100.0) for u in range(101)]
    assert values == sorted(values)
    assert values[0] == pytest.approx(0.0, abs=1e-5)
    assert values[-1] == pytest.approx(1.0, abs=1e-5)


def test_triangular_median_matches_the_closed_form():
    low, mode, high = 0.0, 0.3, 1.0
    dist = Triangular(name="p", low=low, base_value=mode, high=high)
    # For u > (mode-low)/(high-low) the median is high - sqrt(0.5*(high-low)*(high-mode)).
    expected = high - math.sqrt(0.5 * (high - low) * (high - mode))
    assert dist.ppf(0.5) == pytest.approx(expected)


def test_triangular_base_is_the_mode_not_the_median():
    dist = Triangular(name="p", low=0.0, base_value=0.3, high=1.0)
    assert dist.base() == pytest.approx(0.3)
    assert dist.base() != pytest.approx(dist.ppf(0.5))


def test_triangular_rejects_a_mode_outside_the_range():
    with pytest.raises(DistributionError):
        Triangular(name="p", low=0.0, base_value=2.0, high=1.0)


def test_normal_quantiles_are_symmetric_about_the_mean():
    dist = Normal(name="p", mu=10.0, sigma=2.0)
    assert dist.ppf(0.5) == pytest.approx(10.0)
    assert dist.ppf(0.9) - 10.0 == pytest.approx(10.0 - dist.ppf(0.1))


def test_normal_one_sigma_quantile_is_correct():
    dist = Normal(name="p", mu=0.0, sigma=1.0)
    assert dist.ppf(0.8413447) == pytest.approx(1.0, abs=1e-4)


def test_normal_rejects_non_positive_sigma():
    with pytest.raises(DistributionError):
        Normal(name="p", mu=0.0, sigma=0.0)


def test_lognormal_from_p10_p90_reproduces_those_quantiles():
    dist = LogNormal.from_p10_p90("p", 100.0, 400.0)
    assert dist.ppf(0.10) == pytest.approx(100.0, rel=1e-6)
    assert dist.ppf(0.90) == pytest.approx(400.0, rel=1e-6)


def test_lognormal_is_strictly_positive():
    dist = LogNormal.from_p10_p90("p", 1.0, 100.0)
    assert dist.ppf(1e-9) > 0.0


def test_lognormal_rejects_non_positive_quantiles():
    with pytest.raises(DistributionError):
        LogNormal.from_p10_p90("p", 0.0, 10.0)


def test_deterministic_ignores_the_quantile():
    dist = Deterministic(name="p", value=7.0)
    assert dist.ppf(0.0) == 7.0
    assert dist.ppf(1.0) == 7.0


def test_quantile_outside_the_unit_interval_is_rejected():
    with pytest.raises(DistributionError):
        Uniform(name="p", low=0.0, high=1.0).ppf(1.5)


def test_to_dict_matches_the_report_table_columns():
    row = Triangular(name="GIP", unit="GSm3", low=1.0, base_value=2.0, high=3.0).to_dict()
    assert row["name"] == "GIP"
    assert row["unit"] == "GSm3"
    assert row["low"] == 1.0
    assert row["base"] == 2.0
    assert row["high"] == 3.0
    assert row["distribution"] == "triangular"


def test_unbounded_distribution_reports_p10_p90_as_its_range():
    row = Normal(name="p", mu=0.0, sigma=1.0).to_dict()
    assert row["low"] == pytest.approx(-1.2816, abs=1e-3)
    assert row["high"] == pytest.approx(1.2816, abs=1e-3)


def test_from_spec_builds_each_supported_type():
    triangular = from_spec(
        {"name": "GIP", "distribution": "triangular", "low": 1.0, "base": 2.0, "high": 3.0}
    )
    assert isinstance(triangular, Triangular)
    lognormal = from_spec(
        {"name": "k", "distribution": "lognormal", "low": 10.0, "high": 100.0}
    )
    assert isinstance(lognormal, LogNormal)
    fixed = from_spec({"name": "d", "distribution": "deterministic", "value": 5.0})
    assert fixed.base() == 5.0


def test_from_spec_rejects_an_unknown_distribution():
    with pytest.raises(DistributionError) as excinfo:
        from_spec({"name": "p", "distribution": "weibull"})
    assert "triangular" in str(excinfo.value)


def test_kind_defaults_to_technical_and_can_be_set_to_economic():
    assert Uniform(name="p", low=0.0, high=1.0).kind == "technical"
    assert Uniform(name="p", low=0.0, high=1.0, kind="economic").kind == "economic"
