"""Illustration source register: every drawn element must be traceable to a real source and, where it shows a calculated value, bound to NeqSim.

An element record is a dict:

``element``        id shown in the figure (tag or name)
``figures``        list of figure file names where it is drawn
``kind``           equipment, line, valve, instrument, structure, dimension, value
``status``         ``SOURCED`` (P&ID, datasheet, line list, drawing, trajectory), ``DERIVED`` (from a task results.json / model file) or ``ASSUMED``
``source``         dict(type, file, doc_no, revision, page, note) - required for SOURCED and DERIVED
``reason``         why it is assumed (required for ASSUMED) and what would replace it
``neqsim_binding`` optional dict(unit, address, value, tolerance_rel, results_key) linking a shown number to a NeqSim result;
                   ``unit`` is the NeqSim equipment or stream name (or ``lumped:<node>`` for the task's lumped model), ``address`` the property
                   address (for example ``pv.outletPressure`` or ``results.key_results[...]``).

:func:`check_register` returns findings; ERROR findings (missing source, ASSUMED without reason, ASSUMED not declared in the figure
legend/footnote, stale bound value) make :func:`register_status` return ``FAIL``. Pass ``fresh`` (callable ``binding -> float``) to compare each
bound value with a fresh model run.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Sequence
from typing import Any

STATUSES = ("SOURCED", "DERIVED", "ASSUMED")
SOURCE_KEYS = ("type", "file")
LEGEND_TEXT_NO = "antatt/skjematisk"


def element(name: str, kind: str, status: str, figures: Sequence[str] = (), source: dict | None = None, reason: str | None = None,
            neqsim_binding: dict | None = None, **extra: Any) -> dict[str, Any]:
    """Build one register record."""
    rec: dict[str, Any] = {"element": name, "kind": kind, "status": status, "figures": list(figures)}
    if source:
        rec["source"] = source
    if reason:
        rec["reason"] = reason
    if neqsim_binding:
        rec["neqsim_binding"] = neqsim_binding
    rec.update(extra)
    return rec


def check_register(register: Iterable[dict], fresh: Callable[[dict], float] | None = None, legend_texts: dict[str, str] | None = None) -> list[dict]:
    """Return findings ``{severity, code, element, message}``.

    Codes: NO_STATUS, NO_SOURCE, NO_REASON, ASSUMED_NOT_LABELLED, NO_FIGURE, BAD_BINDING, STALE_VALUE, FRESH_FAILED. neqsim_binding is optional: only elements that carry one are checked against a fresh run.
    ``legend_texts`` maps figure name -> legend/footnote text; every figure showing an ASSUMED element must contain 'antatt' or 'skjematisk' in it.
    """
    out: list[dict] = []

    def add(sev: str, code: str, el: dict, msg: str) -> None:
        out.append({"severity": sev, "code": code, "element": el.get("element", "?"), "message": msg})

    for el in register:
        st = el.get("status")
        if st not in STATUSES:
            add("ERROR", "NO_STATUS", el, "status must be one of %s" % (STATUSES,))
            continue
        if not el.get("figures"):
            add("WARN", "NO_FIGURE", el, "element is not linked to a figure")
        src = el.get("source") or {}
        if st in ("SOURCED", "DERIVED"):
            if not all(src.get(k) for k in SOURCE_KEYS):
                add("ERROR", "NO_SOURCE", el, "%s element needs source.type and source.file (document number, revision and page where they exist)" % st)
            elif st == "SOURCED" and not (src.get("doc_no") or src.get("page")):
                add("WARN", "NO_SOURCE", el, "SOURCED element should give doc_no and page")
        else:
            if not el.get("reason"):
                add("ERROR", "NO_REASON", el, "ASSUMED element needs a reason and the data that would replace it")
            if legend_texts is not None:
                for fig in el.get("figures", []):
                    txt = (legend_texts.get(fig) or "").lower()
                    if "antatt" not in txt and "skjematisk" not in txt and "assumed" not in txt:
                        add("ERROR", "ASSUMED_NOT_LABELLED", el, "figure %s shows an ASSUMED element but its legend/footnote does not say antatt/skjematisk" % fig)
        b = el.get("neqsim_binding")
        if b:
            if not b.get("unit") or not b.get("address") or b.get("value") is None:
                add("ERROR", "BAD_BINDING", el, "neqsim_binding needs unit, address and value")
                continue
            if fresh is not None:
                try:
                    new = float(fresh(b))
                except Exception as exc:  # noqa: BLE001 - report any failure of the model run
                    add("ERROR", "FRESH_FAILED", el, "fresh model run failed for %s: %s" % (b.get("address"), exc))
                    continue
                old = float(b["value"])
                tol = float(b.get("tolerance_rel", 0.01))
                if abs(new - old) > tol * max(abs(old), 1e-12):
                    add("ERROR", "STALE_VALUE", el, "bound value %s=%s differs from fresh NeqSim run %s (tolerance %s)" % (b.get("address"), old, new, tol))
    return out


def register_status(findings: Sequence[dict]) -> str:
    """FAIL if any ERROR, WARN if any WARN, else PASS."""
    sev = {f["severity"] for f in findings}
    return "FAIL" if "ERROR" in sev else "WARN" if "WARN" in sev else "PASS"


def assumed_summary(register: Iterable[dict], figure: str | None = None) -> list[str]:
    """Names of ASSUMED elements (optionally for one figure) for the legend/footnote text."""
    return [e["element"] for e in register if e.get("status") == "ASSUMED" and (figure is None or figure in e.get("figures", []))]


def legend_line(register: Iterable[dict], figure: str, max_items: int = 14) -> str:
    """Norwegian legend sentence that names the ASSUMED elements of a figure."""
    names = assumed_summary(register, figure)
    if not names:
        return "Alle viste elementer har kilde i kilderegisteret."
    shown = ", ".join(names[:max_items]) + (" m.fl" if len(names) > max_items else "")
    return "%s (ikke funnet i kildene): %s." % (LEGEND_TEXT_NO.capitalize(), shown)


def to_markdown(register: Sequence[dict], title: str = "Kilder til illustrasjoner") -> str:
    """Markdown table of the register."""
    rows = ["# %s" % title, "", "| Element | Type | Status | Kilde (dokument, rev., side) | NeqSim-binding | Figurer |", "|---|---|---|---|---|---|"]
    for e in register:
        s = e.get("source") or {}
        src = "; ".join(x for x in (s.get("doc_no"), ("rev. %s" % s["revision"]) if s.get("revision") else None, ("s. %s" % s["page"]) if s.get("page") else None, s.get("file")) if x) \
            if e["status"] != "ASSUMED" else "ANTATT: %s" % e.get("reason", "")
        b = e.get("neqsim_binding")
        bind = "%s : %s = %s" % (b["unit"], b["address"], b["value"]) if b else ""
        rows.append("| %s | %s | %s | %s | %s | %s |" % (e["element"], e.get("kind", ""), e["status"], src.replace("|", "/"), bind.replace("|", "/"), ", ".join(e.get("figures", []))))
    return "\n".join(rows) + "\n"


def save(register: Sequence[dict], path: str) -> None:
    """Write the register as JSON."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"schema": "neqsim_illustration_sources.v1", "elements": list(register)}, fh, indent=1, ensure_ascii=False)


def load(path: str) -> list[dict]:
    """Read a register written by :func:`save`."""
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["elements"]
