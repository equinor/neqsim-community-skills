"""Command line: ``<python> -m flare_helideck_dispersion run|figures|overlay|facility config.json``.

* ``section`` - vertical section of the plume through a source (JSON of ``s``, ``z``,
  ``values`` in percent of the limit) and the receptors in that plane, for a schematic
  overlay on a picture of the facility (config key ``section``).
* ``facility`` - any release sources against any receptors (air intakes, muster areas,
  escape routes, crane cabs, helideck and flight paths, ...), optional ``--figures``,
  ``facility_fragment.json``. See :func:`facility_inputs` for the configuration keys.
* ``run`` - helideck and flight-path wind sweep, optional sensitivity,
  ``results_fragment.json``.
* ``figures`` - house-style figures from the saved run, and the fragment with captions
  and discussion.
* ``overlay`` - schematic overlay of a plume section on a user-supplied image.

The JSON configuration holds ``output_dir``, ``geometry``, ``wind`` (``table_json``,
``hourly_csv`` or an inline ``table``), ``releases``, optional ``settings``,
``sensitivity``, ``benchmarks``, ``psv_table``, ``criteria``, ``flameout`` and
``overlay``. Relative paths are resolved against the folder of the configuration file.
See the skill README for a complete example.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .facility import (
    FacilityRelease,
    FacilityStudyResult,
    Receptor,
    Source,
    build_release,
    facility_section,
    facility_tilt_scan,
    helideck_facility,
    run_facility_study,
    write_facility_section,
)
from .facility_results import build_facility_results
from .model import ReleaseCase
from .receptors import PlatformGeometry
from .results import build_results, validate_fragment, write_results_json
from .sensitivity import run_sensitivity
from .sources import release_case_from_composition
from .study import (
    BenchmarkScenario,
    StudyResult,
    StudySettings,
    load_study,
    run_study,
)
from .wind import WindTable


def _resolve(base: Path, value: str) -> Path:
    """Resolve a path from the configuration against the configuration folder."""
    p = Path(value)
    return p if p.is_absolute() else (base / p).resolve()


def _case(data: dict[str, Any]) -> ReleaseCase:
    """Build a release case from a configuration mapping (composition optional)."""
    data = dict(data)
    if "composition" in data:
        return release_case_from_composition(
            data.pop("name"),
            data.pop("mass_flow_kg_s"),
            data.pop("composition"),
            data.pop("gamma"),
            data.pop("t0_k"),
            **{
                k: v
                for k, v in data.items()
                if k
                in (
                    "tip_diameter_m",
                    "tip_override",
                    "rho_gas_amb_kg_m3",
                    "description",
                )
            },
        )
    return ReleaseCase.from_dict(data)


class Inputs:
    """Inputs parsed from a configuration file.

    Args:
        config_path: Path of the JSON configuration.
    """

    def __init__(self, config_path: Path) -> None:
        self.base = config_path.resolve().parent
        self.cfg: dict[str, Any] = json.loads(config_path.read_text(encoding="utf-8"))
        self.out = _resolve(
            self.base, self.cfg.get("output_dir", "flare_helideck_output")
        )
        self.geometry = PlatformGeometry.from_dict(self.cfg.get("geometry", {}))
        self.settings = StudySettings.from_dict(self.cfg.get("settings", {}))
        self.cases: list[ReleaseCase] = [_case(c) for c in self.cfg["releases"]]
        self.wind = self._wind(self.cfg["wind"])

    def _wind(self, spec: dict[str, Any]) -> WindTable:
        """Load the wind table from the configuration."""
        low = float(spec.get("low_bin_speed_ms", 1.5))
        if "table_json" in spec:
            return WindTable.load_json(_resolve(self.base, spec["table_json"]), low)
        if "table" in spec:
            return WindTable.from_dict(spec["table"], low)
        if "hourly_csv" in spec:
            return WindTable.from_hourly_csv(
                _resolve(self.base, spec["hourly_csv"]),
                spec.get("speed_column"),
                spec.get("direction_column"),
                float(spec.get("speed_scale", 1.0)),
                sector_count=int(spec.get("sector_count", 16)),
                low_bin_speed_ms=low,
            )
        raise ValueError("wind needs table_json, table or hourly_csv")

    def benchmarks(self) -> list[BenchmarkScenario]:
        """Benchmark scenarios from the configuration."""
        out = []
        for b in self.cfg.get("benchmarks", []):
            out.append(
                BenchmarkScenario(
                    b["label"],
                    _case(b["case"]),
                    float(b["speed_m_s"]),
                    b.get("reference_outcome", ""),
                    b.get("reference_source", ""),
                    b.get("reference_pct_lfl_max"),
                )
            )
        return out


def _write_fragment(
    inp: Inputs,
    study: StudyResult,
    figures: Sequence[Any],
    sens: dict[str, Any] | None,
) -> list[str]:
    """Build and write the results fragment; return validation problems."""
    flame = inp.cfg.get("flameout", {})
    fragment = build_results(
        study,
        figures,
        sens,
        inp.benchmarks(),
        inp.cfg.get("criteria"),
        flame.get("frequency_per_year"),
        flame.get("hours_per_release"),
    )
    write_results_json(inp.out / "results_fragment.json", fragment, merge=False)
    return validate_fragment(fragment)


def cmd_run(inp: Inputs) -> int:
    """Run the study, the sensitivity and write the fragment."""
    study = run_study(inp.cases, inp.wind, inp.geometry, inp.settings)
    study.save(inp.out)
    sens = None
    spec = inp.cfg.get("sensitivity")
    if spec:
        ranges = (
            {k: tuple(v) for k, v in spec["ranges"].items()}
            if spec.get("ranges")
            else None
        )
        sens = run_sensitivity(
            inp.cases,
            inp.wind,
            study.receptors,
            inp.settings,
            spec.get("tilt_scan_cases"),
            spec.get("cases"),
            spec.get("tilts", (20.0, 25.0, 30.0, 35.0, 40.0, 55.0, 70.0)),
            int(spec.get("n_samples", 100)),
            int(spec.get("seed", 42)),
            ranges,
        )
        (inp.out / "uncertainty.json").write_text(
            json.dumps(sens, indent=1), encoding="utf-8"
        )
    problems = _write_fragment(inp, study, [], sens)
    for name, entry in study.summaries.items():
        m = entry["modes"]["briggs"]
        sys.stdout.write(
            "{}: helideck {:.2f} % LFL, any path {:.1f} % LFL, >=20 % LFL on {:.2f} % of wind hours (given a release)\n".format(
                name,
                m["peak_pct_lfl_helideck"],
                m["peak_pct_lfl_any_path"],
                m["exceed_pct_hours"]["20"]["any_path"],
            )
        )
    for p in problems:
        sys.stdout.write(f"results fragment problem: {p}\n")
    sys.stdout.write(f"wrote {inp.out}\n")
    return 0


def _load_saved(inp: Inputs) -> StudyResult:
    """Reload the saved study; ask for ``run`` first when it is missing."""
    if not (inp.out / "study_results.json").exists():
        raise FileNotFoundError(
            f"no saved study in {inp.out}; run the 'run' command first"
        )
    return load_study(inp.out, inp.cases, inp.wind, inp.geometry, inp.settings)


def cmd_figures(inp: Inputs) -> int:
    """Create the figures from the saved run."""
    from .figures import make_all_figures

    study = _load_saved(inp)
    sens = None
    unc = inp.out / "uncertainty.json"
    if unc.exists():
        sens = json.loads(unc.read_text(encoding="utf-8"))
    records = make_all_figures(
        study,
        str(inp.out / "figures"),
        sens,
        inp.benchmarks() or None,
        inp.cfg.get("psv_table"),
    )
    bad = 0
    for r in records:
        sys.stdout.write(
            "{} {}\n".format(
                r.name, "OK" if not r.problems else "LAYOUT: " + "; ".join(r.problems)
            )
        )
        bad += bool(r.problems)
    problems = _write_fragment(inp, study, records, sens)
    for p in problems:
        sys.stdout.write(f"results fragment problem: {p}\n")
    return 1 if bad else 0


def cmd_overlay(inp: Inputs) -> int:
    """Create the schematic overlay from the saved run."""
    from .overlay import compose_overlay_figure

    spec = inp.cfg["overlay"]
    study = _load_saved(inp)
    res = compose_overlay_figure(
        study,
        spec["case"],
        float(spec["wind_from_deg"]),
        float(spec["speed_m_s"]),
        _resolve(inp.base, spec["image"]),
        (float(spec["anchor_px"][0]), float(spec["anchor_px"][1])),
        float(spec["px_per_m"]),
        _resolve(inp.base, spec.get("out", str(inp.out / "figures" / "overlay.png"))),
        disclaimer=spec.get("disclaimer"),
        image_note=spec.get("image_note", ""),
    )
    sys.stdout.write(f"wrote {res.path} (max {res.max_pct_lfl:.0f} % LFL in view)\n")
    for p in res.problems:
        sys.stdout.write(f"LAYOUT: {p}\n")
    return 1 if res.problems else 0


def facility_inputs(inp: Inputs) -> tuple[list[FacilityRelease], list[Receptor]]:
    """Build the sources, release cases and receptors of a facility configuration.

    The configuration holds ``sources`` (mappings for :meth:`Source.from_dict`),
    ``receptors`` (mappings for :meth:`Receptor.from_dict`), optionally ``helideck``
    (platform geometry fields plus ``source``, which adds the helideck, any flight path
    and into-wind path receptors around the named source) and ``releases`` whose
    ``source`` key names the source of each case (default: the first source).

    Args:
        inp: Parsed configuration.

    Returns:
        Tuple ``(releases, receptors)``.

    Raises:
        ValueError: If no source is defined or a release names an unknown source.
    """
    sources = [Source.from_dict(s) for s in inp.cfg.get("sources", [])]
    receptors = [Receptor.from_dict(r) for r in inp.cfg.get("receptors", [])]
    deck = inp.cfg.get("helideck")
    if deck is not None:
        spec = dict(deck)
        name = spec.pop("source", None)
        geometry = PlatformGeometry.from_dict(spec)
        known = {s.name: s for s in sources}
        if name and name in known:
            tip = known[name]
            preset_source, preset = helideck_facility(
                geometry, tip.name, (tip.east_m, tip.north_m)
            )
        else:
            preset_source, preset = helideck_facility(geometry, name or "flare_tip")
            sources.append(preset_source)
        receptors.extend(preset)
    if not sources:
        raise ValueError("a facility configuration needs sources or a helideck preset")
    by_name = {s.name: s for s in sources}
    releases = []
    for case, raw in zip(inp.cases, inp.cfg["releases"]):
        key = raw.get("source", sources[0].name)
        if key not in by_name:
            raise ValueError(f"release {case.name!r} names unknown source {key!r}")
        releases.append(FacilityRelease(case, by_name[key]))
    return releases, receptors


def cmd_facility(inp: Inputs, with_figures: bool = False) -> int:
    """Run the facility study, optional figures and the results fragment."""
    releases, receptors = facility_inputs(inp)
    study = run_facility_study(releases, inp.wind, receptors, inp.settings)
    study.save(inp.out)
    spec = inp.cfg.get("sensitivity") or {}
    scans: dict[str, Any] | None = None
    if spec:
        tilts = spec.get("tilts", (20.0, 30.0, 40.0, 55.0, 70.0, 90.0))
        scans = {
            fr.case.name: facility_tilt_scan(
                fr, inp.wind, receptors, inp.settings, tilts
            )
            for fr in releases
            if fr.case.name in spec.get("tilt_scan_cases", [f.case.name for f in releases])
        }
        (inp.out / "facility_sensitivity.json").write_text(
            json.dumps(scans, indent=1, default=float), encoding="utf-8"
        )
    records: list[Any] = []
    bad = 0
    if with_figures:
        from .facility_figures import make_facility_figures

        records = make_facility_figures(study, str(inp.out / "figures"))
        for r in records:
            sys.stdout.write(
                "{} {}\n".format(
                    r.name,
                    "OK" if not r.problems else "LAYOUT: " + "; ".join(r.problems),
                )
            )
            bad += bool(r.problems)
    flame = inp.cfg.get("flameout", {})
    fragment = build_facility_results(
        study,
        records,
        scans,
        inp.cfg.get("criteria"),
        flame.get("frequency_per_year"),
        flame.get("hours_per_release"),
    )
    write_results_json(inp.out / "facility_fragment.json", fragment, merge=False)
    for row in study.ranking(20.0)[:10]:
        sys.stdout.write(
            "{} -> {}: peak {:.2f} % LFL, >=20 % LFL on {:.2f} % of wind hours (given a release)\n".format(
                row["case"], row["receptor"], row["peak_pct_lfl"], row["exceed_pct_hours"]
            )
        )
    for p in validate_fragment(fragment):
        sys.stdout.write(f"results fragment problem: {p}\n")
    sys.stdout.write(f"wrote {inp.out}\n")
    return 1 if bad else 0


def cmd_section(inp: Inputs) -> int:
    """Write the vertical section JSON (and the receptor marks) of one case and wind."""
    spec = inp.cfg["section"]
    releases, receptors = facility_inputs(inp)
    sources = list({fr.source.name: fr.source for fr in releases}.values())
    study = FacilityStudyResult(
        inp.settings,
        inp.wind,
        sources,
        receptors,
        {fr.case.name: build_release(fr, inp.settings) for fr in releases},
        releases,
        {},
        {},
        [],
    )
    section = facility_section(
        study,
        spec["case"],
        float(spec["wind_from_deg"]),
        float(spec["speed_m_s"]),
        tuple(spec.get("s_range_m", (-50.0, 600.0))),
        tuple(spec.get("z_range_m", (2.0, 200.0))),
        float(spec.get("ds_m", 5.0)),
        float(spec.get("dz_m", 2.0)),
        spec.get("azimuth_deg"),
        lateral_tolerance_m=float(spec.get("tolerance_m", 15.0)),
    )
    out = write_facility_section(_resolve(inp.base, spec.get("out", str(inp.out / "section.json"))), section)
    sys.stdout.write(f"wrote {out} (peak {section['peak_pct_lfl']:.1f} % LFL in the plane)\n")
    for m in section["marks"]:
        sys.stdout.write(
            "mark: {:.0f},{:.0f},{} (schematic; {:.0f} m off the plane, {:.1f} % LFL there)\n".format(
                m["s_m"], m["z_m"], m["label"], m["lateral_offset_m"], m["peak_pct_lfl_here"]
            )
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point.

    Args:
        argv: Command-line arguments (default ``sys.argv[1:]``).

    Returns:
        Process exit code (0 on success).
    """
    parser = argparse.ArgumentParser(
        prog="flare_helideck_dispersion", description=__doc__.splitlines()[0]
    )
    parser.add_argument(
        "command", choices=["run", "figures", "overlay", "facility", "section"]
    )
    parser.add_argument("config", help="JSON configuration file")
    parser.add_argument(
        "--figures",
        action="store_true",
        help="facility: also write the plan and exceedance figures",
    )
    args = parser.parse_args(argv)
    inp = Inputs(Path(args.config))
    if args.command == "facility":
        return cmd_facility(inp, args.figures)
    if args.command == "section":
        return cmd_section(inp)
    return {"run": cmd_run, "figures": cmd_figures, "overlay": cmd_overlay}[
        args.command
    ](inp)


if __name__ == "__main__":
    raise SystemExit(main())
