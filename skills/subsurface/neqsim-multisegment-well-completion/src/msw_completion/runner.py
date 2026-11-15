"""Run completor in-process on a schedule (or a whole deck) and read the device layer back."""

from __future__ import annotations

import contextlib
import io
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Union

from .msw import keyword_blocks, split_schedule

MISSING_COMPLETOR = ("completor is not installed in this Python environment. It is declared in this skill's "
                     "pyproject.toml (completor>=1.6); install the skill's dependencies, do not pip install at run "
                     "time.")


class CompletorUnavailable(RuntimeError):
    """completor cannot be imported."""


def completor_version() -> Optional[str]:
    try:
        from importlib.metadata import version

        return version("completor")
    except Exception:  # noqa: BLE001 - any metadata failure means "unknown"
        return None


def run_completor(case_text: str, schedule_text: str, output_path: Union[str, Path]) -> Dict[str, object]:
    """Run completor on schedule text and write the advanced schedule to ``output_path``.

    A whole deck may be passed: only the SCHEDULE section is processed and the rest is kept unchanged.
    Returns ``{"output", "warnings", "completor_version"}``; raises ``CompletorUnavailable`` or the completor
    error (which names the offending well or keyword).
    """
    try:
        from completor.main import create
    except ImportError as exc:
        raise CompletorUnavailable(MISSING_COMPLETOR) from exc
    head, schedule = split_schedule(schedule_text)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = output_path.with_suffix(output_path.suffix + ".schedule.tmp")
    records: List[str] = []

    class _Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    handler = _Collect(level=logging.WARNING)
    logger = logging.getLogger("completor.logger")  # completor's own logger, with console handlers
    saved = (list(logger.handlers), logger.propagate)
    logger.handlers, logger.propagate = [handler], False
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            create(case_text, schedule, str(tmp))
        advanced = tmp.read_text(encoding="utf-8")
    finally:
        logger.handlers, logger.propagate = saved
        if tmp.exists():
            tmp.unlink()
    warnings = [m for m in records if "Could not resolve case-file path" not in m]
    output_path.write_text(head + advanced, encoding="utf-8")
    return {"output": str(output_path), "warnings": warnings, "completor_version": completor_version()}


def _num(token: Optional[str]) -> Optional[float]:
    try:
        return float(token) if token is not None else None
    except ValueError:
        return None


def read_device_layer(deck_text: str) -> Dict[str, Dict[str, object]]:
    """Summarise a completor output deck per well: segments, branches and devices per segment.

    Device rows carry ``segment``, ``kind`` and ``devices`` (from the scale factor ``-1/N`` for AICD and ICD;
    for valves completor multiplies Cv by N instead, so ``cv_segment`` is reported).
    """
    wells: Dict[str, Dict[str, object]] = {}

    def well(name: str) -> Dict[str, object]:
        return wells.setdefault(name, {"segments": 0, "branches": set(), "devices": [], "md_by_segment": {}})

    for _, _, recs in keyword_blocks(deck_text, "WELSEGS"):
        if not recs:
            continue
        name = (recs[0][0] or "").strip("'")
        entry = well(name)
        for rec in recs[1:]:
            seg, branch, md = int(rec[0]), int(rec[2]), _num(rec[4])
            entry["segments"] = max(int(entry["segments"]), seg)
            entry["branches"].add(branch)
            entry["md_by_segment"][seg] = md
    for kw, kind in (("WSEGAICD", "AICD"), ("WSEGSICD", "ICD")):
        for _, _, recs in keyword_blocks(deck_text, kw):
            for rec in recs:
                scale = _num(rec[4])
                devices = round(-1.0 / scale, 6) if scale and scale < 0 else None
                row = {"segment": int(rec[1]), "kind": kind, "strength": _num(rec[3]), "devices": devices}
                if kind == "AICD":
                    # after expanding the 5* defaults: 12 = X, 13 = Y, 14 = FLAG, 15-20 = a-f, 21 = Z
                    row.update({"x": _num(rec[12]), "y": _num(rec[13]), "z": _num(rec[21]) if len(rec) > 21 else None})
                well((rec[0] or "").strip("'"))["devices"].append(row)
    for _, _, recs in keyword_blocks(deck_text, "WSEGVALV"):
        for rec in recs:
            if not rec or rec[0] is None or not re.match(r"^'?[A-Za-z0-9_\-]+'?$", rec[0]):
                continue
            name = rec[0].strip("'")
            seg = int(rec[1])
            entry = well(name)
            if any(d["segment"] == seg for d in entry["devices"]):
                continue  # ACTIONX switches of a density device repeat the segment
            entry["devices"].append({"segment": seg, "kind": "VALVE", "cv_segment": _num(rec[2]),
                                     "area_m2": _num(rec[3])})
    density_segments = set(re.findall(r"SWHF\s+'?([^'\s]+)'?\s+(\d+)", deck_text))
    for name, seg in density_segments:
        for d in wells.get(name, {}).get("devices", []):
            if d["segment"] == int(seg):
                d["kind"] = "DENSITY"
    summary = {}
    for name, entry in wells.items():
        devices = sorted(entry["devices"], key=lambda d: d["segment"])
        for d in devices:
            d["md"] = entry["md_by_segment"].get(d["segment"])
        counts: Dict[str, int] = {}
        for d in devices:
            counts[d["kind"]] = counts.get(d["kind"], 0) + 1
        summary[name] = {"segments": entry["segments"], "branches": len(entry["branches"]),
                         "device_segments": counts, "devices": devices}
    return summary
