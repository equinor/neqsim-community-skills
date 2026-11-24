"""Tests for the illustration source register (asset_scene.register)."""

from asset_scene import register as rg

SRC = {"type": "STID datasheet", "file": "references/stid/x.pdf", "doc_no": "11-1A-X", "revision": "02", "page": "5"}


def _ok():
    return [
        rg.element("VA 20900", "equipment", "SOURCED", ["f1.png"], source=SRC),
        rg.element("Toppunkt LP", "value", "DERIVED", ["f1.png"], source={"type": "results.json", "file": "results.json"},
                   neqsim_binding={"unit": "lumped:LP", "address": "peak_barg", "value": 45.77, "tolerance_rel": 0.01}),
        rg.element("jakke", "structure", "ASSUMED", ["f1.png"], reason="geometri ikke i STID"),
    ]


def test_clean_register_passes_with_fresh_value_and_labelled_assumptions():
    reg = _ok()
    f = rg.check_register(reg, fresh=lambda b: 45.80, legend_texts={"f1.png": "Antatt/skjematisk: jakke"})
    assert rg.register_status(f) == "PASS", f


def test_missing_source_and_reason_fail():
    reg = [rg.element("A", "equipment", "SOURCED", ["f.png"]), rg.element("B", "equipment", "ASSUMED", ["f.png"]), rg.element("C", "equipment", "GUESS", ["f.png"])]
    codes = {x["code"] for x in rg.check_register(reg)}
    assert {"NO_SOURCE", "NO_REASON", "NO_STATUS"} <= codes
    assert rg.register_status(rg.check_register(reg)) == "FAIL"


def test_stale_bound_value_fails():
    f = rg.check_register(_ok(), fresh=lambda b: 52.0)
    assert any(x["code"] == "STALE_VALUE" for x in f) and rg.register_status(f) == "FAIL"


def test_assumed_must_be_declared_in_legend():
    f = rg.check_register(_ok(), legend_texts={"f1.png": "Trykk i bara"})
    assert any(x["code"] == "ASSUMED_NOT_LABELLED" for x in f)


def test_fresh_failure_and_bad_binding_reported():
    def boom(b):
        raise RuntimeError("model missing")

    assert any(x["code"] == "FRESH_FAILED" for x in rg.check_register(_ok(), fresh=boom))
    bad = [rg.element("V", "value", "DERIVED", ["f.png"], source={"type": "r", "file": "r.json"}, neqsim_binding={"unit": "u"})]
    assert any(x["code"] == "BAD_BINDING" for x in rg.check_register(bad))


def test_legend_markdown_and_roundtrip(tmp_path):
    reg = _ok()
    assert "jakke" in rg.legend_line(reg, "f1.png") and "antatt" in rg.legend_line(reg, "f1.png").lower()
    md = rg.to_markdown(reg)
    assert "VA 20900" in md and "ANTATT" in md and "lumped:LP" in md
    p = tmp_path / "r.json"
    rg.save(reg, str(p))
    assert rg.load(str(p)) == reg


def test_legend_line_truncation_has_single_period_and_markdown_shows_revision():
    reg = [rg.element("A%d" % i, "structure", "ASSUMED", ["f.png"], reason="r") for i in range(20)]
    line = rg.legend_line(reg, "f.png", max_items=3)
    assert line.endswith("m.fl.") and not line.endswith("..")
    sourced = [rg.element("P&ID", "line", "SOURCED", ["f.png"], source={"type": "STID", "file": "x.pdf", "doc_no": "11-1A-HM-C78-20030", "revision": "11L", "page": "1"})]
    assert "rev. 11L" in rg.to_markdown(sourced) and "s. 1" in rg.to_markdown(sourced)
