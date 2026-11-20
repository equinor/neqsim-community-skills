import numpy as np
import pytest

pytest.importorskip("matplotlib")

from flare_helideck_dispersion import style as st
from flare_helideck_dispersion.figures import section_field
from flare_helideck_dispersion.overlay import (
    DEFAULT_DISCLAIMER,
    MANDATORY_PHRASE,
    EmptyViewError,
    OverlayLabel,
    compose_overlay_figure,
    ensure_disclaimer,
    nice_scale_length_m,
    overlay_section_on_image,
)
from flare_helideck_dispersion.wind import pasquill_by_speed

SKY = np.dstack([np.linspace(0.3, 0.7, 640)[None, :].repeat(360, 0)] * 3)


@pytest.fixture(scope="module")
def section(coarse_study):
    rel = coarse_study.releases["cold"]
    stab = pasquill_by_speed(3.0)
    return section_field(
        rel,
        60.0,
        3.0,
        stab,
        coarse_study.receptors,
        (-50.0, 1800.0),
        (2.0, 300.0),
        10.0,
        3.0,
    )


def texts_of(fig):
    return [t.get_text() for ax in fig.axes for t in ax.texts] + [
        t.get_text() for t in fig.texts
    ]


def test_disclaimer_is_mandatory_and_cannot_be_dropped():
    assert MANDATORY_PHRASE in DEFAULT_DISCLAIMER.lower()
    assert ensure_disclaimer(None) == DEFAULT_DISCLAIMER
    custom = ensure_disclaimer("my own text")
    assert MANDATORY_PHRASE in custom.lower() and "my own text" in custom
    assert (
        ensure_disclaimer("Schematic, not registered to the camera - custom")
        == "Schematic, not registered to the camera - custom"
    )


def test_overlay_carries_disclaimer_scale_bar_and_report_width(
    section, coarse_study, tmp_path
):
    s, z, f = section
    labels = [OverlayLabel("Helideck (schematic)", (240.0, 81.0))]
    res = overlay_section_on_image(
        SKY,
        (200.0, 180.0),
        0.1,
        s,
        z,
        f,
        124.0,
        tmp_path / "o.png",
        labels,
        keep_figure=True,
    )
    texts = " ".join(texts_of(res.figure)).lower()
    assert MANDATORY_PHRASE in texts
    assert "overlay scale" in texts and "both axes" in texts
    assert MANDATORY_PHRASE in res.disclaimer.lower()
    assert res.figure.get_size_inches()[0] == pytest.approx(st.W_FULL)
    assert res.problems == [] and res.max_pct_lfl >= 5.0
    assert (tmp_path / "o.png").exists()


def test_overlay_refuses_an_empty_view_and_bad_anchor(section, tmp_path):
    s, z, f = section
    with pytest.raises(EmptyViewError):
        overlay_section_on_image(
            SKY, (200.0, 180.0), 0.1, s, z, f * 0.0, 124.0, tmp_path / "e.png"
        )
    with pytest.raises(ValueError):
        overlay_section_on_image(
            SKY, (5000.0, 180.0), 0.1, s, z, f, 124.0, tmp_path / "e.png"
        )
    with pytest.raises(ValueError):
        overlay_section_on_image(
            SKY, (200.0, 180.0), 0.0, s, z, f, 124.0, tmp_path / "e.png"
        )
    with pytest.raises(FileNotFoundError):
        overlay_section_on_image(
            tmp_path / "missing.png",
            (1.0, 1.0),
            0.1,
            s,
            z,
            f,
            124.0,
            tmp_path / "e.png",
        )


def test_scale_bar_length_fits_the_image():
    assert nice_scale_length_m(0.75, 1792.0) == 500.0
    assert nice_scale_length_m(0.1, 640.0) * 0.1 <= 0.4 * 640.0


def test_composite_has_disclaimer_scale_bar_and_to_scale_side_panels(
    coarse_study, tmp_path
):
    res = compose_overlay_figure(
        coarse_study,
        "cold",
        60.0,
        3.0,
        SKY,
        (200.0, 180.0),
        0.1,
        tmp_path / "c.png",
        keep_figure=True,
    )
    fig = res.figure
    assert MANDATORY_PHRASE in " ".join(texts_of(fig)).lower()
    assert "overlay scale" in " ".join(texts_of(fig)).lower()
    assert fig.get_size_inches()[0] == pytest.approx(st.W_FULL)
    assert res.problems == []
    titles = [ax.get_title(loc="left") for ax in fig.axes]
    assert any(t.startswith("To scale: vertical section (scale x3") for t in titles)
    assert any(t == "To scale: plan view" for t in titles)
    plan = next(
        ax for ax in fig.axes if ax.get_title(loc="left") == "To scale: plan view"
    )
    assert plan.get_aspect() in (1.0, "equal")
    section_ax = next(
        ax for ax in fig.axes if "vertical section" in ax.get_title(loc="left")
    )
    assert section_ax.get_aspect() == pytest.approx(st.VERTICAL_EXAGGERATION)
    legend_labels = [t.get_text() for t in fig.legends[0].get_texts()]
    assert legend_labels[:5] == st.LFL_LABELS
