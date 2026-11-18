"""Regression tests for timestamp resolution and frozen-value masking."""

import numpy as np
import pandas as pd
import pytest
from dynamic_identification import align


@pytest.mark.parametrize("unit", ["s", "ms", "us", "ns"])
def test_align_infers_seconds_and_masks_frozen_values_without_mutating_input(unit):
    index = pd.date_range("2026-01-01", periods=100, freq="2s", tz="UTC").as_unit(unit)
    values = np.arange(100, dtype=float)
    values[40:60] = 7.0
    series = pd.Series(values, index=index)
    original = series.copy(deep=True)

    data = align({"f": series}, frozen_samples=10)

    assert data["timebase_s"] == 2.0
    pd.testing.assert_index_equal(data["times"].as_unit(unit), index, exact=False)
    expected = values.copy()
    expected[40:60] = np.nan
    np.testing.assert_array_equal(data["values"]["f"], expected)
    assert data["bad_fraction"]["f"] == pytest.approx(0.2)
    pd.testing.assert_series_equal(series, original)
