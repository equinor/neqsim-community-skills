"""Read public ANP GeoServer (GeoANP) layers and locate production installations.

ANP publishes blocks, fields, wells, pipelines and gas processing plants as WFS
layers, but it does not publish FPSO or platform point coordinates. The helpers
here fetch layers with a cache and a download log, repair the mixed encodings
that ANP files carry, and derive an approximate installation position as the
median wellhead position of the wells that report production to it.

Only the standard library is required. ``requests`` is used when it is
installed; otherwise ``urllib`` is used.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import re
import statistics
import unicodedata
import urllib.parse
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from .tools import haversine_km

ANP_WFS_BASE = "https://geomaps.anp.gov.br/geoserver/ows"
"""Public ANP GeoServer OWS endpoint (native CRS EPSG:4674, SIRGAS 2000)."""

ANP_LAYERS = {
    "blocks": "sisroc:block_shp_geoanp",
    "awarded_blocks_opc": "geoanp:blocos_arrematados_opc_4deg_ciclo",
    "fields": "sisroc:campos_gishub_db",
    "presalt_polygon": "sisroc:presal_shp_geoanp",
    "gas_outflow_pipelines": "geoanp:gasodutos_de_escoamento",
    "gas_processing_plants": "geoanp:unidade_de_processamento_de_gas_natural",
    "wells": "sisroc:pocos_gishub_db",
    "basins": "sisroc:basin_shp_geoanp",
    "gas_transport_pipelines": "geoanp:gasodutos_de_transporte",
    "oil_outflow_pipelines": "geoanp:oleodutos_de_escoamento",
    "oil_transfer_pipelines": "geoanp:oleodutos_de_transferencia",
    "oil_transport_pipelines": "geoanp:oleodutos_de_transporte",
    "production_units": "geoanp:unidade_de_producao",
    "lng_terminals": "geoanp:terminais_gnl",
    "limit_terminals": "geoanp:terminais_limite",
    "refineries": "geoanp:refinarias",
    "evaluation_plans": "geoanp:pad",
    "relinquished_blocks": "geoanp:blocos_exploratorios_devolvidos",
    "relinquished_fields": "geoanp:campos_de_producao_devolvidos",
}
"""Layer names verified against the ANP GeoServer capabilities document."""


def build_getfeature_url(
    type_name: str,
    cql: str | None = None,
    bbox: Iterable[float] | None = None,
    max_features: int = 5000,
    base: str = ANP_WFS_BASE,
) -> str:
    """Build a WFS 1.0.0 GetFeature URL that returns GeoJSON.

    Args:
        type_name: Layer name, for example ``"sisroc:pocos_gishub_db"`` or a key of
            :data:`ANP_LAYERS`.
        cql: Optional CQL filter, for example ``"NOM_BLOCO='S-M-1378'"``.
        bbox: Optional ``(min_lon, min_lat, max_lon, max_lat)`` in degrees.
            GeoServer does not accept ``bbox`` together with ``cql``.
        max_features: Upper limit on returned features.
        base: OWS endpoint.

    Returns:
        The request URL.

    Raises:
        ValueError: If both ``cql`` and ``bbox`` are given or ``bbox`` is malformed.
    """
    type_name = ANP_LAYERS.get(type_name, type_name)
    params = {
        "service": "WFS",
        "version": "1.0.0",
        "request": "GetFeature",
        "typeName": type_name,
        "outputFormat": "application/json",
        "maxFeatures": str(int(max_features)),
    }
    if cql and bbox is not None:
        raise ValueError("GeoServer rejects CQL_FILTER together with bbox; use one")
    if cql:
        params["CQL_FILTER"] = cql
    if bbox is not None:
        b = [float(v) for v in bbox]
        if len(b) != 4 or b[0] >= b[2] or b[1] >= b[3]:
            raise ValueError("bbox must be (min_lon, min_lat, max_lon, max_lat)")
        params["bbox"] = ",".join(repr(v) for v in b)
    return base + "?" + urllib.parse.urlencode(params)


def _default_get(url: str, timeout: float) -> bytes:
    """Fetch a URL with requests when available, else urllib."""
    try:
        import requests  # type: ignore

        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        return r.content
    except ImportError:  # pragma: no cover - exercised only without requests
        import urllib.request

        with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
            return resp.read()


def fetch_layer(
    type_name: str,
    cache_dir: str | Path,
    cql: str | None = None,
    bbox: Iterable[float] | None = None,
    max_features: int = 5000,
    offline: bool = False,
    getter: Callable[[str, float], bytes] | None = None,
    timeout: float = 120.0,
    base: str = ANP_WFS_BASE,
) -> tuple[dict, dict]:
    """Fetch one WFS layer as GeoJSON, using a cache file named after the query.

    Args:
        type_name: Layer name or :data:`ANP_LAYERS` key.
        cache_dir: Folder for cached GeoJSON and the download log (task folder).
        cql: Optional CQL filter.
        bbox: Optional bounding box.
        max_features: Upper limit on returned features.
        offline: When True, never touch the network; a missing cache is an error.
        getter: Optional ``getter(url, timeout) -> bytes`` (used by tests).
        timeout: Network timeout in seconds.
        base: OWS endpoint.

    Returns:
        ``(geojson, log_record)``. The log record holds layer, file, url,
        retrieved_utc, n_features, status and truncated (True when the count
        reached ``max_features``).

    Raises:
        FileNotFoundError: Offline mode and no cached file.
        ValueError: The response is not a GeoJSON FeatureCollection.
    """
    url = build_getfeature_url(type_name, cql, bbox, max_features, base)
    layer = ANP_LAYERS.get(type_name, type_name)
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    fname = cache / ("anp_wfs_%s_%s.geojson" % (layer.replace(":", "_"), key))
    status = "cache"
    if fname.exists():
        data = json.loads(fname.read_text(encoding="utf-8"))
        retrieved = None
        meta = fname.with_suffix(".log.json")
        if meta.exists():
            retrieved = json.loads(meta.read_text(encoding="utf-8")).get("retrieved_utc")
    else:
        if offline:
            raise FileNotFoundError("offline mode and no cache for %s (%s)" % (layer, fname.name))
        raw = (getter or _default_get)(url, timeout)
        data = json.loads(raw.decode("utf-8"))
        if data.get("type") != "FeatureCollection":
            raise ValueError("ANP WFS did not return a FeatureCollection for %s" % layer)
        fname.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        retrieved = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
        status = "downloaded"
    n = len(data.get("features", []))
    rec = {
        "layer": layer,
        "file": fname.name,
        "url": url,
        "retrieved_utc": retrieved,
        "n_features": n,
        "status": status,
        "truncated": n >= int(max_features),
        "native_crs": "EPSG:4674",
    }
    if status == "downloaded":
        fname.with_suffix(".log.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
    return data, rec


_MOJIBAKE = re.compile("[\u00c3\u00c2][^\x00-\x7f]")


def repair_name(text: Any) -> Any:
    """Repair the encoding damage seen in ANP names and normalise spacing.

    Handles UTF-8 bytes decoded as cp1252/latin-1 (``"SÃ£O"`` to ``"SÃO"``)
    and collapses whitespace. Characters already lost as U+FFFD cannot be
    restored here; use :func:`name_key` to compare such names.

    Args:
        text: A name; non-strings are returned unchanged.

    Returns:
        The repaired name.
    """
    if not isinstance(text, str):
        return text
    s = text
    if _MOJIBAKE.search(s):
        for enc in ("cp1252", "latin-1"):
            try:
                s = s.encode(enc).decode("utf-8")
                break
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
    return re.sub(r"\s+", " ", s).strip()


def name_key(text: Any) -> str:
    """Return an accent- and case-free key for matching ANP names across files.

    ANP files mix correct accents, mojibake and U+FFFD replacement characters for
    the same installation or well. The key drops all non-ASCII letters after
    accent folding, removes bracketed suffixes and punctuation, and upper-cases.

    Args:
        text: A name.

    Returns:
        The match key (empty string for None).
    """
    s = repair_name(text) or ""
    s = re.sub(r"\(.*?\)", " ", str(s))
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if ord(ch) < 128)
    s = re.sub(r"[^A-Za-z0-9]+", " ", s).upper()
    return re.sub(r"\s+", " ", s).strip()


def locate_installations(
    wells_geojson: Mapping,
    well_to_installation: Iterable[tuple[str, str]],
    well_name_key: str = "name",
    lon_key: str = "longitude",
    lat_key: str = "latitude",
    depth_key: str | None = "lamina_dagua",
    aliases: Mapping[str, str] | None = None,
) -> list[dict]:
    """Derive approximate installation positions from producing wellheads.

    Args:
        wells_geojson: ANP well layer (``sisroc:pocos_gishub_db``) as GeoJSON.
        well_to_installation: ``(well_name, installation_name)`` pairs, typically
            from the ANP production-by-well file for a recent period.
        well_name_key: Property holding the well name in the well layer.
        lon_key: Property holding longitude; geometry is used when absent.
        lat_key: Property holding latitude; geometry is used when absent.
        depth_key: Property holding water depth in m, or None.
        aliases: Optional map of :func:`name_key` installation keys to a
            canonical key (ANP spells some installations differently by year).

    Returns:
        One record per installation, sorted by name, with ``lon``, ``lat``,
        ``n_wells_matched``, ``n_wells_reported``, ``well_spread_max_km``,
        ``water_depth_m_median``, ``location_quality`` and ``location_method``.
        Installations with no matched well are listed with ``lon``/``lat`` None.
    """
    pos: dict[str, tuple[float, float, float | None]] = {}
    for f in wells_geojson.get("features", []):
        p = f.get("properties") or {}
        lon, lat = p.get(lon_key), p.get(lat_key)
        if (lon is None or lat is None) and (f.get("geometry") or {}).get("type") == "Point":
            lon, lat = f["geometry"]["coordinates"][:2]
        if lon is None or lat is None:
            continue
        wd = p.get(depth_key) if depth_key else None
        pos[name_key(p.get(well_name_key))] = (float(lon), float(lat), wd)
    aliases = dict(aliases or {})
    reported: dict[str, set] = {}
    display: dict[str, str] = {}
    for well, inst in well_to_installation:
        ik = name_key(inst)
        if not ik:
            continue
        ik = aliases.get(ik, ik)
        display.setdefault(ik, repair_name(inst))
        reported.setdefault(ik, set()).add(name_key(well))
    out = []
    for ik in sorted(reported):
        pts = [pos[w] for w in reported[ik] if w in pos]
        rec = {
            "installation": display[ik],
            "installation_key": ik,
            "n_wells_reported": len(reported[ik]),
            "n_wells_matched": len(pts),
            "lon": None,
            "lat": None,
            "well_spread_max_km": None,
            "water_depth_m_median": None,
            "location_quality": "unlocated",
            "location_method": "no reported well found in the well layer",
        }
        if pts:
            lon = statistics.median(p[0] for p in pts)
            lat = statistics.median(p[1] for p in pts)
            depths = [float(p[2]) for p in pts if p[2] not in (None, "", 0)]
            spread = max(haversine_km(lon, lat, p[0], p[1]) for p in pts)
            rec.update(
                lon=round(lon, 5),
                lat=round(lat, 5),
                well_spread_max_km=round(spread, 1),
                water_depth_m_median=round(statistics.median(depths)) if depths else None,
                location_quality="approximate-derived-from-ANP-wells",
                location_method=(
                    "median of ANP wellhead coordinates of %d producing wells; the hull "
                    "position is not published by ANP, wells spread up to %.1f km" % (len(pts), spread)
                ),
            )
        out.append(rec)
    return out


def installation_production(
    rows: Iterable[Mapping],
    installation_col: str,
    month_col: str,
    oil_m3_cols: Iterable[str] = (),
    gas_mm3_cols: Iterable[str] = (),
    water_m3_cols: Iterable[str] = (),
    aliases: Mapping[str, str] | None = None,
) -> dict[str, dict]:
    """Aggregate monthly production per installation from ANP per-well rows.

    Values must already be numbers (use :func:`anp_open_data.load_table` with
    ``numeric=`` to convert ANP decimal commas). Gas columns are in Mm3
    (thousand m3) as ANP reports them.

    Args:
        rows: Iterable of row mappings.
        installation_col: Column with the installation name.
        month_col: Column with the period (``"MM/YYYY"`` or ``"YYYY-MM"``).
        oil_m3_cols: Columns summed as liquid hydrocarbon in m3 (oil, condensate).
        gas_mm3_cols: Columns summed as gas in thousand m3.
        water_m3_cols: Columns summed as water in m3.
        aliases: Optional installation key aliases, as in :func:`locate_installations`.

    Returns:
        ``{installation_key: {"installation", "latest_month", "months",
        "oil_m3_latest_month", "oil_m3d_latest", "gas_mm3d_latest",
        "water_m3d_latest", "oil_m3d_peak"}}``. Daily rates divide the month total
        by the calendar days of that month.
    """
    import calendar

    aliases = dict(aliases or {})
    acc: dict[str, dict[str, dict[str, float]]] = {}
    disp: dict[str, str] = {}

    def period(v: Any) -> str | None:
        s = str(v or "").strip()
        m = re.match(r"^(\d{1,2})/(\d{4})$", s)
        if m:
            return "%s-%02d" % (m.group(2), int(m.group(1)))
        m = re.match(r"^(\d{4})-(\d{1,2})", s)
        if m:
            return "%s-%02d" % (m.group(1), int(m.group(2)))
        return None

    for r in rows:
        ik = name_key(r.get(installation_col))
        per = period(r.get(month_col))
        if not ik or not per:
            continue
        ik = aliases.get(ik, ik)
        disp.setdefault(ik, repair_name(r.get(installation_col)))
        m = acc.setdefault(ik, {}).setdefault(per, {"oil": 0.0, "gas": 0.0, "water": 0.0})
        m["oil"] += sum(float(r.get(c) or 0.0) for c in oil_m3_cols)
        m["gas"] += sum(float(r.get(c) or 0.0) for c in gas_mm3_cols)
        m["water"] += sum(float(r.get(c) or 0.0) for c in water_m3_cols)
    out = {}
    for ik, months in acc.items():

        def days(p: str) -> int:
            y, mo = int(p[:4]), int(p[5:7])
            return calendar.monthrange(y, mo)[1]

        latest = max(months)
        d = days(latest)
        out[ik] = {
            "installation": disp[ik],
            "latest_month": latest,
            "months": len(months),
            "oil_m3_latest_month": round(months[latest]["oil"], 1),
            "oil_m3d_latest": round(months[latest]["oil"] / d, 1),
            "gas_mm3d_latest": round(months[latest]["gas"] / d, 2),
            "water_m3d_latest": round(months[latest]["water"] / d, 1),
            "oil_m3d_peak": round(max(v["oil"] / days(p) for p, v in months.items()), 1),
        }
    return out
