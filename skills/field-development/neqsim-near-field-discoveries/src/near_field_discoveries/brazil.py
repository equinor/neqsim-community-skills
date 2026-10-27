"""Brazilian discoveries from public ANP GeoServer layers.

ANP publishes no list of discoveries with names and volumes. A discovery is
therefore reconstructed from what is public:

* exploratory wells whose result is hydrocarbon-bearing (``reclassificacao``),
* the field polygons (a well inside a field belongs to that field),
* the discovery-evaluation plan polygons (PAD, layer ``geoanp:pad``),
* exploration blocks (``NUM_DESCOB`` counts notified discoveries) and returned blocks.

Hydrocarbon-bearing wells outside every field are single-linkage clustered into
discovery candidates and each candidate is staged from the plan polygon, block
and field layers. The result is a screening inventory; the operator's discovery
notification, evaluation plan and any declaration of commerciality are the
authority, and volumes are not public.
"""

from __future__ import annotations

import datetime as _dt
import re
import unicodedata
from typing import Any, Iterable, Mapping, Sequence

from .geo import (
    bbox_around,
    cluster_points,
    median,
    point_from_geometry,
    point_in_rings,
    point_to_rings_km,
    rings_from_geometry,
)
from .models import Discovery

EXPLORATORY_CATEGORIES = {
    "PIONEIRO",
    "PIONEIRO ADJACENTE",
    "EXTENSAO",
    "JAZIDA MAIS PROFUNDA",
    "JAZIDA MAIS RASA",
}
RESULT_RANK = {"discovery": 0, "commercial": 1, "subcommercial": 2, "bearing": 3, "extension": 4, "shows": 5}
HYDROCARBON_RESULTS = ("discovery", "commercial", "subcommercial", "bearing", "extension")
FIELD_STAGES = {"PRODUCAO": "producing", "DESENVOLVIMENTO": "in_development", "EM DEVOLUCAO": "unlikely"}
ANP_EXTRA_LAYERS = {
    "evaluation_plans": "geoanp:pad",
    "relinquished_blocks": "geoanp:blocos_exploratorios_devolvidos",
    "relinquished_fields": "geoanp:campos_de_producao_devolvidos",
    "production_units": "geoanp:unidade_de_producao",
}
"""Layers this module reads that ``anp_open_data.ANP_LAYERS`` may not alias; checked 2026-10-27."""

GAP_NO_VOLUMES = "ANP publishes no volumes for discoveries; supply operator or concession-contract figures."
GAP_NO_NAME = "ANP publishes no discovery name; the discovery well name is used."


def fold(text: Any) -> str:
    """Upper-case, accent-free, single-spaced form of an ANP string (damaged characters become ``?``)."""
    if not isinstance(text, str):
        return ""
    s = text.replace("\ufffd", "?")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip().upper()


def classify_well_result(reclassificacao: Any) -> tuple[str, str | None]:
    """Classify an ANP well result text.

    Args:
        reclassificacao: Value of the ``reclassificacao`` property of a well.

    Returns:
        ``(result_class, fluid)``. ``result_class`` is one of ``discovery``, ``commercial``,
        ``subcommercial``, ``bearing``, ``extension``, ``shows``, ``dry`` or ``other``;
        ``fluid`` is ``oil``, ``gas``, ``oil+gas``, ``gas-condensate`` or ``None``.
    """
    t = fold(reclassificacao)
    if t.startswith("DESCOBRIDOR"):
        cls = "discovery"
    elif t.startswith("PRODUTOR COMERCIAL"):
        cls = "commercial"
    elif t.startswith("PRODUTOR SUBCOMERCIAL"):
        cls = "subcommercial"
    elif t.startswith("PORTADOR"):
        cls = "bearing"
    elif t.startswith("EXTENSAO PARA"):
        cls = "extension"
    elif t.startswith("SECO COM"):
        cls = "shows"
    elif t.startswith("SECO SEM"):
        cls = "dry"
    else:
        cls = "other"
    if "CONDENSADO" in t:
        fluid = "gas-condensate"
    elif "PETROLEO E GAS" in t:
        fluid = "oil+gas"
    elif "GAS NATURAL" in t:
        fluid = "gas"
    elif "PETROLEO" in t:
        fluid = "oil"
    else:
        fluid = None
    return cls, fluid


def parse_date(value: Any) -> _dt.date | None:
    """Parse the date styles seen in ANP layers (ISO, ``dd/mm/yyyy``, ``dd-mm-yyyy``, damaged ISO)."""
    if value is None:
        return None
    s = str(value).strip()
    for pattern, order in (
        (r"^(\d{4})-(\d{2})-(\d{2})", "ymd"),
        (r"^(\d{2})/(\d{2})/(\d{4})", "dmy"),
        (r"^(\d{2})-(\d{2})-(\d{4})", "dmy"),
    ):
        m = re.match(pattern, s)
        if m:
            a, b, c = (int(x) for x in m.groups())
            y, mo, d = (a, b, c) if order == "ymd" else (c, b, a)
            try:
                return _dt.date(y, mo, d)
            except ValueError:
                return None
    m = re.match(r"^(\d{4})-(\d{2})", s)
    if m:
        try:
            return _dt.date(int(m.group(1)), int(m.group(2)), 1)
        except ValueError:
            return None
    return None


def _features(layer: Any) -> list[dict]:
    if layer is None:
        return []
    if isinstance(layer, Mapping):
        return list(layer.get("features", []))
    return list(layer)


def _props(feature: Mapping[str, Any]) -> Mapping[str, Any]:
    return feature.get("properties") or {}


def _well_point(feature: Mapping[str, Any]) -> tuple[float, float] | None:
    p = _props(feature)
    lat, lon = p.get("latitude"), p.get("longitude")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)) and (lat or lon):
        return float(lon), float(lat)
    return point_from_geometry(feature.get("geometry"))


def _num(value: Any) -> float | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def field_records(fields: Any) -> list[Discovery]:
    """Field polygons as records staged from the ANP ``etapa`` (production, development, returned)."""
    out = []
    for f in _features(fields):
        p = _props(f)
        name = str(p.get("name") or p.get("nome_campo") or "").strip()
        rings = rings_from_geometry(f.get("geometry"))
        pt = point_from_geometry(f.get("geometry"))
        if not name or pt is None:
            continue
        etapa = str(p.get("etapa") or "")
        stage = FIELD_STAGES.get(fold(etapa), "unknown")
        started = parse_date(p.get("dat_inicio"))
        discovered = parse_date(p.get("dat_descob"))
        fluid = fold(p.get("fluido_pri"))
        out.append(
            Discovery(
                country="BR",
                id="BR_FIELD_" + re.sub(r"\W+", "_", fold(name)),
                name=name,
                kind="field",
                stage=stage,
                status_raw=etapa or None,
                hc_type={"OLEO": "oil", "GAS": "gas"}.get(fluid, fluid.lower() or None),
                discovery_year=discovered.year if discovered else None,
                operator=(p.get("operador") or None),
                lon=pt[0],
                lat=pt[1],
                position_basis="polygon-centroid",
                rings=rings,
                water_depth_m=_num(p.get("med_lamina")),
                plan_note=("production start " + started.isoformat()) if started else None,
                linked={"basin": p.get("nome_bacia"), "round": p.get("num_rodada")},
                source="ANP GeoServer sisroc:campos_gishub_db",
                gaps=[GAP_NO_VOLUMES],
            )
        )
    return out


def evaluation_area_records(plans: Any, as_of: _dt.date) -> list[Discovery]:
    """Discovery-evaluation plan (PAD) polygons as ``evaluation_area`` records."""
    out = []
    for f in _features(plans):
        p = _props(f)
        name = str(p.get("NOME_PAD") or "").strip()
        pt = point_from_geometry(f.get("geometry"))
        if not name or pt is None:
            continue
        end = parse_date(p.get("DAT_TERM"))
        start = parse_date(p.get("DAT_INICIO"))
        active = end is not None and end >= as_of
        out.append(
            Discovery(
                country="BR",
                id="BR_PAD_" + re.sub(r"\W+", "_", fold(name)),
                name=name,
                kind="evaluation_area",
                stage="in_clarification" if active else "unknown",
                status_raw="PAD code %s" % (p.get("IN_PL_ATIV") or "?"),
                lon=pt[0],
                lat=pt[1],
                position_basis="polygon-centroid",
                rings=rings_from_geometry(f.get("geometry")),
                plan_note="Discovery evaluation plan %s to %s (%s)"
                % (start.isoformat() if start else "?", end.isoformat() if end else "?", "running" if active else "ended or no end date"),
                linked={"block": p.get("COD_BLOCO"), "basin": p.get("NOM_BACIA"), "area_km2": _num(p.get("AREA"))},
                source="ANP GeoServer geoanp:pad",
                gaps=["The meaning of the plan status code is not documented in the layer; confirm with ANP.", GAP_NO_VOLUMES],
            )
        )
    return out


def discovery_candidates(
    wells: Any,
    fields: Any = None,
    evaluation_plans: Any = None,
    blocks: Any = None,
    relinquished_blocks: Any = None,
    *,
    as_of: _dt.date | None = None,
    link_km: float = 5.0,
    field_buffer_km: float = 3.0,
    include_shows: bool = False,
    aliases: Mapping[str, str] | None = None,
    known_volumes: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[Discovery]:
    """Reconstruct discovery candidates from hydrocarbon-bearing exploratory wells outside fields.

    Args:
        wells: ANP well features (``sisroc:pocos_gishub_db``) as a list or FeatureCollection.
        fields: ANP field features; wells inside or within ``field_buffer_km`` of a field belong to it.
        evaluation_plans: ANP PAD features (``geoanp:pad``).
        blocks: ANP exploration-block features (``sisroc:block_shp_geoanp``).
        relinquished_blocks: ANP returned-block features.
        as_of: Date used to decide whether an evaluation plan is running; defaults to today.
        link_km: Single-linkage distance joining wells into one candidate.
        field_buffer_km: Distance from a field outline within which a well is treated as in the field.
        include_shows: Also treat wells with oil or gas shows only (``SECO COM INDICIOS``) as evidence.
        aliases: Optional ``{well name or candidate id: public name}``, for example a name from an operator release.
        known_volumes: Optional ``{well name or candidate id: volume dict}`` from a non-ANP source; each
            entry should carry its own ``source`` key.

    Returns:
        Candidate records sorted by name. Fields and evaluation areas are not included; use
        :func:`field_records` and :func:`evaluation_area_records` for those.
    """
    as_of = as_of or _dt.date.today()
    aliases = {fold(k): v for k, v in (aliases or {}).items()}
    known = {fold(k): dict(v) for k, v in (known_volumes or {}).items()}
    field_rings = [(str(_props(f).get("name") or ""), rings_from_geometry(f.get("geometry"))) for f in _features(fields)]
    plan_feats = [(f, rings_from_geometry(f.get("geometry"))) for f in _features(evaluation_plans)]
    block_feats = [(f, rings_from_geometry(f.get("geometry"))) for f in _features(blocks)]
    ret_feats = [(f, rings_from_geometry(f.get("geometry"))) for f in _features(relinquished_blocks)]

    classes = HYDROCARBON_RESULTS + (("shows",) if include_shows else ())
    evidence: list[dict[str, Any]] = []
    for f in _features(wells):
        p = _props(f)
        exploratory = fold(p.get("tipo")).startswith("EXPLORAT") or fold(p.get("categoria")) in EXPLORATORY_CATEGORIES
        cls, fluid = classify_well_result(p.get("reclassificacao"))
        pt = _well_point(f)
        if not exploratory or cls not in classes or pt is None:
            continue
        in_field = None
        for fname, rings in field_rings:
            d = point_to_rings_km(pt[0], pt[1], rings)
            if d is not None and d <= field_buffer_km:
                in_field = fname
                break
        if in_field is None and p.get("nome_campo"):
            in_field = str(p.get("nome_campo"))
        if in_field:
            continue
        evidence.append({"props": p, "pt": pt, "cls": cls, "fluid": fluid})

    groups = cluster_points([e["pt"] for e in evidence], link_km)
    out: list[Discovery] = []
    for g in groups:
        members = [evidence[i] for i in g]
        members.sort(key=lambda e: (RESULT_RANK[e["cls"]], parse_date(e["props"].get("dat_conclusao")) or _dt.date.max))
        lead = members[0]
        lon = median([m["pt"][0] for m in members])
        lat = median([m["pt"][1] for m in members])
        names = [str(m["props"].get("name") or "").strip() for m in members]
        key = fold(names[0])
        cid = "BR_DSC_" + re.sub(r"\W+", "_", key)
        fluids = sorted({m["fluid"] for m in members if m["fluid"]})
        if "oil+gas" in fluids:
            fluids = [f for f in fluids if f not in ("oil", "gas")]
        years = [d.year for d in (parse_date(m["props"].get("dat_conclusao")) for m in members) if d]
        depths = [v for v in (_num(m["props"].get("lamina_dagua")) for m in members) if v]
        counts: dict[str, int] = {}
        for m in members:
            counts[m["cls"]] = counts.get(m["cls"], 0) + 1

        stage, note = "not_evaluated", "No public evaluation plan, field or returned block contains the wells."
        linked: dict[str, Any] = {"discovery_wells": names, "well_results": counts, "operator_of_lead_well": lead["props"].get("operador")}
        gaps = [GAP_NO_NAME, GAP_NO_VOLUMES]
        plan = next(((f, r) for f, r in plan_feats if point_in_rings(lon, lat, r)), None)
        if plan is not None:
            pp = _props(plan[0])
            end = parse_date(pp.get("DAT_TERM"))
            running = end is not None and end >= as_of
            linked["evaluation_plan"] = pp.get("NOME_PAD")
            linked["evaluation_plan_end"] = end.isoformat() if end else None
            if running:
                stage, note = "in_clarification", "Inside discovery-evaluation plan %s running to %s." % (pp.get("NOME_PAD"), end.isoformat())
            else:
                stage = "unknown"
                note = "Inside evaluation plan %s that ended %s; the outcome is not in the public layers." % (
                    pp.get("NOME_PAD"), end.isoformat() if end else "(no end date)")
        blk = next(((f, r) for f, r in block_feats if point_in_rings(lon, lat, r)), None)
        if blk is not None:
            bp = _props(blk[0])
            linked["block"] = bp.get("NOM_BLOCO") or bp.get("COD_BLOCO")
            linked["basin"] = bp.get("NOM_BACIA")
            linked["block_operator"] = bp.get("OPERADOR_C")
            linked["block_notified_discoveries"] = bp.get("NUM_DESCOB")
        if plan is None and any(point_in_rings(lon, lat, r) for _, r in ret_feats):
            stage, note = "unlikely", "Inside an exploration block returned to ANP."
        hc = "/".join(x.upper() for x in fluids) if fluids else None
        rec = Discovery(
            country="BR",
            id=cid,
            name=aliases.get(key) or aliases.get(cid.upper()) or names[0],
            kind="discovery",
            stage=stage,
            status_raw="; ".join("%d %s" % (n, c) for c, n in sorted(counts.items())),
            hc_type=hc,
            discovery_year=min(years) if years else None,
            operator=linked["operator_of_lead_well"] or linked.get("block_operator"),
            lat=lat,
            lon=lon,
            position_basis="wellhead" if len(members) == 1 else "approximate-derived-from-ANP-wells",
            plan_note=note,
            linked=linked,
            water_depth_m=median(depths) if depths else None,
            n_wells=len(members),
            source="ANP GeoServer sisroc:pocos_gishub_db + geoanp:pad + sisroc:campos_gishub_db",
            gaps=gaps,
        )
        extra = known.get(key) or known.get(fold(cid))
        if extra:
            rec.volumes = extra
            rec.gaps = [g_ for g_ in rec.gaps if g_ != GAP_NO_VOLUMES]
        if aliases.get(key):
            rec.gaps = [g_ for g_ in rec.gaps if g_ != GAP_NO_NAME]
            rec.linked["name_source"] = "user alias"
        out.append(rec)
    out.sort(key=lambda r: r.name)
    return out


def brazil_records(layers: Mapping[str, Any], *, as_of: _dt.date | None = None, include_fields: bool = True,
                   include_evaluation_areas: bool = True, **kwargs: Any) -> list[Discovery]:
    """All Brazilian records from a layer dict: candidates, fields and evaluation areas.

    Args:
        layers: Mapping with ``wells`` and optionally ``fields``, ``evaluation_plans``, ``blocks``,
            ``relinquished_blocks`` (lists or FeatureCollections).
        as_of: Date for running-plan tests.
        include_fields: Add field polygons.
        include_evaluation_areas: Add PAD polygons.
        **kwargs: Passed to :func:`discovery_candidates`.

    Returns:
        Records of kind ``discovery``, ``field`` and ``evaluation_area``.
    """
    as_of = as_of or _dt.date.today()
    recs = discovery_candidates(
        layers.get("wells"), layers.get("fields"), layers.get("evaluation_plans"), layers.get("blocks"),
        layers.get("relinquished_blocks"), as_of=as_of, **kwargs)
    if include_fields:
        recs += field_records(layers.get("fields"))
    if include_evaluation_areas:
        recs += evaluation_area_records(layers.get("evaluation_plans"), as_of)
    return recs


def hosts_from_production_units(units: Any) -> list[dict[str, Any]]:
    """Hosts from the ANP production-unit layer (point per platform or FPSO).

    Args:
        units: Features of ``geoanp:unidade_de_producao``.

    Returns:
        Dicts with ``name``, ``lat``, ``lon``, ``kind``, ``operator``, ``water_depth_m``, ``serves`` and ``source``.
    """
    out = []
    for f in _features(units):
        p = _props(f)
        pt = point_from_geometry(f.get("geometry"))
        if pt is None or not p.get("NOM_INSTALACAO"):
            continue
        out.append({
            "name": str(p["NOM_INSTALACAO"]).strip(),
            "lon": pt[0],
            "lat": pt[1],
            "kind": p.get("DESC_TIPO_UEP"),
            "operator": p.get("NOM_PROPRIETARIO"),
            "water_depth_m": _num(p.get("MED_DISTANCIA_LAMINA")),
            "serves": p.get("DESC_ATENDIMENTOS"),
            "source": "ANP GeoServer geoanp:unidade_de_producao",
        })
    return out


def fetch_anp_layers(
    point: tuple[float, float],
    radius_km: float,
    cache_dir: Any,
    *,
    offline: bool = False,
    getter: Any = None,
    max_features: int = 30000,
    extra_margin_km: float = 20.0,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Read the ANP layers needed around ``point`` through ``anp_open_data.fetch_layer`` (cached).

    Args:
        point: ``(lon, lat)`` of the target.
        radius_km: Study radius; the read box adds ``extra_margin_km``.
        cache_dir: Task-folder cache directory.
        offline: Reuse cached files only.
        getter: Optional ``getter(url, timeout) -> bytes`` for tests.
        max_features: Per-layer limit; a read reaching it is flagged ``truncated`` in its log record.
        extra_margin_km: Margin added around the radius so polygons crossing the circle are complete.

    Returns:
        ``(layers, logs)``: layers keyed ``wells``, ``fields``, ``evaluation_plans``, ``blocks``,
        ``relinquished_blocks``, ``production_units`` (feature lists) and the per-read log records.

    Raises:
        ImportError: ``anp_open_data`` (skill ``neqsim-anp-open-data``) is not installed.
    """
    try:
        from anp_open_data import fetch_layer
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError("install neqsim-anp-open-data to read ANP layers: pip install -e skills/field-development/neqsim-anp-open-data") from exc
    box = bbox_around(point[0], point[1], radius_km + extra_margin_km)
    plan = {
        "wells": "wells",
        "fields": "fields",
        "evaluation_plans": ANP_EXTRA_LAYERS["evaluation_plans"],
        "blocks": "blocks",
        "relinquished_blocks": ANP_EXTRA_LAYERS["relinquished_blocks"],
        "production_units": ANP_EXTRA_LAYERS["production_units"],
    }
    layers: dict[str, Any] = {}
    logs: list[dict[str, Any]] = []
    for key, layer in plan.items():
        data, log = fetch_layer(layer, cache_dir, bbox=box, max_features=max_features, offline=offline, getter=getter)
        layers[key] = data.get("features", [])
        logs.append(log)
    return layers, logs
