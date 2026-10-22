"""Ready-made sketches for an oil export line: source platform end and landing host end."""

from __future__ import annotations

from typing import Dict, List, Optional

from .elements import Element, TieInEndSketch


def source_end_oil_export(
    source: str,
    landing: str,
    existing_equipment_label: str = "Eksisterende\neksportpumpe /\nveske til FSO",
    existing_tag: str = "",
    new_export_pump: bool = True,
    keep_old_route: bool = True,
    line_label: str = "",
) -> TieInEndSketch:
    """Source end: existing liquid system, new pump, metering, pig launcher, ESDV and riser.

    Args:
        source: source platform name.
        landing: landing host name, used in labels.
        existing_equipment_label: label of the existing equipment the new line is tied to.
        existing_tag: existing tag read from the controlled P&ID, or empty to leave it blank.
        new_export_pump: include a new export pump (needed when the existing discharge pressure is too low).
        keep_old_route: keep a block valve and blind towards the old route (FSO/tanker) so it can be isolated.
        line_label: text at the end of the line.

    Returns:
        A :class:`TieInEndSketch`.
    """
    els: List[Element] = [Element("equipment", existing_tag, existing_equipment_label, existing=True, proposed=False)]
    if keep_old_route:
        els.append(Element("spec_break", "SB-01", "Skillt mot\ngammel rute\n(FSO/tanker)"))
    if new_export_pump:
        els.append(Element("pump", "PA-01", "Ny eksportpumpe\n(trykk fra\nhydraulikk)"))
    els += [
        Element("control_valve", "FCV-01", "Mengde-/\ntrykkregulering"),
        Element("flow_meter", "FT-01", "Allokerings-\nmåling"),
        Element("transmitter", "PT-01", "Trykk/temp.\nlokalt", measure="P"),
        Element("check_valve", "NRV-01", "Tilbakeslag"),
        Element("pig_launcher", "PL-01", "Pigg-\nutskyter"),
        Element("esdv", "XV-01", "ESDV\n(plattformgrense)"),
        Element("riser", "RS-01", "Stigerør\nmed klamme"),
        Element("tie_in", "TI-A", f"Tie-in A\n{source}"),
    ]
    return TieInEndSketch(
        title=f"{source} – kilde-ende av oljeeksport mot {landing}",
        subtitle="Konseptuell P&ID, hovedlinje fra venstre mot høyre",
        side="source",
        elements=els,
        line_label=line_label or f"→ {landing}",
        options=[
            "A1 Tie-in nedstrøms eksisterende eksportpumpe, hvis utløpstrykket dekker trykkbehovet.",
            "A2 Ny eksportpumpe (vist), hvis trykkbehovet er høyere enn eksisterende pumpe leverer.",
            "A3 Ny stigerørsslot/J-rør må bekreftes ledig på jacket og dekk.",
        ],
        notes=[
            "Vann og stabilisering må ivaretas oppstrøms; skissen forutsetter tørr, stabilisert olje.",
            "Pigging, injeksjonspunkt for kjemikalier og trykkavlastning må dimensjoneres i detaljfase.",
        ],
    )


def landing_end_oil_header(
    landing: str,
    source: str,
    header_label: str = "Eksisterende\neksportheader\n(OTS-start)",
    header_tag: str = "",
    with_booster: bool = False,
    line_label: str = "",
) -> TieInEndSketch:
    """Landing end: riser, ESDV, pig receiver, pressure control and tie-in to an existing export header.

    Args:
        landing: landing host name.
        source: source platform name.
        header_label: label of the existing header the new line joins.
        header_tag: existing tag read from the controlled P&ID, or empty.
        with_booster: add a booster pump between the receiver and the header (needed if the header pressure
            exceeds the arrival pressure).
        line_label: text at the start of the line.

    Returns:
        A :class:`TieInEndSketch`.
    """
    els: List[Element] = [
        Element("tie_in", "TI-B", f"Tie-in B\n{landing}"),
        Element("riser", "RS-02", "Stigerør"),
        Element("esdv", "XV-02", "ESDV\n(plattformgrense)"),
        Element("pig_receiver", "PR-01", "Pigg-\nmottaker"),
        Element("check_valve", "NRV-02", "Tilbakeslag"),
        Element("transmitter", "PT-02", "Trykk/temp.", measure="P"),
        Element("sampler", "AS-01", "Oljeprøve\n(BS&W, TVP)"),
    ]
    if with_booster:
        els.append(Element("pump", "PA-02", "Boosterpumpe"))
    els += [
        Element("control_valve", "PCV-02", "Mottrykks-\nregulering"),
        Element("spec_break", "SB-02", "Spektakel-\nblind"),
        Element("equipment", header_tag, header_label, existing=True, proposed=False),
    ]
    return TieInEndSketch(
        title=f"{landing} – landing-ende fra {source}",
        subtitle="Konseptuell P&ID, hovedlinje fra venstre mot høyre",
        side="landing",
        elements=els,
        line_label=line_label or f"fra {source} →",
        options=[
            "B1 Oseberg feltsenter (anbefalt): innløp til eksisterende OTS-header etter målestasjon.",
            "B2 Oseberg Sør: via eksisterende rør til feltsenteret.",
            "B3 Oseberg C: via nytt eller eksisterende rør til feltsenteret.",
            "B4 Ankomsttrykk, oljekvalitet (BS&W, TVP, voks) og målekrav må avtales med OTS-eier.",
        ],
        notes=[
            "Tie-in krever ledig kapasitet i header, ledig stigerørsslot og kvalitetsgodkjenning for Sture.",
            "Allokering: separat måler eller bevisst mengdefordeling mot øvrige OTS-leverandører.",
        ],
    )


def pair_sketch(source: str, landing: str) -> Dict[str, TieInEndSketch]:
    """Both ends with consistent names."""
    return {"source": source_end_oil_export(source, landing), "landing": landing_end_oil_header(landing, source)}
