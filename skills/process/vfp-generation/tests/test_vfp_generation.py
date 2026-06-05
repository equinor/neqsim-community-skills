import math

from vfp_generation import (
    DEFAULT_THRESHOLDS,
    classify_named,
    classify_value,
    enforce_monotonic,
    format_eclipse_vfp,
    get_thresholds,
    parse_vfp_text,
)


# --- classify_value: factor mode -----------------------------------------
def test_factor_mode_pass_warn_fail():
    # limit 1000; pass at 1.0x, fail at 1.05x
    assert classify_value(1000.0, 1000.0, "factor", 1.0, 1.0, 1.05) == "PASS"
    assert classify_value(1020.0, 1000.0, "factor", 1.0, 1.0, 1.05) == "WARN"
    assert classify_value(1050.0, 1000.0, "factor", 1.0, 1.0, 1.05) == "FAIL"


# --- classify_value: offset mode -----------------------------------------
def test_offset_mode_pass_warn_fail():
    # motor power vs 500 MW limit, pass_at 1.0, fail_at 0.0
    assert classify_value(498.0, 500.0, "offset", 1.0, 0.5, 0.0) == "PASS"
    assert classify_value(499.5, 500.0, "offset", 1.0, 0.5, 0.0) == "WARN"
    assert classify_value(500.5, 500.0, "offset", 1.0, 0.5, 0.0) == "FAIL"


# --- classify_value: margin_pct mode -------------------------------------
def test_margin_pct_mode():
    assert classify_value(20.0, 0.0, "margin_pct", 10.0, 5.0, 5.0) == "PASS"
    assert classify_value(7.0, 0.0, "margin_pct", 10.0, 5.0, 5.0) == "WARN"
    assert classify_value(3.0, 0.0, "margin_pct", 10.0, 5.0, 5.0) == "FAIL"


def test_default_thresholds_cover_eight_constraints():
    expected = {
        "motor_power", "discharge_temperature", "surge_margin",
        "stonewall_margin", "pipe_velocity", "scrubber_k_value",
        "chart_envelope", "max_casing_capacity",
    }
    assert expected.issubset(set(DEFAULT_THRESHOLDS))


def test_get_thresholds_overrides_and_classify_named():
    mode, p, w, f = get_thresholds("motor_power")
    assert mode == "offset"
    # override only warn_at
    mode2, p2, w2, f2 = get_thresholds("motor_power", (None, None, 0.7, None))
    assert mode2 == "offset" and p2 == p and w2 == 0.7 and f2 == f
    assert classify_named("motor_power", 498.0, 500.0) == "PASS"


# --- monotonic ------------------------------------------------------------
def test_enforce_monotonic_lifts_dips():
    rows = [[10.0, 9.0, 12.0, 11.0]]
    assert enforce_monotonic(rows) == [[10.0, 10.0, 12.0, 12.0]]


def test_enforce_monotonic_skips_nan():
    rows = [[10.0, math.nan, 8.0]]
    out = enforce_monotonic(rows)
    assert out[0][0] == 10.0
    assert math.isnan(out[0][1])
    assert out[0][2] == 10.0  # lifted up to running max


# --- export validation ----------------------------------------------------
def test_format_eclipse_vfp_validates_shape():
    try:
        format_eclipse_vfp(1, 335.0, [1e6, 2e6], [80.0], [[40.0]])
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for mismatched matrix shape")


# --- round trip -----------------------------------------------------------
def test_export_parse_round_trip():
    flow = [1.0e6, 5.0e6, 1.0e7]
    pout = [80.0, 100.0, 120.0]
    matrix = [
        [40.0, 50.0, 60.0],
        [55.0, 65.0, 75.0],
        [70.0, 80.0, 90.0],
    ]
    text = format_eclipse_vfp(7, 335.0, flow, pout, matrix,
                              traceability={"conf_id": "demo"})
    tables = parse_vfp_text(text, source_file="demo.VFP")
    assert len(tables) == 1
    tbl = tables[0]
    assert tbl.table_id == 7
    assert tbl.datum_depth == 335.0
    assert [round(q) for q in tbl.flow_rates] == [round(q) for q in flow]
    assert tbl.outlet_pressures == pout
    for r_out, r_in in zip(tbl.inlet_pressures, matrix):
        assert [round(v, 3) for v in r_out] == [round(v, 3) for v in r_in]


def test_failure_value_written_for_nan():
    text = format_eclipse_vfp(1, 335.0, [1e6, 2e6], [80.0],
                              [[40.0, math.nan]], failure_value=999.0)
    tables = parse_vfp_text(text)
    assert tables[0].inlet_pressures[0][0] == 40.0
    assert tables[0].inlet_pressures[0][1] == 999.0


def test_vfp_table_label_and_msm3d():
    text = format_eclipse_vfp(3, 335.0, [1e6], [80.0], [[40.0]],
                              traceability={"conf_id": "X"})
    tbl = parse_vfp_text(text)[0]
    assert tbl.flow_rates_MSm3d[0] == 1.0
    assert "T3" in tbl.default_label
