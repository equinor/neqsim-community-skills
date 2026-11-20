import numpy as np
import pytest

pytest.importorskip("matplotlib")

from flare_helideck_dispersion import BenchmarkScenario, run_sensitivity
from flare_helideck_dispersion import style as st
from flare_helideck_dispersion.figures import (
    fig_footprints,
    make_all_figures,
    select_scenarios,
)
from flare_helideck_dispersion.study import helideck_peak_over_directions
from matplotlib.image import imread


@pytest.fixture(scope="module")
def sens(coarse_study, wind, cases):
    return run_sensitivity(
        cases,
        wind,
        coarse_study.receptors,
        coarse_study.settings,
        tilt_scan_cases=["warm", "cold"],
        uncertainty_cases=["warm", "cold"],
        tilts_deg=(30.0, 60.0),
        n_samples=2,
        ranges={"tilt_deg": (40.0, 50.0), "mass_flow_scale": (0.8, 1.2)},
    )


@pytest.fixture(scope="module")
def scenarios(cases):
    return [
        BenchmarkScenario("warm 4 m/s", cases[0], 4.0, "illustrative", "test", 0.0),
        BenchmarkScenario("cold 2 m/s", cases[1], 2.0, "illustrative", "test", 0.0),
    ]


@pytest.fixture(scope="module")
def records(coarse_study, sens, scenarios, tmp_path_factory):
    folder = tmp_path_factory.mktemp("figures")
    return make_all_figures(coarse_study, str(folder), sens, scenarios)


def by_label(records, label):
    return next(r for r in records if label in r.name)


def test_every_figure_has_report_width_and_no_layout_problems(records):
    assert len(records) >= 11
    for rec in records:
        assert rec.width_in == pytest.approx(st.W_FULL), rec.name
        assert rec.problems == [], (rec.name, rec.problems)
        img = imread(rec.paths[0])
        assert img.shape[1] == round(st.W_FULL * st.DPI), rec.name
        assert float(np.std(img[..., :3])) > 0.02, f"{rec.name} looks empty"
        assert rec.height_in <= 9.0


def test_titles_state_a_finding_with_numbers_and_fit_two_lines(records):
    for rec in records:
        assert 20 < len(rec.title) <= 160, rec.name
        assert rec.sub, rec.name
        assert any(
            ch.isdigit() for ch in rec.title
        ), f"{rec.name} title carries no number"
        text = rec.figure.texts
        head = next(t for t in text if t.get_gid() == "headline")
        assert head.get_text().count("\n") <= 1
        assert head.get_fontweight() == "bold"


def test_no_table_is_repeated_as_a_figure(records):
    assert not any("table" in r.name or "summary" in r.name for r in records)
    assert len({r.name for r in records}) == len(records)


def test_text_is_page_width_sized(records):
    for rec in records:
        for ax in rec.figure.axes:
            for lab in ax.get_xticklabels() + ax.get_yticklabels():
                if lab.get_text():
                    assert 5.0 <= lab.get_fontsize() <= 9.0, rec.name


def test_layout_checker_detects_title_overlapping_axes():
    fig = st.new_fig(2.0, constrained=False)
    ax = fig.add_axes([0.1, 0.1, 0.8, 0.85])
    ax.plot([0, 1], [0, 1])
    st.headline(fig, "A long headline that is placed on top of the axes", "sub")
    problems = st.layout_problems(fig)
    assert any("overlaps axes" in p for p in problems)
    fig2 = st.new_fig(3.0)
    fig2.add_subplot(1, 1, 1).plot([0, 1], [0, 1])
    st.lfl_legend(fig2)
    st.headline(fig2, "Clean layout keeps margins", "sub")
    assert st.layout_problems(fig2) == []
    with pytest.raises(ValueError):
        st.headline(st.new_fig(2.0), "word " * 60)


def test_lfl_legend_is_shared_and_at_the_bottom():
    fig = st.new_fig(3.0)
    fig.add_subplot(1, 1, 1)
    st.lfl_legend(fig)
    legend = fig.legends[0]
    labels = [t.get_text() for t in legend.get_texts()]
    assert labels[:5] == st.LFL_LABELS
    assert labels[5:] == ["10 % LFL contour", "20 % LFL contour"]
    assert legend._loc == 8  # lower center
    assert len(st.LFL_COLORS) == len(st.LFL_LABELS) == len(st.LFL_LEVELS) - 1


def test_peak_text_is_capped_and_floored():
    assert st.peak_text(500.0) == "> 100 % LFL"
    assert st.peak_text(0.01) == "< 0.1 % LFL"
    assert st.peak_text(42.3) == "42 % LFL"


def test_plan_conventions(coarse_study):
    fig = st.new_fig(4.0, constrained=False)
    ax = fig.add_subplot(1, 1, 1)
    extent = st.plan_extent(coarse_study.receptors)
    st.plan_base(ax, coarse_study.receptors, extent)
    st.wind_box(ax, 60.0, 3.0, "Wind from 060 deg\n3.0 m/s, class E")
    assert ax.get_aspect() in (1.0, "equal")
    assert ax.get_xlim() == extent[0] and ax.get_ylim() == extent[1]
    texts = [t.get_text() for t in ax.texts]
    assert "N" in texts and any(t.startswith("Wind from 060") for t in texts)
    assert next(t.get_text() for t in ax.get_xticklabels()) != ""  # km labels
    markers = {l.get_marker() for l in ax.lines}
    assert "*" in markers and "H" in markers
    # the extent contains every flight path point
    pts = coarse_study.receptors.all_paths
    assert extent[0][0] <= pts[:, 0].min() and pts[:, 0].max() <= extent[0][1]
    assert extent[1][0] <= pts[:, 1].min() and pts[:, 1].max() <= extent[1][1]


def test_footprints_show_flight_path_peaks_and_something(coarse_study, tmp_path):
    rec = fig_footprints(coarse_study, "cold", str(tmp_path), "fp.png")
    texts = [t.get_text() for ax in rec.figure.axes for t in ax.texts]
    assert sum(t.startswith("peak on flight paths:") for t in texts) == 4
    assert max(rec.facts["flight_path_peaks"]) > 5.0, "no panel shows a cloud"
    scen = select_scenarios(coarse_study, "cold")
    assert scen[0][1] == pytest.approx(
        coarse_study.geometry.azimuth_toward_deck_wind_from_deg
    )
    pk = coarse_study.summaries["cold"]["modes"]["briggs"]["peak_any_path_condition"]
    assert (scen[1][1], scen[1][2]) == (pk["wind_from_deg"], pk["speed_m_s"])


def test_sections_state_vertical_exaggeration(records):
    rec = by_label(records, "vertical_sections")
    assert "exaggerated 3 times" in rec.sub
    for ax in rec.figure.axes:
        if ax.get_xlabel() or ax.get_ylabel():
            assert ax.get_aspect() == pytest.approx(3.0)


def test_sensitivity_axes_start_at_zero_and_are_shared(records):
    tornado = by_label(records, "tornado")
    axes = [a for a in tornado.figure.axes if a.get_xlabel()]
    assert len(axes) >= 2
    assert all(a.get_xlim()[0] == 0.0 for a in axes)
    assert len({a.get_xlim() for a in axes}) == 1
    tilt = by_label(records, "tilt")
    hours_axis = next(
        a for a in tilt.figure.axes if a.get_title(loc="left") == "Flight paths"
    )
    assert hours_axis.get_ylim()[0] == 0.0
    exceed = by_label(records, "exceedance")
    assert all(a.get_ylim()[0] == 0.0 for a in exceed.figure.axes)


def test_benchmark_figure_is_log_axis_with_computed_numeric_labels(
    records, coarse_study, scenarios
):
    rec = by_label(records, "benchmark")
    ax = rec.figure.axes[0]
    assert ax.get_xscale() == "log"
    lines = [l.get_xdata()[0] for l in ax.lines if len(l.get_xdata()) == 2]
    assert 20.0 in lines
    labels = [t.get_text() for t in ax.texts]
    assert sum("%" in t and "LFL" not in t for t in labels) == len(scenarios)
    for s in scenarios:
        peak = helideck_peak_over_directions(
            s, coarse_study.receptors, coarse_study.settings
        )["peak_pct_lfl"]
        assert rec.facts["peaks_pct_lfl"][s.label] == pytest.approx(max(peak, 1e-5))
    assert (
        "{:.2g}".format(rec.facts["worst_pct_lfl"]) in "".join(labels)
        or rec.facts["worst_pct_lfl"] <= 1.01e-5
    )


def test_heatmap_title_lists_computed_sectors(records, coarse_study):
    rec = by_label(records, "heatmaps")
    assert "20 % LFL" in rec.title
    for s in rec.facts["exposed_sectors"]:
        assert s in coarse_study.wind.sectors
