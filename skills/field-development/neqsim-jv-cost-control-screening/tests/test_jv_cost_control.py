import numpy as np
import pandas as pd
import pytest

from jv_cost_control import (
    check_identities,
    check_subtotals,
    interest_share_check,
    outlier_months,
    parse_hierarchical_rows,
    price_volume_split,
    reconcile_tables,
    rollforward_check,
    run_rate_outlook,
    variance_commentary,
    variance_table,
)
from jv_cost_control.hierarchy import to_number

VALUES = {"cm": 4, "ytd": 5}


def _rows(total_override=None):
    """Synthetic statement: label cols 0-3, value cols 4-5.

    Two groups under one category, a subtotal per group, a TOTAL for the
    category and a grand total of the group totals.
    """
    cm_total = 30.0 if total_override is None else total_override
    return [
        ["Area A", "EXPENDITURES", "Drilling", None, 10.0, 100.0],
        [None, None, None, None, 20.0, 200.0],
        [None, None, "TOTAL Drilling", None, cm_total, 300.0],
        [None, None, "Facilities", None, 5.0, 50.0],
        [None, None, "TOTAL Facilities", None, 5.0, 50.0],
        [None, "TOTAL EXPENDITURES", None, None, 35.0, 350.0],
    ]


def test_to_number_handles_text_and_negatives():
    assert to_number("1,250.5") == 1250.5
    assert to_number("(10)") == -10.0
    assert to_number("  ") is None
    assert to_number("abc") is None
    assert to_number(True) is None


def test_hierarchy_ties_out():
    parsed = parse_hierarchical_rows(_rows(), range(4), VALUES)
    assert len(parsed.detail) == 3
    assert len(parsed.totals) == 3
    assert check_subtotals(parsed).empty


def test_grand_total_uses_sibling_totals():
    parsed = parse_hierarchical_rows(_rows(), range(4), VALUES)
    kinds = parsed.totals.set_index("label")["kind"].to_dict()
    assert kinds["TOTAL EXPENDITURES"] == "subtotal"


def test_subtotal_mismatch_is_reported():
    parsed = parse_hierarchical_rows(_rows(total_override=31.5), range(4), VALUES)
    bad = check_subtotals(parsed)
    assert len(bad) >= 1
    assert bad.iloc[0]["max_abs_diff"] == pytest.approx(1.5)


def test_net_zero_details_are_not_a_grand_total():
    rows = [
        ["Area B", "EXPENDITURES", "Studies", None, 5.0, 5.0],
        [None, None, None, None, -5.0, -5.0],
        [None, None, "TOTAL Studies", None, 0.0, 0.0],
    ]
    parsed = parse_hierarchical_rows(rows, range(4), VALUES)
    assert parsed.totals.iloc[0]["kind"] == "subtotal"
    assert check_subtotals(parsed).empty


def test_empty_arguments_rejected():
    with pytest.raises(ValueError):
        parse_hierarchical_rows([], [], VALUES)


def test_variance_table_flags_material_and_unbudgeted():
    df = pd.DataFrame(
        {
            "acct": ["a", "b", "c", "d"],
            "actual": [120.0, 52.0, 30.0, 1.0],
            "budget": [100.0, 50.0, 0.0, 0.0],
        }
    )
    table = variance_table(df, "actual", "budget", ["acct"], abs_threshold=10.0, pct_threshold=0.10)
    flags = table.set_index("acct")["material"].to_dict()
    assert flags == {"a": True, "b": False, "c": True, "d": False}
    assert table.iloc[0]["acct"] == "c" or table.iloc[0]["acct"] == "a"
    commentary = variance_commentary(table, ["acct"], "actual", "budget", top_n=5)
    assert len(commentary) == 2
    assert commentary[0]["reason"].startswith("TO BE CONFIRMED")


def test_price_volume_split_adds_up():
    split = price_volume_split(415.6, 38.4, 360.9, 40.3)
    assert split["volume_effect"] + split["rate_effect"] == pytest.approx(split["total"])
    with pytest.raises(ValueError):
        price_volume_split(1.0, 0.0, 1.0, 1.0)


def test_run_rate_outlook():
    result = run_rate_outlook(60.0, 6, full_year_ref=100.0)
    assert result["run_rate_full_year"] == pytest.approx(120.0)
    assert result["vs_reference"] == pytest.approx(20.0)
    with pytest.raises(ValueError):
        run_rate_outlook(1.0, 0)


def test_outlier_months_uses_mad():
    series = pd.Series([10.0, 10.2, 9.9, 10.1, 25.0, 10.0])
    flags = outlier_months(series)
    assert flags.tolist() == [False, False, False, False, True, False]
    assert not outlier_months(pd.Series([5.0, 5.0, 5.0])).any()


def test_reconcile_statuses():
    a = pd.DataFrame({"k": ["x", "y", "z"], "v": [100.0, 200.0, 5.0]})
    b = pd.DataFrame({"k": ["x", "y", "w"], "v": [100.0, 150.0, 7.0]})
    result = reconcile_tables(a, b, ["k"], "v", "v", tol_abs=1.0, names=("jib", "crr")).set_index("k")
    assert result.loc["x", "status"] == "MATCH"
    assert result.loc["y", "status"] == "DIFF"
    assert result.loc["z", "status"] == "ONLY_jib"
    assert result.loc["w", "status"] == "ONLY_crr"


def test_rollforward_flags_restatement():
    prior = pd.Series({"a": 100.0, "b": 50.0})
    month = pd.Series({"a": 10.0, "b": 5.0})
    ytd = pd.Series({"a": 110.0, "b": 70.0})
    result = rollforward_check(prior, month, ytd)
    assert bool(result.loc["b", "flag"]) and not bool(result.loc["a", "flag"])
    assert result.loc["b", "diff"] == pytest.approx(15.0)


def test_identities_and_safe_evaluation():
    values = {"RC10": 100.0, "RC12": 50.0, "RC13": 10.0, "RC14": 160.0}
    ok, bad, missing, unsafe = check_identities(
        values,
        [
            ("RC14", "RC14", "RC10 + RC12 + RC13"),
            ("RC14b", "RC14", "RC10 + RC12"),
            ("miss", "RC14", "RC99 + 1"),
            ("unsafe", "RC14", "__import__('os').getcwd()"),
        ],
    )
    assert ok.ok and not bad.ok and not missing.ok and not unsafe.ok
    assert bad.diff == pytest.approx(10.0)
    assert np.isnan(missing.lhs)


def test_interest_share_check():
    df = pd.DataFrame(
        {
            "gross": [1000.0, 2000.0, 3000.0, 4000.0],
            "share": [120.0, 266.66, 500.0, 480.0],
        }
    )
    failing = interest_share_check(df, "gross", "share", [0.12, 0.12 / 0.9])
    assert len(failing) == 1
    assert failing.iloc[0]["gross"] == 3000.0
    with pytest.raises(ValueError):
        interest_share_check(df, "gross", "share", [])
