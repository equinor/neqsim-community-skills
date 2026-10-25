"""Concept screening figures drawn only from a ``run_screening`` result (educational).

Every number on a figure is read from the screening result, so a figure can be
regenerated and traced. Requires ``matplotlib`` (install the ``figures`` extra).

Figures:

* ``plot_funnel`` - long list to short list, count per elimination stage.
* ``plot_decision_matrix`` - normalised score heatmap, short list highlighted.
* ``plot_pareto`` - two-criterion projection with the non-dominated set marked.
* ``plot_robustness`` - probability of ranking first and within the top k.
* ``plot_crossovers`` - base weight against the weight where the leader changes.
* ``plot_concept_schematic`` - block schematic of one concept (wells, host,
  export routes, power), not georeferenced; for maps use a layout or map tool.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

ROLE_ORDER = ("host", "wells", "oil_export", "gas_disposal", "drive", "power")
SHORT_LIST_COLOUR = "#1f6f8b"
OTHER_COLOUR = "#9aa5ab"


def _plt():
    """Import pyplot with a non-interactive backend.

    Returns:
        The ``matplotlib.pyplot`` module.

    Raises:
        ImportError: when matplotlib is not installed.
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ImportError(
            "concept figures need matplotlib: pip install matplotlib "
            "(or the 'figures' extra of this skill)"
        ) from exc
    return plt


def short_label(concept: str, max_len: int = 38) -> str:
    """Return a readable label for a ``|``-joined concept id.

    Args:
        concept: concept id.
        max_len: maximum label length before truncation.

    Returns:
        Label with ``/`` separators and underscores as spaces.
    """
    text = " / ".join(p.replace("_", " ") for p in str(concept).split("|"))
    return text if len(text) <= max_len else text[: max_len - 1] + "\u2026"


def _short_ids(result: Mapping[str, Any]) -> list[str]:
    """Return the short-listed concept ids of a screening result.

    Args:
        result: ``run_screening`` result.

    Returns:
        Concept ids in short-list order.
    """
    return [s["concept"] for s in result.get("short_list", [])]


def _finish(fig, path: str | Path | None, dpi: int):
    """Lay out and optionally save a figure.

    Args:
        fig: matplotlib figure.
        path: output path or None.
        dpi: resolution for raster output.

    Returns:
        The figure.
    """
    fig.tight_layout()
    if path is not None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(path, dpi=dpi)
    return fig


def funnel_counts(result: Mapping[str, Any]) -> list[tuple[str, int]]:
    """Count the concepts left after each screening stage.

    Args:
        result: ``run_screening`` result.

    Returns:
        ``(stage label, count)`` from all combinations down to the short list.
    """
    n_all = int(result.get("n_combinations", 0))
    n_long = len(result.get("long_list", []))
    n_must = sum(
        1 for e in result.get("elimination_log", []) if e.get("stage") == "must_pass"
    )
    n_ranked = len(result.get("ranking", [])) or (n_long - n_must)
    return [
        ("Combinations", n_all),
        ("Long list (after rules)", n_long),
        ("After must-pass", n_ranked),
        ("Short list", len(result.get("short_list", []))),
    ]


def plot_funnel(result, path=None, dpi: int = 150):
    """Plot the long-list to short-list funnel.

    Args:
        result: ``run_screening`` result.
        path: optional output file.
        dpi: raster resolution.

    Returns:
        The matplotlib figure.
    """
    plt = _plt()
    stages = funnel_counts(result)
    fig, ax = plt.subplots(figsize=(8, 4))
    labels = [s[0] for s in stages][::-1]
    counts = [s[1] for s in stages][::-1]
    top = max(counts) or 1
    colours = [SHORT_LIST_COLOUR] + [OTHER_COLOUR] * (len(counts) - 1)
    ax.barh(labels, counts, color=colours, label="Concepts remaining")
    for y, c in enumerate(counts):
        ax.text(c + top * 0.01, y, str(c), va="center", fontsize=9)
    n_var = len(result.get("capacity_variants", []))
    title = "Concept screening funnel"
    if n_var:
        title += f" ({n_var} capacity-variant group(s), "
        title += f"{result.get('n_distinct_topologies')} distinct topologies)"
    ax.set_title(title)
    ax.set_xlabel("Number of concepts [-]")
    ax.set_xlim(0, top * 1.12)
    ax.grid(axis="x", alpha=0.3)
    ax.legend(loc="lower right", fontsize=8)
    return _finish(fig, path, dpi)


def plot_decision_matrix(result, path=None, dpi: int = 150):
    """Plot the normalised decision matrix as a heatmap (1 is best).

    Args:
        result: ``run_screening`` result.
        path: optional output file.
        dpi: raster resolution.

    Returns:
        The matplotlib figure.

    Raises:
        ValueError: when the result has no decision matrix.
    """
    plt = _plt()
    matrix = result.get("decision_matrix") or {}
    if not matrix:
        raise ValueError("result has no decision_matrix (no weighted criteria)")
    order = [r["concept"] for r in result.get("ranking", [])] or list(matrix)
    crits = list(next(iter(matrix.values())))
    data = [[matrix[c][k] for k in crits] for c in order]
    chosen = set(_short_ids(result))
    fig, ax = plt.subplots(figsize=(1.3 * len(crits) + 4, 0.38 * len(order) + 1.8))
    im = ax.imshow(data, cmap="viridis", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(crits)), [k.replace("_", " ") for k in crits], rotation=30)
    ax.set_yticks(
        range(len(order)),
        [("\u25b6 " if c in chosen else "") + short_label(c) for c in order],
        fontsize=8,
    )
    for i, row in enumerate(data):
        for j, v in enumerate(row):
            ax.text(
                j,
                i,
                f"{v:.2f}",
                ha="center",
                va="center",
                fontsize=7,
                color="white" if v < 0.55 else "black",
            )
    fig.colorbar(im, ax=ax, label="Normalised score [-] (1 = best)")
    ax.set_title("Decision matrix, ranked best first (\u25b6 = short list)")
    return _finish(fig, path, dpi)


def plot_pareto(result, x: str, y: str, path=None, dpi: int = 150):
    """Plot two normalised criteria and mark the non-dominated concepts.

    The Pareto front in the result is computed on all criteria, so a marked
    concept can look dominated in a two-criterion projection.

    Args:
        result: ``run_screening`` result.
        x: criterion id on the x axis.
        y: criterion id on the y axis.
        path: optional output file.
        dpi: raster resolution.

    Returns:
        The matplotlib figure.

    Raises:
        ValueError: when a criterion is not in the decision matrix.
    """
    plt = _plt()
    matrix = result.get("decision_matrix") or {}
    for key in (x, y):
        if not matrix or key not in next(iter(matrix.values())):
            raise ValueError(f"criterion '{key}' is not in the decision matrix")
    front = set(result.get("pareto_front", []))
    chosen = set(_short_ids(result))
    fig, ax = plt.subplots(figsize=(7, 5.5))
    for group, colour, label in (
        ([c for c in matrix if c not in front], OTHER_COLOUR, "Dominated"),
        (
            [c for c in matrix if c in front],
            SHORT_LIST_COLOUR,
            "Pareto front (all criteria)",
        ),
    ):
        if group:
            ax.scatter(
                [matrix[c][x] for c in group],
                [matrix[c][y] for c in group],
                c=colour,
                s=50,
                label=label,
            )
    for c in chosen & set(matrix):
        ax.scatter(
            matrix[c][x], matrix[c][y], s=160, facecolors="none", edgecolors="red"
        )
        ax.annotate(
            short_label(c, 28),
            (matrix[c][x], matrix[c][y]),
            fontsize=7,
            xytext=(5, 5),
            textcoords="offset points",
        )
    ax.scatter([], [], s=160, facecolors="none", edgecolors="red", label="Short list")
    ax.set_xlabel(f"{x.replace('_', ' ')} [-] (normalised, 1 = best)")
    ax.set_ylabel(f"{y.replace('_', ' ')} [-] (normalised, 1 = best)")
    ax.set_xlim(-0.05, 1.08)
    ax.set_ylim(-0.05, 1.08)
    ax.set_title("Concept trade-off")
    ax.grid(alpha=0.3)
    ax.legend(loc="lower left", fontsize=8)
    return _finish(fig, path, dpi)


def plot_robustness(result, path=None, dpi: int = 150):
    """Plot rank acceptability under sampled weights.

    Args:
        result: ``run_screening`` result.
        path: optional output file.
        dpi: raster resolution.

    Returns:
        The matplotlib figure.

    Raises:
        ValueError: when the result has no robustness block.
    """
    plt = _plt()
    rob = result.get("robustness") or {}
    if not rob:
        raise ValueError("result has no robustness block")
    order = [r["concept"] for r in result.get("ranking", [])] or list(rob["p_top_k"])
    k = rob["top_k"]
    fig, ax = plt.subplots(figsize=(8, 0.35 * len(order) + 1.8))
    ys = range(len(order))
    ax.barh(
        [i + 0.2 for i in ys],
        [rob["p_top_k"][c] for c in order],
        height=0.4,
        color=OTHER_COLOUR,
        label=f"P(top {k})",
    )
    ax.barh(
        [i - 0.2 for i in ys],
        [rob["p_first"][c] for c in order],
        height=0.4,
        color=SHORT_LIST_COLOUR,
        label="P(rank 1)",
    )
    ax.set_yticks(list(ys), [short_label(c) for c in order], fontsize=8)
    ax.invert_yaxis()
    ax.set_xlim(0, 1)
    ax.set_xlabel("Probability over weight samples [-]")
    ax.set_title(
        f"Rank acceptability, {rob['n_samples']} Dirichlet weight samples "
        f"(concentration {rob['concentration']:g})"
    )
    ax.grid(axis="x", alpha=0.3)
    ax.legend(loc="lower right", fontsize=8)
    return _finish(fig, path, dpi)


def plot_crossovers(result, path=None, dpi: int = 150):
    """Plot each criterion's base weight and the weight where the leader changes.

    Args:
        result: ``run_screening`` result.
        path: optional output file.
        dpi: raster resolution.

    Returns:
        The matplotlib figure.

    Raises:
        ValueError: when the result has no crossovers.
    """
    plt = _plt()
    rows = result.get("crossovers") or []
    if not rows:
        raise ValueError("result has no crossovers")
    fig, ax = plt.subplots(figsize=(8, 0.5 * len(rows) + 1.8))
    for i, r in enumerate(rows):
        ax.plot([0, 1], [i, i], color="#dddddd", lw=1)
        ax.scatter(
            r["base_weight"],
            i,
            color=SHORT_LIST_COLOUR,
            s=50,
            label="Base weight" if i == 0 else None,
            zorder=3,
        )
        if r["crossover_weight"] is not None:
            ax.annotate(
                "",
                xy=(r["crossover_weight"], i),
                xytext=(r["base_weight"], i),
                arrowprops={"arrowstyle": "->", "color": "red"},
            )
            ax.text(
                r["crossover_weight"],
                i + 0.18,
                f"{r['crossover_weight']:.2f} \u2192 {short_label(r['new_leader'], 26)}",
                fontsize=7,
                ha="center",
            )
        else:
            ax.text(1.0, i + 0.18, "leader never changes", fontsize=7, ha="right")
    ax.scatter([], [], marker=r"$\rightarrow$", color="red", label="Crossover weight")
    ax.set_yticks(range(len(rows)), [r["criterion"].replace("_", " ") for r in rows])
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.6, len(rows) - 0.3)
    ax.set_xlabel("Criterion weight [-] (others keep their proportions)")
    ax.set_title("Weight at which the leading concept changes")
    ax.grid(axis="x", alpha=0.3)
    ax.legend(loc="lower right", fontsize=8)
    return _finish(fig, path, dpi)


def _box(ax, xy, text, colour):
    """Draw a labelled rounded box.

    Args:
        ax: matplotlib axes.
        xy: box centre ``(x, y)``.
        text: label.
        colour: face colour.
    """
    from matplotlib.patches import FancyBboxPatch

    w, h = 2.2, 0.8
    ax.add_patch(
        FancyBboxPatch(
            (xy[0] - w / 2, xy[1] - h / 2),
            w,
            h,
            boxstyle="round,pad=0.05",
            fc=colour,
            ec="#333333",
        )
    )
    ax.text(xy[0], xy[1], text, ha="center", va="center", fontsize=8, wrap=True)


def _arrow(ax, a, b, text="", style="-|>"):
    """Draw an arrow between two points with an optional label.

    Args:
        ax: matplotlib axes.
        a: start ``(x, y)``.
        b: end ``(x, y)``.
        text: label at the midpoint.
        style: arrow style.
    """
    ax.annotate(
        "", xy=b, xytext=a, arrowprops={"arrowstyle": style, "color": "#333333"}
    )
    if text:
        ax.text(
            (a[0] + b[0]) / 2,
            (a[1] + b[1]) / 2 + 0.15,
            text,
            ha="center",
            fontsize=7,
            color="#333333",
        )


def plot_concept_schematic(
    concept: str | Mapping[str, str],
    elements: Sequence[str] = ROLE_ORDER,
    key_facts: Sequence[tuple[str, str]] = (),
    path=None,
    dpi: int = 150,
):
    """Draw a block schematic of one concept from its element choices.

    Args:
        concept: ``|``-joined concept id or a ``{element: option}`` mapping.
        elements: element order used to build the id.
        key_facts: ``(label, value with unit)`` read from results, printed in a
            side panel; never invent numbers here.
        path: optional output file.
        dpi: raster resolution.

    Returns:
        The matplotlib figure.

    Raises:
        ValueError: when the id does not match the element order.
    """
    plt = _plt()
    if isinstance(concept, str):
        parts = concept.split("|")
        if len(parts) != len(elements):
            raise ValueError(
                f"concept id has {len(parts)} parts, expected {len(elements)} elements"
            )
        choices = dict(zip(elements, parts))
    else:
        choices = dict(concept)
    lab = {k: str(v).replace("_", " ") for k, v in choices.items()}
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.set_xlim(0, 13 if key_facts else 10)
    ax.set_ylim(0, 6)
    ax.axis("off")
    res, host, oil, gas, pwr = (1.4, 1.2), (5, 3), (8.6, 4.6), (8.6, 3.0), (5, 5.3)
    _box(
        ax,
        res,
        f"Reservoir\n{lab.get('wells', 'wells')} wells\n{lab.get('drive', '')}",
        "#e9d8a6",
    )
    _box(ax, host, f"Host\n{lab.get('host', '?')}", "#94d2bd")
    _arrow(
        ax, (res[0] + 0.6, res[1] + 0.4), (host[0] - 1.1, host[1] - 0.3), "production"
    )
    if "oil_export" in choices:
        _box(ax, oil, f"Oil export\n{lab['oil_export']}", "#ee9b00")
        _arrow(ax, (host[0] + 1.1, host[1] + 0.2), (oil[0] - 1.1, oil[1]))
    if "gas_disposal" in choices:
        _box(ax, gas, f"Gas\n{lab['gas_disposal']}", "#ca6702")
        _arrow(ax, (host[0] + 1.1, host[1]), (gas[0] - 1.1, gas[1]))
        if choices["gas_disposal"] == "reinjection":
            _arrow(ax, (gas[0], gas[1] - 0.4), (res[0] + 1.1, res[1]), "reinjection")
    if "power" in choices:
        _box(ax, pwr, f"Power\n{lab['power']}", "#bde0fe")
        _arrow(ax, (pwr[0], pwr[1] - 0.4), (host[0], host[1] + 0.4), style="-|>")
    if key_facts:
        ax.text(10.4, 5.5, "Key facts (from results)", fontsize=9, weight="bold")
        for i, (k, v) in enumerate(key_facts):
            ax.text(10.4, 5.0 - 0.45 * i, f"{k}: {v}", fontsize=8)
    ax.set_title(
        f"Concept schematic: {short_label(concept if isinstance(concept, str) else '|'.join(choices.values()), 140)}",
        fontsize=8,
    )
    return _finish(fig, path, dpi)


def render_screening_figures(
    result: Mapping[str, Any],
    out_dir: str | Path,
    elements: Sequence[str] = ROLE_ORDER,
    pareto_axes: tuple[str, str] | None = None,
    key_facts: Mapping[str, Sequence[tuple[str, str]]] | None = None,
    dpi: int = 150,
) -> list[dict[str, Any]]:
    """Render the standard figure set and return ``results.json`` figure entries.

    Args:
        result: ``run_screening`` result.
        out_dir: folder for the PNG files.
        elements: element order of the concept ids (for schematics).
        pareto_axes: two criterion ids for the trade-off plot (default: the first
            two criteria of the decision matrix).
        key_facts: optional ``{concept_id: [(label, value)]}`` for schematics.
        dpi: raster resolution.

    Returns:
        Figure entries ``{id, path, caption, linked_results}``.
    """
    plt = _plt()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []

    def add(fig_id, fig, caption, linked):
        path = out / f"{fig_id}.png"
        fig.savefig(path, dpi=dpi)
        plt.close(fig)
        entries.append(
            {
                "id": fig_id,
                "path": str(path),
                "caption": caption,
                "linked_results": linked,
            }
        )

    counts = funnel_counts(result)
    add(
        "fig_concept_funnel",
        plot_funnel(result),
        "Concept funnel: " + ", ".join(f"{s} {c}" for s, c in counts) + ".",
        ["n_combinations", "long_list", "elimination_log", "short_list"],
    )
    if result.get("decision_matrix"):
        add(
            "fig_decision_matrix",
            plot_decision_matrix(result),
            "Normalised decision matrix of the ranked concepts (1 = best); "
            "the short list is marked.",
            ["decision_matrix", "ranking", "short_list"],
        )
        crits = list(next(iter(result["decision_matrix"].values())))
        axes = pareto_axes or (tuple(crits[:2]) if len(crits) >= 2 else None)
        if axes:
            add(
                "fig_pareto",
                plot_pareto(result, *axes),
                f"Trade-off between {axes[0]} and {axes[1]}; Pareto front on all criteria.",
                ["pareto_front", "decision_matrix"],
            )
    if result.get("robustness"):
        add(
            "fig_rank_acceptability",
            plot_robustness(result),
            "Probability of ranking first and within the short-list size under "
            "sampled criterion weights.",
            ["robustness"],
        )
    if result.get("crossovers"):
        add(
            "fig_weight_crossovers",
            plot_crossovers(result),
            "Base criterion weights and the weight at which the leading concept changes.",
            ["crossovers"],
        )
    for i, cid in enumerate(_short_ids(result), 1):
        try:
            fig = plot_concept_schematic(cid, elements, (key_facts or {}).get(cid, ()))
        except ValueError:
            continue
        add(
            f"fig_concept_schematic_{i}",
            fig,
            f"Block schematic of short-listed concept {i}: {short_label(cid, 90)}.",
            ["short_list"],
        )
    return entries
