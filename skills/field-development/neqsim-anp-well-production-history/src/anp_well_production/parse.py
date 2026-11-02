"""Read ANP well-production files into typed, unit-explicit records.

Four ANP file families are recognised by their header (see ``catalog.FAMILIES``).
Every family is mapped onto one record layout so that downstream code never
depends on a Portuguese header. A header that is missing or renamed raises a
``KeyError`` that names the field, instead of returning a silent wrong number.

Unit conventions of the record layout:

* liquid rates in m3/d, gas rates in thousand m3/d (ANP writes this "Mm3"),
  water in m3/d;
* a monthly volume is converted to a rate by dividing by the calendar days of
  the month, which is the ANP definition (verified against the by-well rate and
  volume files for the same month);
* gas composition values are percent by volume, which equals mole percent for
  an ideal gas.
"""

from __future__ import annotations

import calendar
import csv
import io
import re
import unicodedata
import zipfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

BBL_TO_M3 = 0.158987294928
"""Cubic metres per barrel (exact)."""

RATE_FIELDS = (
    "oil_m3d",
    "condensate_m3d",
    "liquid_m3d",
    "gas_assoc_km3d",
    "gas_nonassoc_km3d",
    "gas_total_km3d",
    "water_m3d",
)
"""Production fields that are summed when records are aggregated."""

GAS_COMPOSITION_KEYS = (
    "methane",
    "ethane",
    "propane",
    "iso_butane",
    "butane",
    "iso_pentane",
    "n_pentane",
    "hexanes",
    "heptanes",
    "octanes",
    "nonanes",
    "decanes",
    "undecanes",
    "oxygen",
    "nitrogen",
    "carbon_dioxide",
)


def fold(text: Any) -> str:
    """Fold a header or name to lower-case ASCII words.

    Args:
        text: Any value; ``None`` gives an empty string.

    Returns:
        Lower-case text without accents, brackets, unit punctuation or the
        U+FFFD replacement character, words separated by one space.
    """
    if text is None:
        return ""
    s = str(text).replace("\ufffd", "").replace("³", "").replace("²", "")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^0-9a-zA-Z]+", " ", s.lower())
    return s.strip()


def parse_number(text: Any) -> Optional[float]:
    """Parse a Brazilian-formatted number.

    Accepts ``"4841,6358"``, ``",878"`` (no leading zero), ``"3.127,441"`` (dot
    thousands) and ``"1.234.567"`` (dots only, grouped in threes: thousands).
    Empty text, ``"-"`` and text that is not a number give ``None``.

    Args:
        text: Cell text or a number.

    Returns:
        The value, or ``None`` when the cell is empty or not numeric.
    """
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    s = str(text).strip().replace("\u00a0", "").replace(" ", "")
    if s in ("", "-", "--"):
        return None
    s = s.rstrip("%")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def parse_period(text: Any) -> Tuple[int, int]:
    """Parse a reporting period into ``(year, month)``.

    Accepts ``"2023/12"`` and ``"2023-12"`` (by-well rate files), ``"01/2026"``
    (volume files) and ``"01/08/2026"`` or ``"2026-08-01"`` (zone files).

    Args:
        text: Period text.

    Returns:
        ``(year, month)``.

    Raises:
        ValueError: The text is not a recognised period.
    """
    s = str(text).strip()
    m = re.fullmatch(r"(\d{4})[/-](\d{1,2})(?:[/-]\d{1,2})?", s)
    if m:
        year, month = int(m.group(1)), int(m.group(2))
    else:
        m = re.fullmatch(r"(?:\d{1,2}/)?(\d{1,2})/(\d{4})", s)
        if not m:
            raise ValueError("Unrecognised ANP period: %r" % text)
        month, year = int(m.group(1)), int(m.group(2))
    if not 1 <= month <= 12:
        raise ValueError("Month out of range in period %r" % text)
    return year, month


def days_in_month(year: int, month: int) -> int:
    """Return the calendar days of a month.

    Args:
        year: Four-digit year.
        month: Month number, 1 to 12.

    Returns:
        Number of days.
    """
    return calendar.monthrange(year, month)[1]


def decode_bytes(raw: bytes) -> Tuple[str, str]:
    """Decode ANP file bytes line by line, UTF-8 first and Windows-1252 otherwise.

    Some ANP files mix encodings: a Windows-1252 header above UTF-8 data rows,
    with an occasional row cut inside a multi-byte character. Decoding each line
    on its own keeps every valid line intact.

    Args:
        raw: File content.

    Returns:
        ``(text, encoding)`` where encoding is ``utf-8``, ``cp1252`` or ``mixed``.
    """
    try:
        return raw.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        pass
    lines, kinds = [], set()
    for chunk in raw.split(b"\n"):
        try:
            lines.append(chunk.decode("utf-8"))
            kinds.add("utf-8" if any(b > 127 for b in chunk) else "ascii")
        except UnicodeDecodeError:
            lines.append(chunk.decode("cp1252", errors="replace"))
            kinds.add("cp1252")
    kinds.discard("ascii")
    encoding = kinds.pop() if len(kinds) == 1 else ("mixed" if kinds else "utf-8")
    return "\n".join(lines).lstrip("\ufeff"), encoding


def read_table_bytes(raw: bytes) -> Tuple[List[str], List[List[str]], Dict[str, Any]]:
    """Read delimited ANP bytes into a header, rows and a meta record.

    The delimiter (semicolon or comma) is taken from the header line.

    Args:
        raw: File content.

    Returns:
        ``(headers, rows, meta)``; ``meta`` holds ``encoding``, ``delimiter`` and
        ``n_rows``. Headers keep their original text.

    Raises:
        ValueError: The file is empty.
    """
    text, encoding = decode_bytes(raw)
    lines = text.splitlines()
    if not lines or not lines[0].strip():
        raise ValueError("Empty ANP file")
    delimiter = ";" if lines[0].count(";") > lines[0].count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    headers = [h.strip() for h in next(reader)]
    rows = [r for r in reader if any(c.strip() for c in r)]
    meta = {"encoding": encoding, "delimiter": delimiter, "n_rows": len(rows)}
    return headers, rows, meta


def read_table(path: str | Path) -> Tuple[List[str], List[List[str]], Dict[str, Any]]:
    """Read a delimited ANP file from disk.

    Args:
        path: CSV file path.

    Returns:
        See :func:`read_table_bytes`.
    """
    return read_table_bytes(Path(path).read_bytes())


def read_zip(path: str | Path) -> Dict[str, bytes]:
    """Return the CSV members of an ANP zip as ``{member name: bytes}``.

    Args:
        path: Zip file path.

    Returns:
        Mapping of member name to content for every ``.csv`` member.
    """
    out: Dict[str, bytes] = {}
    with zipfile.ZipFile(path) as zf:
        for name in zf.namelist():
            if name.lower().endswith(".csv"):
                out[name] = zf.read(name)
    return out


def _aliases(*names: str) -> Tuple[str, ...]:
    return tuple(fold(n) for n in names)


# Canonical field -> accepted folded header names. The spellings without the
# accented letter cover headers whose characters were lost (U+FFFD removed).
_COMMON = {
    "well": _aliases("Nome Poço ANP", "Nome Poo ANP", "Poço", "Poo"),
    "field": _aliases("Campo"),
    "basin": _aliases("Bacia"),
    "state": _aliases("Estado"),
    "environment": _aliases("Ambiente"),
    "operator": _aliases("Operador"),
    "installation": _aliases("Instalação Destino", "Instalação", "Instalao Destino", "Instalao"),
}

SCHEMAS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "well_monthly_rates": dict(
        _COMMON,
        period=_aliases("Período", "Perodo"),
        contract=_aliases("Número do Contrato", "Nmero do Contrato"),
        oil_bbld=_aliases("Óleo (bbl/dia)", "leo bbl dia"),
        condensate_bbld=_aliases("Condensado (bbl/dia)"),
        liquid_bbld=_aliases("Petróleo (bbl/dia)", "Petrleo bbl dia"),
        gas_assoc_km3d=_aliases("Gás Natural (Mm³/dia) Assoc", "Gs Natural Mm dia Assoc"),
        gas_nonassoc_km3d=_aliases("Gás Natural (Mm³/dia) N Assoc", "Gs Natural Mm dia N Assoc"),
        gas_total_km3d=_aliases("Gás Natural (Mm³/dia) Total", "Gs Natural Mm dia Total"),
        water_bbld=_aliases("Água (bbl/dia)", "gua bbl dia"),
        hours_on=_aliases("Tempo de Produção (hs por mês)", "Tempo de Produo hs por ms"),
        api=_aliases("Grau API"),
        analysis_period=_aliases("Período da Carga", "Perodo da Carga"),
        installation_type=_aliases("Tipo Instalação", "Tipo Instalao"),
        gcv_kj_m3=_aliases("PCS GP(kJ/m³)", "PCS GP kJ m"),
    ),
    "well_monthly_volumes": dict(
        _COMMON,
        period=_aliases("Mês/Ano", "Ms/Ano"),
        oil_m3=_aliases("Produção de Óleo (m³)", "Produo de leo m"),
        condensate_m3=_aliases("Produção de Condensado (m³)", "Produo de Condensado m"),
        gas_assoc_km3=_aliases("Produção de Gás Associado (Mm³)", "Produo de Gs Associado Mm"),
        gas_nonassoc_km3=_aliases("Produção de Gás Não Associado (Mm³)", "Produo de Gs No Associado Mm"),
        water_m3=_aliases("Produção de Água (m³)", "Produo de gua m"),
        gas_inj_km3=_aliases("Injeção de Gás (Mm³)", "Injeo de Gs Mm"),
        water_inj_secondary_m3=_aliases(
            "Injeção de Água para Recuperação Secundária (m³)", "Injeo de gua para Recuperao Secundria m"
        ),
        water_inj_disposal_m3=_aliases("Injeção de Água para Descarte (m³)", "Injeo de gua para Descarte m"),
        co2_inj_km3=_aliases("Injeção de Gás Carbônico (Mm³)", "Injeo de Gs Carbnico Mm"),
    ),
    "zone_daily_rates": dict(
        _COMMON,
        zone=_aliases("Zona"),
        period=_aliases("Data"),
        oil_m3d=_aliases("Óleo (m³/d)", "leo m d"),
        condensate_m3d=_aliases("Condensado (m³/d)"),
        liquid_m3d=_aliases("Petróleo (m³/d)", "Petrleo m d"),
        gas_assoc_km3d=_aliases("Gás associado (Mil m³/d)", "Gs associado Mil m d"),
        gas_nonassoc_km3d=_aliases("Gás não associado (Mil m³/d)", "Gs no associado Mil m d"),
        gas_total_km3d=_aliases("Gás total (Mil m³/d)", "Gs total Mil m d"),
        water_m3d=_aliases("Água (m³/d)", "gua m d"),
        water_inj_disposal_m3d=_aliases("Água injetada para descarte (m³/d)", "gua injetada para descarte m d"),
        water_inj_secondary_m3d=_aliases(
            "Água injetada para rec. secundária (m³/d)", "gua injetada para rec secundria m d"
        ),
        gas_inj_km3d=_aliases("Gás injetado (Mil m³/d)", "Gs injetado Mil m d"),
    ),
    "well_status": {
        "well": _aliases("Nome_poço_anp", "Nome_poo_anp"),
        "field": _aliases("Campo"),
        "basin": _aliases("Bacia"),
        "operator": _aliases("Operador_atual"),
        "state": _aliases("Estado"),
        "environment": _aliases("Ambiente"),
        "spud_date": _aliases("Data_início_perfuração", "Data_incio_perfurao"),
        "completion_date": _aliases("Data_conclusão_poço", "Data_concluso_poo"),
        "first_production": _aliases("Data_início_produção_(mês/ano)", "Data_incio_produo_ms_ano"),
        "last_production": _aliases("Data_última_produçaõ_(mês/ano)", "Data_ltima_produao_ms_ano"),
        "in_operation": _aliases("Em_operação_(produção_ou_injeção)", "Em_operao_produo_ou_injeo"),
        "latitude": _aliases("Latitude_da_base"),
        "longitude": _aliases("Longitude_da_base"),
        "status": _aliases("Situação_do_poço", "Situao_do_poo"),
        "lift_method": _aliases("Método_de_elevação", "Mtodo_de_elevao"),
    },
}
"""Accepted folded header spellings per canonical field and file family."""

_REQUIRED = {
    "well_monthly_rates": ("well", "period", "liquid_bbld", "gas_total_km3d"),
    "well_monthly_volumes": ("well", "period", "oil_m3", "gas_assoc_km3"),
    "zone_daily_rates": ("well", "period", "zone", "liquid_m3d"),
    "well_status": ("well", "status"),
}

_COMPOSITION_HEADERS = {
    "methane": "metano",
    "ethane": "etano",
    "propane": "propano",
    "iso_butane": "iso butano",
    "butane": "butano",
    "iso_pentane": "iso pentano",
    "n_pentane": "n pentano",
    "hexanes": "hexanos",
    "heptanes": "heptanos",
    "octanes": "octanos",
    "nonanes": "nonanos",
    "decanes": "decanos",
    "undecanes": "undecanos",
    "oxygen": "oxigenio",
    "nitrogen": "nitrogenio",
    "carbon_dioxide": "gas carbonico",
}


def detect_schema(headers: Sequence[str]) -> str:
    """Name the ANP file family from its header.

    Args:
        headers: Header cells as read.

    Returns:
        One of ``well_monthly_rates``, ``well_monthly_volumes``,
        ``zone_daily_rates`` or ``well_status``.

    Raises:
        ValueError: No family matches; the message lists some folded headers.
    """
    folded = {fold(h) for h in headers}
    for family in ("zone_daily_rates", "well_monthly_volumes", "well_monthly_rates", "well_status"):
        spec = SCHEMAS[family]
        if all(any(a in folded for a in spec[k]) for k in _REQUIRED[family]):
            return family
    raise ValueError("Header matches no known ANP family: %s" % sorted(folded)[:12])


def _column_index(headers: Sequence[str], spec: Mapping[str, Tuple[str, ...]]) -> Dict[str, int]:
    folded = [fold(h) for h in headers]
    idx: Dict[str, int] = {}
    for key, names in spec.items():
        for i, h in enumerate(folded):
            if h in names:
                idx[key] = i
                break
    return idx


def _composition_index(headers: Sequence[str]) -> Dict[str, int]:
    idx: Dict[str, int] = {}
    for i, h in enumerate(headers):
        f = fold(h)
        if not f.startswith("em volumes"):
            continue
        tail = f[len("em volumes"):].strip()
        for key, name in _COMPOSITION_HEADERS.items():
            if tail == name:
                idx[key] = i
    return idx


def _cell(row: Sequence[str], idx: Mapping[str, int], key: str) -> Optional[str]:
    i = idx.get(key)
    if i is None or i >= len(row):
        return None
    v = row[i].strip()
    return v if v != "" else None


def _num(row: Sequence[str], idx: Mapping[str, int], key: str) -> Optional[float]:
    return parse_number(_cell(row, idx, key))


def _scale(value: Optional[float], factor: float) -> Optional[float]:
    return None if value is None else value * factor


def normalize(
    headers: Sequence[str],
    rows: Iterable[Sequence[str]],
    family: Optional[str] = None,
    source: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Convert raw rows of one ANP family to the common record layout.

    Production records carry ``well``, ``field``, ``basin``, ``state``,
    ``environment``, ``operator``, ``installation``, ``year``, ``month``,
    ``period`` (``YYYY-MM``), ``days``, ``oil_m3d``, ``condensate_m3d``,
    ``liquid_m3d`` (oil plus condensate), ``gas_assoc_km3d``,
    ``gas_nonassoc_km3d``, ``gas_total_km3d`` and ``water_m3d``. Optional keys
    appear where the family has them: ``hours_on``, ``api``,
    ``analysis_period``, ``gas_composition_pct``, ``zone`` and injection rates.
    Missing numbers stay ``None``; they are never turned into zero.

    Args:
        headers: Header cells.
        rows: Data rows.
        family: Family name; detected from the header when omitted.
        source: Optional label (file name) copied to each record as ``source``.

    Returns:
        List of record dicts. For ``well_status`` the list holds status records
        with the well identity, dates, status, lift method and coordinates.

    Raises:
        KeyError: A required header of the family is missing.
        ValueError: The family cannot be detected or a period cannot be parsed.
    """
    family = family or detect_schema(headers)
    spec = SCHEMAS[family]
    idx = _column_index(headers, spec)
    missing = [k for k in _REQUIRED[family] if k not in idx]
    if missing:
        raise KeyError("ANP %s file lacks required column(s): %s" % (family, ", ".join(missing)))
    comp_idx = _composition_index(headers) if family == "well_monthly_rates" else {}
    out: List[Dict[str, Any]] = []
    for row in rows:
        rec: Dict[str, Any] = {"family": family}
        if source:
            rec["source"] = source
        for key in ("well", "field", "basin", "state", "environment", "operator", "installation"):
            rec[key] = _cell(row, idx, key)
        if family == "well_status":
            for key in (
                "spud_date",
                "completion_date",
                "first_production",
                "last_production",
                "in_operation",
                "status",
                "lift_method",
            ):
                rec[key] = _cell(row, idx, key)
            rec["latitude_dms"] = _cell(row, idx, "latitude")
            rec["longitude_dms"] = _cell(row, idx, "longitude")
            out.append(rec)
            continue
        year, month = parse_period(_cell(row, idx, "period"))
        days = days_in_month(year, month)
        rec.update({"year": year, "month": month, "period": "%04d-%02d" % (year, month), "days": days})
        if family == "well_monthly_rates":
            oil = _scale(_num(row, idx, "oil_bbld"), BBL_TO_M3)
            cond = _scale(_num(row, idx, "condensate_bbld"), BBL_TO_M3)
            liquid = _scale(_num(row, idx, "liquid_bbld"), BBL_TO_M3)
            if liquid is None and oil is not None:
                liquid = oil + (cond or 0.0)
            rec.update(
                oil_m3d=oil,
                condensate_m3d=cond,
                liquid_m3d=liquid,
                gas_assoc_km3d=_num(row, idx, "gas_assoc_km3d"),
                gas_nonassoc_km3d=_num(row, idx, "gas_nonassoc_km3d"),
                gas_total_km3d=_num(row, idx, "gas_total_km3d"),
                water_m3d=_scale(_num(row, idx, "water_bbld"), BBL_TO_M3),
                hours_on=_num(row, idx, "hours_on"),
                api=_num(row, idx, "api"),
                analysis_period=_cell(row, idx, "analysis_period"),
                installation_type=_cell(row, idx, "installation_type"),
                gcv_kj_m3=_num(row, idx, "gcv_kj_m3"),
                contract=_cell(row, idx, "contract"),
            )
            comp = {}
            for key, i in comp_idx.items():
                v = parse_number(row[i]) if i < len(row) else None
                if v is not None:
                    comp[key] = v
            rec["gas_composition_pct"] = comp or None
        elif family == "well_monthly_volumes":
            oil = _num(row, idx, "oil_m3")
            cond = _num(row, idx, "condensate_m3")
            ga = _num(row, idx, "gas_assoc_km3")
            gn = _num(row, idx, "gas_nonassoc_km3")
            wat = _num(row, idx, "water_m3")
            liquid = None if oil is None else oil + (cond or 0.0)
            gas = None if ga is None and gn is None else (ga or 0.0) + (gn or 0.0)
            per_day = 1.0 / days
            rec.update(
                oil_m3d=_scale(oil, per_day),
                condensate_m3d=_scale(cond, per_day),
                liquid_m3d=_scale(liquid, per_day),
                gas_assoc_km3d=_scale(ga, per_day),
                gas_nonassoc_km3d=_scale(gn, per_day),
                gas_total_km3d=_scale(gas, per_day),
                water_m3d=_scale(wat, per_day),
                gas_inj_km3d=_scale(_num(row, idx, "gas_inj_km3"), per_day),
                water_inj_secondary_m3d=_scale(_num(row, idx, "water_inj_secondary_m3"), per_day),
                water_inj_disposal_m3d=_scale(_num(row, idx, "water_inj_disposal_m3"), per_day),
                co2_inj_km3d=_scale(_num(row, idx, "co2_inj_km3"), per_day),
                hours_on=None,
                api=None,
            )
        else:
            rec.update(
                zone=_cell(row, idx, "zone"),
                oil_m3d=_num(row, idx, "oil_m3d"),
                condensate_m3d=_num(row, idx, "condensate_m3d"),
                liquid_m3d=_num(row, idx, "liquid_m3d"),
                gas_assoc_km3d=_num(row, idx, "gas_assoc_km3d"),
                gas_nonassoc_km3d=_num(row, idx, "gas_nonassoc_km3d"),
                gas_total_km3d=_num(row, idx, "gas_total_km3d"),
                water_m3d=_num(row, idx, "water_m3d"),
                water_inj_disposal_m3d=_num(row, idx, "water_inj_disposal_m3d"),
                water_inj_secondary_m3d=_num(row, idx, "water_inj_secondary_m3d"),
                gas_inj_km3d=_num(row, idx, "gas_inj_km3d"),
                hours_on=None,
                api=None,
            )
        out.append(rec)
    return out


def load_records(
    path: str | Path,
    family: Optional[str] = None,
    environment: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Read one ANP CSV and return normalised records.

    Args:
        path: CSV path.
        family: Family name, detected from the header when omitted.
        environment: Label stored as ``environment`` when the file has no such
            value (for example ``"MAR"``, ``"TERRA"``, ``"PRESAL"``).

    Returns:
        Records as returned by :func:`normalize`.
    """
    headers, rows, _ = read_table(path)
    recs = normalize(headers, rows, family=family, source=Path(path).name)
    if environment:
        for r in recs:
            if not r.get("environment"):
                r["environment"] = environment
    return recs
