"""Schematic overlay of a plume section on a user-supplied image.

The overlay is anchored at one pixel (the release point in the image) and uses one scale
(pixels per metre) in both axes. It is NOT registered to the camera: the image carries no
camera parameters, so perspective, lens distortion and depth are ignored. Every overlay
therefore carries the mandatory disclaimer ``Schematic, not registered to the camera``
and a scale bar, and the composite adds to-scale side panels (vertical section and plan)
that are the quantitative figures.

Any image can be used (a rendering, a photo, a drawing); this module neither fetches nor
stores images.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from matplotlib.image import imread
from matplotlib.patches import Rectangle

from . import style as st
from .figures import (
    plan_field,
    section_field,
    section_zmax,
)
from .study import StudyResult
from .wind import pasquill_by_speed

MANDATORY_PHRASE = "schematic, not registered to the camera"
"""Text that every overlay must contain (case-insensitive)."""
DEFAULT_DISCLAIMER = (
    "Schematic, not registered to the camera: overlay anchored at the user-supplied "
    "release pixel, one scale in both axes."
)


class EmptyViewError(ValueError):
    """Raised when an overlay would show no cloud inside the image."""


@dataclass
class OverlayLabel:
    """A text box with an arrow to a point of the section.

    Attributes:
        text: Label text.
        target_section: ``(distance_m, height_asl_m)`` of the point in the section.
        text_px: Pixel position of the text box centre; ``None`` places it automatically.
        color: Box colour.
    """

    text: str
    target_section: tuple[float, float]
    text_px: tuple[float, float] | None = None
    color: str = st.NAVY


@dataclass
class OverlayResult:
    """Result of an overlay.

    Attributes:
        path: Saved file.
        disclaimer: Disclaimer text drawn on the image.
        anchor_px: Anchor pixel.
        px_per_m: Overlay scale.
        max_pct_lfl: Maximum percent of the LFL of the section.
        scale_bar_m: Length of the drawn scale bar, m.
        problems: Layout problems (empty when none).
        figure: The figure when ``keep_figure`` was requested.
    """

    path: str
    disclaimer: str
    anchor_px: tuple[float, float]
    px_per_m: float
    max_pct_lfl: float
    scale_bar_m: float
    problems: list[str] = field(default_factory=list)
    figure: Any = None


def ensure_disclaimer(text: str | None) -> str:
    """Return a disclaimer that contains the mandatory phrase.

    A custom text that lacks the phrase is prefixed with the default disclaimer; the
    phrase can never be dropped.

    Args:
        text: Custom disclaimer or ``None``.

    Returns:
        Disclaimer text containing :data:`MANDATORY_PHRASE`.
    """
    if not text:
        return DEFAULT_DISCLAIMER
    if MANDATORY_PHRASE in text.lower():
        return text
    return DEFAULT_DISCLAIMER + "\n" + text


def load_image(image: str | Path | np.ndarray) -> np.ndarray:
    """Load an image as an array.

    Args:
        image: Path to a PNG/JPEG file or an array.

    Returns:
        Image array ``(height, width[, channels])``.

    Raises:
        FileNotFoundError: If the path does not exist.
    """
    if isinstance(image, np.ndarray):
        return image
    p = Path(image)
    if not p.exists():
        raise FileNotFoundError(f"overlay image not found: {p}")
    return imread(str(p))


def nice_scale_length_m(
    px_per_m: float, image_width_px: float, max_fraction: float = 0.4
) -> float:
    """Largest round length whose bar fits within a fraction of the image width.

    Args:
        px_per_m: Overlay scale.
        image_width_px: Image width, pixels.
        max_fraction: Maximum bar length as a fraction of the width.

    Returns:
        Bar length, m.
    """
    options = [50.0, 100.0, 200.0, 250.0, 500.0, 1000.0, 2000.0, 5000.0]
    fits = [m for m in options if m * px_per_m <= max_fraction * image_width_px]
    return fits[-1] if fits else options[0]


def draw_overlay(
    ax: Any,
    image: np.ndarray,
    anchor_px: tuple[float, float],
    px_per_m: float,
    s_grid: np.ndarray,
    z_grid: np.ndarray,
    pct_grid: np.ndarray,
    tip_height_asl_m: float,
    labels: Sequence[OverlayLabel] = (),
    disclaimer: str | None = None,
    image_note: str = "",
    scale_bar_m: float | None = None,
    alpha: float = 0.6,
) -> tuple[float, float]:
    """Draw the image, the section overlay, labels, scale bar and disclaimer on an axes.

    Args:
        ax: Axes (sized to the image aspect by the caller).
        image: Image array.
        anchor_px: Pixel of the release point ``(x, y)``, y downwards.
        px_per_m: Overlay scale, pixels per metre (both axes).
        s_grid: Section distances, m, 2-D.
        z_grid: Section heights ASL, m, 2-D.
        pct_grid: Percent of the LFL on the section grid.
        tip_height_asl_m: Release height ASL, m (maps to the anchor row).
        labels: Labels with arrows.
        disclaimer: Custom disclaimer (the mandatory phrase is always present).
        image_note: Extra line appended to the disclaimer (for example the image source).
        scale_bar_m: Scale-bar length, m; chosen automatically when ``None``.
        alpha: Opacity of the cloud bands.

    Returns:
        Tuple ``(max_visible_pct_lfl, scale_bar_m)``.

    Raises:
        ValueError: If the anchor lies outside the image or ``px_per_m`` is not positive.
        EmptyViewError: If no cloud reaches the lowest band inside the image.
    """
    h, w = image.shape[0], image.shape[1]
    ax0, ay0 = anchor_px
    if px_per_m <= 0.0:
        raise ValueError("px_per_m must be positive")
    if not (0.0 <= ax0 <= w and 0.0 <= ay0 <= h):
        raise ValueError(f"anchor pixel {anchor_px} lies outside the {w}x{h} image")
    xx = ax0 + s_grid * px_per_m
    yy = ay0 - (z_grid - tip_height_asl_m) * px_per_m
    visible = (xx >= 0) & (xx <= w) & (yy >= 0) & (yy <= h)
    vis_max = float(pct_grid[visible].max()) if visible.any() else 0.0
    if vis_max < st.LFL_LEVELS[0]:
        raise EmptyViewError(
            f"the overlay shows no cloud above {st.LFL_LEVELS[0]:g} % LFL inside the image; check the anchor, "
            "scale and wind case"
        )
    ax.imshow(image, extent=(0, w, h, 0), aspect="auto")
    ax.set_xlim(0, w)
    ax.set_ylim(h, 0)
    st.lfl_contours(ax, xx, yy, pct_grid, alpha=alpha)
    ax.plot(ax0, ay0, marker="*", ms=9, mfc=st.ORANGE, mec="white", mew=0.8, zorder=7)
    for lab in labels:
        tx = ax0 + lab.target_section[0] * px_per_m
        ty = ay0 - (lab.target_section[1] - tip_height_asl_m) * px_per_m
        pos = lab.text_px or (
            min(max(tx + 0.12 * w, 0.1 * w), 0.9 * w),
            min(max(ty + 0.12 * h, 0.1 * h), 0.9 * h),
        )
        ax.annotate(
            lab.text,
            (tx, ty),
            pos,
            color="white",
            fontsize=7,
            ha="center",
            weight="bold",
            arrowprops={"arrowstyle": "-|>", "color": "white", "lw": 1.2},
            bbox={"fc": lab.color, "ec": "white", "alpha": 0.92},
            zorder=8,
        )
    bar = scale_bar_m if scale_bar_m else nice_scale_length_m(px_per_m, w)
    bx0 = 0.97 * w - bar * px_per_m
    by0 = 0.94 * h
    ax.add_patch(
        Rectangle((bx0, by0), bar * px_per_m, 0.008 * h, fc="white", ec="k", zorder=9)
    )
    ax.text(
        bx0 + 0.5 * bar * px_per_m,
        by0 - 0.012 * h,
        f"overlay scale {bar:.0f} m (both axes)",
        ha="center",
        color="white",
        fontsize=6.5,
        weight="bold",
        bbox={"fc": "k", "ec": "none", "alpha": 0.6},
        zorder=9,
    )
    text = ensure_disclaimer(disclaimer)
    if image_note:
        text += "\n" + image_note
    ax.text(
        0.01 * w,
        0.99 * h,
        text,
        color="white",
        fontsize=6,
        ha="left",
        va="bottom",
        bbox={"fc": "k", "ec": "none", "alpha": 0.7},
        zorder=9,
    )
    ax.axis("off")
    return vis_max, bar


def overlay_section_on_image(
    image: str | Path | np.ndarray,
    anchor_px: tuple[float, float],
    px_per_m: float,
    s_grid: np.ndarray,
    z_grid: np.ndarray,
    pct_grid: np.ndarray,
    tip_height_asl_m: float,
    out_path: str | Path,
    labels: Sequence[OverlayLabel] = (),
    title: str = "Plume section overlaid on the image (indicative)",
    sub: str = "Conditional on an unignited release; the image is context only",
    disclaimer: str | None = None,
    image_note: str = "",
    scale_bar_m: float | None = None,
    keep_figure: bool = False,
) -> OverlayResult:
    """Overlay a plume section on an image and save it at report width (7.2 in).

    Args:
        image: Image path or array.
        anchor_px: Pixel of the release point ``(x, y)``, y downwards.
        px_per_m: Overlay scale, pixels per metre (both axes).
        s_grid: Section distances along the wind, m, 2-D.
        z_grid: Section heights ASL, m, 2-D.
        pct_grid: Percent of the LFL on the grid.
        tip_height_asl_m: Release height ASL, m.
        out_path: Output PNG.
        labels: Labels with arrows.
        title: Title stating the finding.
        sub: Sub-line with case and conditions.
        disclaimer: Custom disclaimer; the mandatory phrase is always included.
        image_note: Extra line under the disclaimer (for example the image source).
        scale_bar_m: Scale-bar length, m.
        keep_figure: Return the figure in the result (for inspection in tests).

    Returns:
        The overlay result.

    Raises:
        EmptyViewError: If no cloud is visible in the image.
    """
    with st.house_style():
        img = load_image(image)
        h, w = img.shape[0], img.shape[1]
        top, legend = 0.85, 0.4
        img_h = st.W_FULL * h / w
        fig = st.new_fig(top + img_h + legend, constrained=False)
        ax = fig.add_axes(
            [
                0.0,
                legend / fig.get_size_inches()[1],
                1.0,
                img_h / fig.get_size_inches()[1],
            ]
        )
        vis, bar = draw_overlay(
            ax,
            img,
            anchor_px,
            px_per_m,
            s_grid,
            z_grid,
            pct_grid,
            tip_height_asl_m,
            labels,
            disclaimer,
            image_note,
            scale_bar_m,
        )
        st.lfl_legend(fig)
        st.headline(fig, title, sub)
        paths, problems = st.save(fig, str(Path(out_path).parent), Path(out_path).name)
    return OverlayResult(
        paths[0],
        ensure_disclaimer(disclaimer),
        anchor_px,
        px_per_m,
        vis,
        bar,
        problems,
        fig if keep_figure else None,
    )


def compose_overlay_figure(
    study: StudyResult,
    case: str,
    wind_from: float,
    speed: float,
    image: str | Path | np.ndarray,
    anchor_px: tuple[float, float],
    px_per_m: float,
    out_path: str | Path,
    labels: Sequence[OverlayLabel] | None = None,
    disclaimer: str | None = None,
    image_note: str = "",
    mode: str = "briggs",
    keep_figure: bool = False,
) -> OverlayResult:
    """Page-width composite: image with overlay above to-scale section and plan panels.

    The panels use explicit axes placement because fixed-aspect panels break a
    constrained layout. The section panel states its vertical exaggeration.

    Args:
        study: Study result.
        case: Case name.
        wind_from: Wind direction (FROM), degrees true.
        speed: Wind speed, m/s.
        image: Image path or array.
        anchor_px: Pixel of the release point.
        px_per_m: Overlay scale, pixels per metre.
        out_path: Output PNG.
        labels: Overlay labels; default a helideck label and a release label.
        disclaimer: Custom disclaimer; the mandatory phrase is always included.
        image_note: Extra line under the disclaimer.
        mode: Plume mode.
        keep_figure: Return the figure in the result.

    Returns:
        The overlay result.

    Raises:
        EmptyViewError: If no cloud is visible in the image.
    """
    rec, geo = study.receptors, study.geometry
    release = study.releases[case]
    stab = pasquill_by_speed(speed, study.settings.stability_scheme)
    travel = math.radians(wind_from + 180.0)
    zmax = section_zmax(rec)
    s_max = round(0.97 * geo.flight_paths.length_m / 100.0) * 100.0
    s_grid, z_grid, f = section_field(
        release,
        wind_from,
        speed,
        stab,
        rec,
        (-50.0, s_max),
        (2.0, zmax),
        ds=10.0,
        dz=2.0,
        mode=mode,
    )
    dd = float(rec.deck[0] * math.sin(travel) + rec.deck[1] * math.cos(travel))
    if labels is None:
        labels = []
        if dd > 0:
            labels.append(
                OverlayLabel(
                    f"Helideck position (schematic; not in the image)\n{dd:.0f} m from tip, {geo.tip_height_asl_m - geo.helideck_height_asl_m:.0f} m lower",
                    (dd, float(rec.deck[2])),
                    None,
                    st.NAVY,
                )
            )
    with st.house_style():
        img = load_image(image)
        ih, iw = img.shape[0], img.shape[1]
        extent = st.plan_extent(rec)
        sec_w, plan_w = 3.0, 2.6
        sec_h = st.VERTICAL_EXAGGERATION * (zmax) / (s_max + 100.0) * sec_w
        plan_h = plan_w * (extent[1][1] - extent[1][0]) / (extent[0][1] - extent[0][0])
        top, legend, gap, label_zone = 1.15, 0.4, 0.3, 0.6
        echo_h = st.W_FULL * ih / iw
        panel_h = max(sec_h, plan_h) + label_zone
        total = top + echo_h + gap + panel_h + legend
        fig = st.new_fig(total, constrained=False)
        fig.set_size_inches(st.W_FULL, total)

        def frac(
            left: float, bottom: float, width: float, height: float
        ) -> list[float]:
            return [left / st.W_FULL, bottom / total, width / st.W_FULL, height / total]

        ax = fig.add_axes(frac(0.0, total - top - echo_h, st.W_FULL, echo_h))
        vis, bar = draw_overlay(
            ax,
            img,
            anchor_px,
            px_per_m,
            s_grid,
            z_grid,
            f,
            geo.tip_height_asl_m,
            labels,
            disclaimer,
            image_note,
        )
        ax.set_title(
            "Image with schematic overlay", loc="left", fontsize=8, fontweight="bold"
        )
        base = legend + label_zone
        bx = fig.add_axes(frac(0.62, base + max(plan_h - sec_h, 0.0), sec_w, sec_h))
        st.lfl_contours(bx, s_grid, z_grid, f)
        bx.axhline(0, color=st.SEA, lw=1.4)
        bx.plot([0, 0], [0, geo.tip_height_asl_m], color="#444", lw=2.5)
        bx.plot(
            0, geo.tip_height_asl_m, marker="*", ms=9, mfc=st.ORANGE, mec="k", mew=0.5
        )
        if dd > 0:
            bx.plot(
                dd,
                rec.deck[2],
                marker="H",
                ms=6,
                mfc=st.BLUE,
                mec="k",
                mew=0.5,
                zorder=5,
            )
        pb = (wind_from + 180.0) % 360.0
        if rec.in_obstacle_free_sector(pb):
            path = rec.path_points(pb)
            sp = path[:, 0] * math.sin(travel) + path[:, 1] * math.cos(travel)
            bx.plot(
                sp,
                path[:, 2],
                color=st.GREEN,
                lw=1.4,
                label=f"flight path {pb:03.0f} deg T",
            )
            bx.legend(loc="upper right", frameon=False, fontsize=6.3)
        bx.set_xlim(-100, s_max)
        bx.set_ylim(0, zmax)
        bx.set_aspect(st.VERTICAL_EXAGGERATION, adjustable="box")
        bx.set_xlabel("Distance downwind of tip (m)")
        bx.set_ylabel("Height ASL (m)")
        bx.set_title(
            f"To scale: vertical section (scale x{st.VERTICAL_EXAGGERATION:g})",
            loc="left",
        )
        cx = fig.add_axes(frac(st.W_FULL - plan_w - 0.1, base, plan_w, plan_h))
        gx, gy, pf = plan_field(release, wind_from, speed, stab, rec, extent, mode=mode)
        st.lfl_contours(cx, gx, gy, pf)
        st.plan_base(cx, rec, extent)
        st.wind_box(
            cx, wind_from, speed, f"Wind from {wind_from:03.0f} deg\n{speed:.1f} m/s"
        )
        cx.set_xlabel("East of tip (km)")
        cx.set_ylabel("North of tip (km)")
        cx.set_title("To scale: plan view", loc="left")
        st.lfl_legend(fig)
        st.headline(
            fig,
            "Image context and dispersion at the flare tip: the section shows where the cloud passes relative to the helideck",
            f"Screening result for {case} ({release.mdot:.0f} kg/s), wind from {wind_from:03.0f} deg at {speed:.1f} m/s; conditional on an unignited release; image is context only",
        )
        paths, problems = st.save(fig, str(Path(out_path).parent), Path(out_path).name)
    return OverlayResult(
        paths[0],
        ensure_disclaimer(disclaimer),
        anchor_px,
        px_per_m,
        vis,
        bar,
        problems,
        fig if keep_figure else None,
    )
