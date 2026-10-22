"""SVG renderer for conceptual P&ID sketches (ISA-style symbols, simplified)."""

from __future__ import annotations

from typing import List
from xml.sax.saxutils import escape

from .elements import Element, TieInEndSketch

PITCH = 120
X0 = 90
Y_LINE = 230
INK = "#1b2a3a"
NEW = "#1e8449"
WARN = "#c0392b"


def _txt(x: float, y: float, s: str, size: int = 11, anchor: str = "middle", weight: str = "normal", fill: str = INK) -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="Arial, Helvetica, sans-serif" font-size="{size}" '
            f'text-anchor="{anchor}" font-weight="{weight}" fill="{fill}">{escape(s)}</text>')


def _symbol(el: Element, x: float, y: float) -> List[str]:
    sw = 1.6 if el.existing else 2.8
    col = INK if el.existing else NEW
    base = f'stroke="{col}" stroke-width="{sw}" fill="white"'
    out: List[str] = []
    k = el.kind
    if k in ("gate_valve", "ball_valve", "esdv", "check_valve", "control_valve", "psv"):
        out.append(f'<path d="M{x-14},{y-10} L{x+14},{y+10} L{x+14},{y-10} L{x-14},{y+10} Z" {base}/>')
        if k == "ball_valve":
            out.append(f'<circle cx="{x}" cy="{y}" r="3.5" fill="{col}"/>')
        if k == "esdv":
            out.append(f'<line x1="{x}" y1="{y}" x2="{x}" y2="{y-26}" stroke="{col}" stroke-width="{sw}"/>')
            out.append(f'<rect x="{x-9}" y="{y-40}" width="18" height="14" {base}/>')
            out.append(_txt(x, y - 29, "S", 10, weight="bold"))
        if k == "control_valve":
            out.append(f'<line x1="{x}" y1="{y}" x2="{x}" y2="{y-22}" stroke="{col}" stroke-width="{sw}"/>')
            out.append(f'<path d="M{x-12},{y-22} A12,12 0 0 1 {x+12},{y-22} Z" {base}/>')
        if k == "check_valve":
            out.append(f'<path d="M{x-5},{y-5} L{x+6},{y} L{x-5},{y+5} Z" fill="{col}"/>')
        if k == "psv":
            out.append(f'<line x1="{x}" y1="{y}" x2="{x}" y2="{y-30}" stroke="{col}" stroke-width="{sw}"/>')
    elif k == "pump":
        out.append(f'<circle cx="{x}" cy="{y}" r="22" {base}/>')
        out.append(f'<path d="M{x-14},{y+14} L{x},{y-22} L{x+14},{y+14}" fill="none" stroke="{col}" stroke-width="{sw}"/>')
    elif k in ("pig_launcher", "pig_receiver"):
        w = 96
        out.append(f'<rect x="{x-w/2}" y="{y-14}" width="{w}" height="28" rx="12" {base}/>')
        out.append(f'<path d="M{x+w/2-4},{y-14} L{x+w/2+16},{y-24} L{x+w/2+16},{y+24} L{x+w/2-4},{y+14}" {base}/>'
                   if k == "pig_launcher" else
                   f'<path d="M{x-w/2+4},{y-14} L{x-w/2-16},{y-24} L{x-w/2-16},{y+24} L{x-w/2+4},{y+14}" {base}/>')
        out.append(f'<circle cx="{x-14 if k == "pig_launcher" else x+14}" cy="{y}" r="6" fill="{col}"/>')
    elif k == "spec_break":
        out.append(f'<line x1="{x-6}" y1="{y-20}" x2="{x-6}" y2="{y+20}" stroke="{col}" stroke-width="{sw+0.8}"/>')
        out.append(f'<line x1="{x+6}" y1="{y-20}" x2="{x+6}" y2="{y+20}" stroke="{col}" stroke-width="{sw+0.8}"/>')
        out.append(f'<circle cx="{x}" cy="{y-10}" r="5" {base}/>')
    elif k in ("transmitter", "flow_meter", "sampler"):
        letter = {"flow_meter": "F", "sampler": "A"}.get(k, el.measure)
        out.append(f'<line x1="{x}" y1="{y}" x2="{x}" y2="{y-34}" stroke="{col}" stroke-width="1.2"/>')
        out.append(f'<circle cx="{x}" cy="{y-48}" r="14" {base}/>')
        out.append(_txt(x, y - 44, letter + "T" if k != "sampler" else "AS", 10, weight="bold"))
        if k == "flow_meter":
            out.append(f'<rect x="{x-14}" y="{y-8}" width="28" height="16" {base}/>')
    elif k == "tie_in":
        out.append(f'<circle cx="{x}" cy="{y}" r="13" fill="{WARN}" stroke="{INK}" stroke-width="1.5"/>')
        out.append(_txt(x, y + 4, "TI", 11, weight="bold", fill="white"))
    elif k == "riser":
        out.append(f'<path d="M{x},{y-70} L{x},{y-14} Q{x},{y} {x+14},{y}" fill="none" stroke="{col}" stroke-width="{sw+1.5}"/>')
        out.append(_txt(x + 8, y - 74, "stigerør til dekk", 10, "start", fill="#555"))
    elif k in ("equipment", "note_box"):
        dash = ' stroke-dasharray="6 3"' if k == "note_box" else ""
        out.append(f'<rect x="{x-48}" y="{y-34}" width="96" height="68" rx="6" {base}{dash}/>')
    return out


def render_svg(sketch: TieInEndSketch) -> str:
    """Render a sketch to an SVG document string.

    Existing plant is drawn thin and dark; new scope is drawn bold and green. Tags that were invented for the
    sketch carry a trailing asterisk and the footer says so.
    """
    n = len(sketch.elements)
    width = X0 * 2 + PITCH * max(n - 1, 1) + 120
    height = 470
    out: List[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="white"/>',
        _txt(24, 30, sketch.title, 18, "start", "bold"),
        _txt(24, 50, sketch.subtitle, 12, "start", fill="#555"),
    ]
    xs = [X0 + i * PITCH for i in range(n)]
    out.append(f'<line x1="{xs[0]-60}" y1="{Y_LINE}" x2="{xs[-1]+60}" y2="{Y_LINE}" stroke="{INK}" stroke-width="2.4"/>')
    arrow_x = xs[-1] + 60 if sketch.side == "source" else xs[0] - 60
    out.append(_txt(arrow_x, Y_LINE - 30, sketch.line_label, 11, "end" if sketch.side == "source" else "start",
                    "bold", NEW))
    for el, x in zip(sketch.elements, xs):
        out.extend(_symbol(el, x, Y_LINE))
        tag = el.tag + ("*" if el.proposed and el.tag else "")
        top = Y_LINE + 52 if el.kind not in ("equipment", "note_box") else Y_LINE + 52
        out.append(_txt(x, top, tag, 11, weight="bold", fill=INK if el.existing else NEW))
        for j, part in enumerate(el.label.split("\n")):
            out.append(_txt(x, top + 15 + 13 * j, part, 10, fill="#444"))
    ys = Y_LINE + 130
    out.append(f'<line x1="24" y1="{ys-14}" x2="{width-24}" y2="{ys-14}" stroke="#bbb"/>')
    out.append(_txt(24, ys, "Alternativer / valg", 12, "start", "bold"))
    for i, opt in enumerate(sketch.options):
        out.append(_txt(34, ys + 18 + 15 * i, f"{i + 1}. {opt}", 10.5, "start"))
    ny = ys + 18 + 15 * max(len(sketch.options), 1) + 14
    for i, note in enumerate(sketch.notes):
        out.append(_txt(24, ny + 14 * i, "• " + note, 10, "start", fill="#555"))
    out.append(f'<line x1="24" y1="68" x2="40" y2="68" stroke="{INK}" stroke-width="1.6"/>')
    out.append(_txt(46, 72, "eksisterende", 10, "start"))
    out.append(f'<line x1="130" y1="68" x2="146" y2="68" stroke="{NEW}" stroke-width="2.8"/>')
    out.append(_txt(152, 72, "nytt omfang", 10, "start"))
    out.append(_txt(width - 24, height - 12,
                    "Konseptuell skisse – * foreslått tag, ikke tag fra kontrollert P&ID. Ikke for bygging.", 10, "end", fill="#777"))
    out.append("</svg>")
    return "\n".join(out)
