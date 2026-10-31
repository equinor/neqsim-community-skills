"""Word report builder for a well design study (python-docx). Content is supplied as sections; numbering is automatic."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.section import WD_ORIENT, WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor


STATUS_COLOURS = {
    "[VERIFIED]": RGBColor(0x1B, 0x7F, 0x3B),
    "[UNVERIFIED-SOURCE]": RGBColor(0xB3, 0x6B, 0x00),
    "[DERIVED]": RGBColor(0x1F, 0x4E, 0x9E),
    "[ASSUMED]": RGBColor(0xB0, 0x2A, 0x2A),
    "[PLACEHOLDER]": RGBColor(0x66, 0x66, 0x66),
    "[NEEDS_REVIEW]": RGBColor(0xB0, 0x2A, 0x2A),
}


def _field(par, code: str, placeholder: str = "1", size: Optional[float] = None) -> None:
    r = par.add_run()
    if size:
        r.font.size = Pt(size)
    for kind, txt in (("begin", None), ("instr", code), ("separate", None), ("text", placeholder), ("end", None)):
        if kind in ("begin", "separate", "end"):
            e = OxmlElement("w:fldChar")
            e.set(qn("w:fldCharType"), kind)
        elif kind == "instr":
            e = OxmlElement("w:instrText")
            e.set(qn("xml:space"), "preserve")
            e.text = txt
        else:
            e = OxmlElement("w:t")
            e.text = txt
        r._r.append(e)


class WellReport:
    """Collects headings, paragraphs, tables and figures and writes a Word document with contents and page numbers."""

    def __init__(self, title: str, subtitle: str, doc_id: str, status: str) -> None:
        self.doc = Document()
        st = self.doc.styles["Normal"]
        st.font.name = "Calibri"
        st.font.size = Pt(10)
        sec = self.doc.sections[0]
        sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
        for a in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
            setattr(sec, a, Cm(1.9))
        p = sec.footer.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(f"{doc_id} - {status} - page ")
        r.font.size = Pt(8)
        _field(p, "PAGE")
        self.ch = self.h2 = 0
        self.app_n = 0
        self.usable_cm = 17.2
        self.fig_n = 0
        self.tab_n = 0
        self.figures: List[Dict[str, str]] = []
        for _ in range(5):
            self.doc.add_paragraph()
        t = self.doc.add_paragraph()
        t.alignment = WD_ALIGN_PARAGRAPH.CENTER
        rr = t.add_run(title)
        rr.bold = True
        rr.font.size = Pt(26)
        t = self.doc.add_paragraph()
        t.alignment = WD_ALIGN_PARAGRAPH.CENTER
        t.add_run(subtitle).font.size = Pt(13)
        for line in (doc_id, status):
            q = self.doc.add_paragraph()
            q.alignment = WD_ALIGN_PARAGRAPH.CENTER
            q.add_run(line).font.size = Pt(11)
        self.doc.add_page_break()
        cp = self.doc.add_paragraph()
        cr = cp.add_run("Contents")
        cr.bold = True
        cr.font.size = Pt(16)
        tp = self.doc.add_paragraph()
        _field(tp, 'TOC \\o "1-2" \\h \\z \\u', "Update the field to build the table of contents.")
        self.doc.add_page_break()

    def _runs(self, par, text: str, size: Optional[float] = None) -> None:
        for part in re.split(r"(\*\*[^*]+\*\*|`[^`]+`|\[(?:VERIFIED|UNVERIFIED-SOURCE|DERIVED|ASSUMED|PLACEHOLDER|NEEDS_REVIEW)\])", text):
            if not part:
                continue
            if part.startswith("**") and part.endswith("**") and len(part) > 4:
                r = par.add_run(part[2:-2])
                r.bold = True
            elif part in STATUS_COLOURS:
                r = par.add_run(part)
                r.bold = True
                r.font.color.rgb = STATUS_COLOURS[part]
            elif part.startswith("`") and part.endswith("`") and len(part) > 2:
                r = par.add_run(part[1:-1])
                r.font.name = "Consolas"
            else:
                r = par.add_run(part)
            if size:
                r.font.size = Pt(size)

    def h1(self, text: str, page_break: bool = True) -> None:
        self.ch += 1
        self.h2 = 0
        if page_break and self.ch > 1:
            self.doc.add_page_break()
        self.doc.add_heading(f"{self.ch} {text}", 1)

    def h2_(self, text: str) -> None:
        self.h2 += 1
        self.doc.add_heading(f"{self.ch}.{self.h2} {text}", 2)

    def appendix(self, text: str, page_break: bool = True) -> None:
        """Start an appendix (A, B, ...) as a level-1 heading so that it appears in the contents."""
        self.app_n += 1
        if page_break:
            self.doc.add_page_break()
        self.doc.add_heading(f"Appendix {chr(64 + self.app_n)} {text}", 1)

    def landscape(self) -> None:
        """Start a new landscape section (wide tables); table widths adapt to the usable width."""
        sec = self.doc.add_section(WD_SECTION.NEW_PAGE)
        sec.orientation = WD_ORIENT.LANDSCAPE
        sec.page_width, sec.page_height = Cm(29.7), Cm(21.0)
        self.usable_cm = 25.9

    def portrait(self) -> None:
        """Return to a portrait section."""
        sec = self.doc.add_section(WD_SECTION.NEW_PAGE)
        sec.orientation = WD_ORIENT.PORTRAIT
        sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
        self.usable_cm = 17.2

    def callout(self, title: str, lines: Sequence[str], fill: str = "EAF1FB", size: float = 9.5) -> None:
        """Shaded single-cell box (answer-first summary, key warnings). Lines support the same inline markup as paragraphs."""
        t = self.doc.add_table(rows=1, cols=1)
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        cell = t.rows[0].cells[0]
        cell.width = Cm(self.usable_cm)
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:fill"), fill)
        cell._tc.get_or_add_tcPr().append(shd)
        p = cell.paragraphs[0]
        r = p.add_run(title)
        r.bold = True
        r.font.size = Pt(size + 1)
        for ln in lines:
            q = cell.add_paragraph()
            q.paragraph_format.space_after = Pt(2)
            self._runs(q, ln, size)
        self.doc.add_paragraph().paragraph_format.space_after = Pt(2)

    def para(self, text: str, size: Optional[float] = None) -> None:
        p = self.doc.add_paragraph()
        p.paragraph_format.space_after = Pt(4)
        self._runs(p, text, size)

    def bullets(self, items: Sequence[str], size: Optional[float] = None) -> None:
        for it in items:
            p = self.doc.add_paragraph(style="List Bullet")
            p.paragraph_format.space_after = Pt(2)
            self._runs(p, it, size)

    def numbered(self, items: Sequence[str]) -> None:
        for i, it in enumerate(items, 1):
            p = self.doc.add_paragraph()
            p.paragraph_format.left_indent = Cm(0.8)
            p.paragraph_format.first_line_indent = Cm(-0.6)
            p.add_run(f"{i}. ")
            self._runs(p, it)

    def table(self, rows: Sequence[Sequence[object]], caption: Optional[str] = None, font: float = 8.0, widths: Optional[Sequence[float]] = None) -> None:
        rows = [[("" if c is None else str(c)) for c in r] for r in rows]
        ncol = max(len(r) for r in rows)
        rows = [r + [""] * (ncol - len(r)) for r in rows]
        if caption:
            self.tab_n += 1
            cp = self.doc.add_paragraph()
            cp.paragraph_format.keep_with_next = True
            rr = cp.add_run(f"Table {self.tab_n}. {caption}")
            rr.bold = True
            rr.font.size = Pt(9)
        t = self.doc.add_table(rows=len(rows), cols=ncol)
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        usable = self.usable_cm
        if widths is None:
            lens = [min(max(max(len(r[c]) for r in rows), 6), 60) ** 0.8 for c in range(ncol)]
            tot = sum(lens)
            widths = [usable * x / tot for x in lens]
        for i, row in enumerate(rows):
            tr = t.rows[i]
            trpr = tr._tr.get_or_add_trPr()
            trpr.append(OxmlElement("w:cantSplit"))
            if i == 0:
                trpr.append(OxmlElement("w:tblHeader"))
            for j, txt in enumerate(row):
                cell = tr.cells[j]
                cell.width = Cm(widths[j])
                par = cell.paragraphs[0]
                par.paragraph_format.space_after = Pt(0)
                self._runs(par, txt, font)
                if i == 0:
                    for r in par.runs:
                        r.bold = True
                    shd = OxmlElement("w:shd")
                    shd.set(qn("w:val"), "clear")
                    shd.set(qn("w:fill"), "D9E2F3")
                    cell._tc.get_or_add_tcPr().append(shd)
        self.doc.add_paragraph().paragraph_format.space_after = Pt(2)

    def figure(self, path: Path, caption: str, provenance: str = "", width_cm: float = 15.5) -> None:
        self.fig_n += 1
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.keep_with_next = True
        p.add_run().add_picture(str(path), width=Cm(width_cm))
        c = self.doc.add_paragraph()
        c.alignment = WD_ALIGN_PARAGRAPH.CENTER
        c.paragraph_format.space_after = Pt(1)
        r = c.add_run(f"Figure {self.fig_n}. {caption}")
        r.bold = True
        r.font.size = Pt(9)
        if provenance:
            q = self.doc.add_paragraph()
            q.alignment = WD_ALIGN_PARAGRAPH.CENTER
            rr = q.add_run(provenance)
            rr.italic = True
            rr.font.size = Pt(7)
            rr.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
        self.figures.append({"n": str(self.fig_n), "file": Path(path).name, "caption": caption})

    def save(self, path: Path) -> Path:
        path = Path(path)
        self.doc.save(path)
        return path


_NUM_RE = re.compile(r"^[<>~=\u2248\u00b1+\-]?\s*\d[\d\s.,/]*\s*(%|[a-zA-Z/\u00b0]{0,5})?$")


def _is_numeric_cell(txt: str) -> bool:
    t = txt.strip()
    return bool(t) and bool(_NUM_RE.match(t)) and len(t) <= 16


def _shade(cell, fill: str) -> None:
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:fill"), fill)
    cell._tc.get_or_add_tcPr().append(shd)


def _cell_margins(table, top: int = 30, bottom: int = 30, left: int = 70, right: int = 70) -> None:
    pr = table._tbl.tblPr
    mar = OxmlElement("w:tblCellMar")
    for side, v in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        e = OxmlElement(f"w:{side}")
        e.set(qn("w:w"), str(v))
        e.set(qn("w:type"), "dxa")
        mar.append(e)
    pr.append(mar)


class WellPlanReport(WellReport):
    """Professional well-plan document: cover with document control, revision history and distribution, contents, list of figures and tables,
    running header and footer with document id, classification and page x of y, key-data box, captioned tables and figures (Word SEQ fields so
    that the lists update), landscape and A3 sheet sections, numeric alignment and repeated table headers.

    Prepared / reviewed / approved cells are left blank on purpose (named people are entered by the document owner).
    """

    NAVY = RGBColor(0x1F, 0x3A, 0x5F)

    def __init__(self, title: str, subtitle: str, doc_id: str, revision: str, date: str, status: str, classification: str, organisation: str = "",
                 revisions: Optional[Sequence[Sequence[str]]] = None, distribution: Optional[Sequence[Sequence[str]]] = None, notice: str = "") -> None:
        self.doc = Document()
        self.doc_id, self.revision, self.status, self.classification = doc_id, revision, status, classification
        self.title = title
        st = self.doc.styles["Normal"]
        st.font.name = "Calibri"
        st.font.size = Pt(10)
        st.paragraph_format.space_after = Pt(4)
        for name, size in (("Heading 1", 16), ("Heading 2", 12.5), ("Heading 3", 11)):
            hs = self.doc.styles[name]
            hs.font.name = "Calibri"
            hs.font.size = Pt(size)
            hs.font.bold = True
            hs.font.color.rgb = self.NAVY
            hs.paragraph_format.keep_with_next = True
            hs.paragraph_format.space_before = Pt(14 if name == "Heading 1" else 10)
            hs.paragraph_format.space_after = Pt(5)
        for sname in ("Header", "Footer"):
            self.doc.styles[sname].paragraph_format.tab_stops.clear_all()
        for sname in ("TOC 1", "TOC 2", "Table of Figures"):
            try:
                st_ = self.doc.styles[sname]
                st_.font.size = Pt(9)
                st_.paragraph_format.space_after = Pt(0)
                st_.paragraph_format.space_before = Pt(0)
            except KeyError:
                pass
        cap = self.doc.styles["Caption"]
        cap.font.name = "Calibri"
        cap.font.size = Pt(9)
        cap.font.bold = True
        cap.font.italic = False
        cap.font.color.rgb = RGBColor(0, 0, 0)
        sec = self.doc.sections[0]
        sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
        sec.left_margin = sec.right_margin = Cm(1.9)
        sec.top_margin, sec.bottom_margin = Cm(2.2), Cm(2.0)
        sec.header_distance = sec.footer_distance = Cm(0.9)
        sec.different_first_page_header_footer = True
        self._header_footer(sec, 17.2)
        self.ch = self.h2 = self.app_n = 0
        self.usable_cm = 17.2
        self.fig_n = self.tab_n = 0
        self.figures: List[Dict[str, str]] = []
        self.tables_list: List[Dict[str, str]] = []
        self._cover(title, subtitle, organisation, date, revisions or [], distribution or [], notice)

    def _header_footer(self, sec, width_cm: float) -> None:
        """Running header (document title left, id and classification right) and footer (status left, page x of y right) for a section."""
        for part, is_header, left, right in ((sec.header, True, self.title, f"{self.doc_id} rev {self.revision} | {self.classification}"), (sec.footer, False, f"{self.status}", None)):
            part.is_linked_to_previous = False
            p = part.paragraphs[0]
            for r in list(p.runs):
                r._r.getparent().remove(r._r)
            p.paragraph_format.tab_stops.clear_all()
            p.paragraph_format.tab_stops.add_tab_stop(Cm(width_cm), alignment=WD_TAB_ALIGNMENT.RIGHT)
            r = p.add_run(left)
            r.font.size = Pt(8)
            r.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
            p.add_run("\t")
            if right is not None:
                rr = p.add_run(right)
                rr.font.size = Pt(8)
                rr.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
            else:
                a = p.add_run(f"{self.doc_id} rev {self.revision} | page ")
                a.font.size = Pt(8)
                _field(p, "PAGE", size=8)
                b = p.add_run(" of ")
                b.font.size = Pt(8)
                _field(p, "NUMPAGES", size=8)
            ppr = p._p.get_or_add_pPr()
            bd = OxmlElement("w:pBdr")
            edge = OxmlElement("w:bottom" if is_header else "w:top")
            edge.set(qn("w:val"), "single")
            edge.set(qn("w:sz"), "4")
            edge.set(qn("w:space"), "2")
            edge.set(qn("w:color"), "808080")
            bd.append(edge)
            ppr.append(bd)

    def _kv_table(self, rows: Sequence[Sequence[str]], widths: Sequence[float], header: Optional[Sequence[str]] = None, font: float = 9.0, label_cols: Sequence[int] = (0,)):
        n = len(rows) + (1 if header else 0)
        ncol = len(widths)
        t = self.doc.add_table(rows=n, cols=ncol)
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        _cell_margins(t)
        allrows = ([list(header)] if header else []) + [list(r) for r in rows]
        for i, row in enumerate(allrows):
            for j in range(ncol):
                cell = t.rows[i].cells[j]
                cell.width = Cm(widths[j])
                par = cell.paragraphs[0]
                par.paragraph_format.space_after = Pt(0)
                txt = str(row[j]) if j < len(row) and row[j] is not None else ""
                self._runs(par, txt, font)
                if header and i == 0:
                    _shade(cell, "1F3A5F")
                    for run in par.runs:
                        run.bold = True
                        run.font.color.rgb = RGBColor(255, 255, 255)
                elif j in label_cols:
                    _shade(cell, "E8EDF5")
                    for run in par.runs:
                        run.bold = True
            t.rows[i]._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
        return t

    def _cover(self, title: str, subtitle: str, organisation: str, date: str, revisions, distribution, notice: str) -> None:
        d = self.doc
        for _ in range(3):
            d.add_paragraph()
        if organisation:
            p = d.add_paragraph()
            r = p.add_run(organisation.upper())
            r.font.size = Pt(10)
            r.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
        p = d.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        r = p.add_run(title)
        r.bold = True
        r.font.size = Pt(28)
        r.font.color.rgb = self.NAVY
        p = d.add_paragraph()
        r = p.add_run(subtitle)
        r.font.size = Pt(13)
        r.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
        ppr = p._p.get_or_add_pPr()
        bd = OxmlElement("w:pBdr")
        edge = OxmlElement("w:bottom")
        edge.set(qn("w:val"), "single")
        edge.set(qn("w:sz"), "12")
        edge.set(qn("w:space"), "6")
        edge.set(qn("w:color"), "1F3A5F")
        bd.append(edge)
        ppr.append(bd)
        d.add_paragraph()
        cp = d.add_paragraph()
        cr = cp.add_run("Document control")
        cr.bold = True
        cr.font.size = Pt(11)
        self._kv_table([["Document id", self.doc_id, "Revision", self.revision], ["Date", date, "Status", self.status],
                        ["Classification", self.classification, "Basis", "Screening, concept / pre-FEED"],
                        ["Prepared by", "(name, date - to be entered)", "Reviewed by", "(name, date - to be entered)"],
                        ["Approved by", "(name, date - to be entered)", "Owner", "(to be entered)"]], [3.2, 5.6, 3.2, 5.2], label_cols=(0, 2))
        d.add_paragraph()
        cp = d.add_paragraph()
        cr = cp.add_run("Revision history")
        cr.bold = True
        cr.font.size = Pt(11)
        self._kv_table(revisions or [[self.revision, date, "First issue (screening draft)", ""]], [2.0, 3.0, 9.0, 4.2], header=["Rev", "Date", "Description", "By"], label_cols=())
        d.add_paragraph()
        cp = d.add_paragraph()
        cr = cp.add_run("Distribution")
        cr.bold = True
        cr.font.size = Pt(11)
        self._kv_table(distribution or [["(to be entered)", "", ""]], [6.0, 6.2, 6.0], header=["Name / function", "Company / team", "Copy"], label_cols=())
        d.add_paragraph()
        if notice:
            self.callout("Status notice", [notice], fill="FDECC8", size=8.5)
        d.add_page_break()
        cp = d.add_paragraph()
        cr = cp.add_run("Contents")
        cr.bold = True
        cr.font.size = Pt(16)
        cr.font.color.rgb = self.NAVY
        tp = d.add_paragraph()
        _field(tp, 'TOC \\o "1-2" \\h \\z \\u', "Update the field to build the table of contents.")
        d.add_page_break()
        cp = d.add_paragraph()
        cr = cp.add_run("List of figures")
        cr.bold = True
        cr.font.size = Pt(13)
        cr.font.color.rgb = self.NAVY
        _field(d.add_paragraph(), 'TOC \\h \\z \\c "Figure"', "Update the field to build the list of figures.")
        cp = d.add_paragraph()
        cr = cp.add_run("List of tables")
        cr.bold = True
        cr.font.size = Pt(13)
        cr.font.color.rgb = self.NAVY
        _field(d.add_paragraph(), 'TOC \\h \\z \\c "Table"', "Update the field to build the list of tables.")
        d.add_page_break()

    def _caption(self, label: str, n: int, text: str, above: bool, keep_next: bool) -> None:
        cp = self.doc.add_paragraph(style="Caption")
        cp.paragraph_format.keep_with_next = keep_next
        cp.paragraph_format.space_after = Pt(3 if above else 1)
        cp.paragraph_format.space_before = Pt(6 if above else 2)
        cp.alignment = WD_ALIGN_PARAGRAPH.LEFT if above else WD_ALIGN_PARAGRAPH.CENTER
        cp.add_run(f"{label} ")
        _field(cp, f"SEQ {label} \\* ARABIC", str(n))
        self._runs(cp, f". {text}", 9)
        for r in cp.runs:
            r.bold = True

    def h1(self, text: str, page_break: bool = True) -> None:
        super().h1(text, page_break)

    def landscape(self, a3: bool = False, margin_cm: Optional[float] = None) -> None:
        """Start a landscape section (A4, or A3 for drawing sheets) with its own header and footer."""
        sec = self.doc.add_section(WD_SECTION.NEW_PAGE)
        sec.orientation = WD_ORIENT.LANDSCAPE
        sec.different_first_page_header_footer = False
        w, h = (42.0, 29.7) if a3 else (29.7, 21.0)
        sec.page_width, sec.page_height = Cm(w), Cm(h)
        m = margin_cm if margin_cm is not None else (1.2 if a3 else 1.9)
        sec.left_margin = sec.right_margin = Cm(m)
        sec.top_margin, sec.bottom_margin = Cm(m + 0.6), Cm(m + 0.3)
        self.usable_cm = w - 2 * m
        self._header_footer(sec, self.usable_cm)

    def portrait(self) -> None:
        """Return to a portrait A4 section."""
        sec = self.doc.add_section(WD_SECTION.NEW_PAGE)
        sec.orientation = WD_ORIENT.PORTRAIT
        sec.different_first_page_header_footer = False
        sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
        sec.left_margin = sec.right_margin = Cm(1.9)
        sec.top_margin, sec.bottom_margin = Cm(2.2), Cm(2.0)
        self.usable_cm = 17.2
        self._header_footer(sec, self.usable_cm)

    def key_data_box(self, title: str, items: Sequence[Sequence[str]], columns: int = 2, size: float = 8.5) -> None:
        """Shaded key-data box: ``items`` are (label, value) pairs laid out in ``columns`` label/value column pairs."""
        rows = []
        for i in range(0, len(items), columns):
            chunk = list(items[i:i + columns])
            row: List[str] = []
            for lab, val in chunk:
                row += [lab, val]
            row += [""] * (2 * columns - len(row))
            rows.append(row)
        lw = {1: 3.4, 2: 3.0}.get(columns, 2.6)
        vw = (self.usable_cm - lw * columns) / columns
        self.tab_n += 1
        self.tables_list.append({"n": str(self.tab_n), "caption": title})
        self._caption("Table", self.tab_n, title, above=True, keep_next=True)
        self._kv_table(rows, [lw, vw] * columns, font=size, label_cols=tuple(range(0, 2 * columns, 2)))
        self.doc.add_paragraph().paragraph_format.space_after = Pt(2)

    def callout(self, title: str, lines: Sequence[str], fill: str = "EAF1FB", size: float = 9.5) -> None:
        """Shaded, bordered box made of paragraphs (not a table, so it needs no table caption); lines support the inline markup of paragraphs."""
        def box(par) -> None:
            ppr = par._p.get_or_add_pPr()
            bd = OxmlElement("w:pBdr")
            for side in ("top", "left", "bottom", "right"):
                e = OxmlElement(f"w:{side}")
                e.set(qn("w:val"), "single")
                e.set(qn("w:sz"), "6")
                e.set(qn("w:space"), "4")
                e.set(qn("w:color"), "808080")
                bd.append(e)
            ppr.append(bd)
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:fill"), fill)
            ppr.append(shd)
            par.paragraph_format.left_indent = Cm(0.2)
            par.paragraph_format.right_indent = Cm(0.2)
            par.paragraph_format.space_after = Pt(0)

        p = self.doc.add_paragraph()
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.space_before = Pt(6)
        r = p.add_run(title)
        r.bold = True
        r.font.size = Pt(size + 1)
        box(p)
        for i, ln in enumerate(lines):
            q = self.doc.add_paragraph()
            q.paragraph_format.keep_with_next = i < len(lines) - 1
            self._runs(q, ln, size)
            box(q)
        self.doc.add_paragraph().paragraph_format.space_after = Pt(2)

    def table(self, rows: Sequence[Sequence[object]], caption: Optional[str] = None, font: float = 8.0, widths: Optional[Sequence[float]] = None,
              note: Optional[str] = None, align_numbers: bool = True, keep_together: Optional[bool] = None) -> None:
        """Captioned table: shaded repeated header row, zebra rows, numeric columns right-aligned, rows kept whole, optional note line below.

        Tables of at most 16 rows are kept on one page (``keep_together`` default); pass ``False`` for long tables that may break across pages.
        """
        rows = [[("" if c is None else str(c)) for c in r] for r in rows]
        ncol = max(len(r) for r in rows)
        rows = [r + [""] * (ncol - len(r)) for r in rows]
        if caption:
            self.tab_n += 1
            self.tables_list.append({"n": str(self.tab_n), "caption": caption})
            self._caption("Table", self.tab_n, caption, above=True, keep_next=True)
        t = self.doc.add_table(rows=len(rows), cols=ncol)
        t.style = "Table Grid"
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        _cell_margins(t, 25, 25, 60, 60)
        usable = self.usable_cm
        if widths is None:
            lens = [min(max(max(len(r[c]) for r in rows), 5), 48) ** 0.75 for c in range(ncol)]
            tot = sum(lens)
            widths = [usable * x / tot for x in lens]
        else:
            tot = sum(widths)
            widths = [usable * w / tot for w in widths] if tot > usable + 0.05 else list(widths)
        numeric_col = [align_numbers and any(_is_numeric_cell(r[c]) for r in rows[1:]) and all(_is_numeric_cell(r[c]) or r[c].strip() in ("", "-") for r in rows[1:]) for c in range(ncol)]
        for i, row in enumerate(rows):
            tr = t.rows[i]
            trpr = tr._tr.get_or_add_trPr()
            trpr.append(OxmlElement("w:cantSplit"))
            if i == 0:
                trpr.append(OxmlElement("w:tblHeader"))
            for j, txt in enumerate(row):
                cell = tr.cells[j]
                cell.width = Cm(widths[j])
                par = cell.paragraphs[0]
                par.paragraph_format.space_after = Pt(0)
                self._runs(par, txt, font)
                if i == 0:
                    _shade(cell, "1F3A5F")
                    for r in par.runs:
                        r.bold = True
                        r.font.color.rgb = RGBColor(255, 255, 255)
                else:
                    if i % 2 == 0:
                        _shade(cell, "F3F6FA")
                    if numeric_col[j]:
                        par.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        if keep_together is None:
            keep_together = len(rows) <= 16
        if keep_together:
            for tr in t.rows[:-1]:
                for cell in tr.cells:
                    for par in cell.paragraphs:
                        par.paragraph_format.keep_with_next = True
        if note:
            q = self.doc.add_paragraph()
            q.paragraph_format.space_before = Pt(2)
            rr = q.add_run(note)
            rr.italic = True
            rr.font.size = Pt(7.5)
            rr.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
        else:
            self.doc.add_paragraph().paragraph_format.space_after = Pt(2)

    def figure(self, path: Path, caption: str, provenance: str = "", width_cm: float = 15.5, max_height_cm: Optional[float] = None) -> None:
        """Figure with a caption below (SEQ field) and a provenance line; the picture is scaled to fit the width and ``max_height_cm``."""
        from PIL import Image

        self.fig_n += 1
        with Image.open(str(path)) as im:
            ratio = im.height / im.width
        w = min(width_cm, self.usable_cm)
        mh = max_height_cm if max_height_cm is not None else (23.0 if self.usable_cm < 20 else 14.5)
        if w * ratio > mh:
            w = mh / ratio
        p = self.doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.keep_with_next = True
        p.paragraph_format.space_after = Pt(0)
        p.add_run().add_picture(str(path), width=Cm(w))
        self._caption("Figure", self.fig_n, caption, above=False, keep_next=bool(provenance))
        if provenance:
            q = self.doc.add_paragraph()
            q.alignment = WD_ALIGN_PARAGRAPH.CENTER
            rr = q.add_run(provenance)
            rr.italic = True
            rr.font.size = Pt(7.5)
            rr.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
        self.figures.append({"n": str(self.fig_n), "file": Path(path).name, "caption": caption})

    def sheet_page(self, path: Path, caption: str, provenance: str = "", a3: bool = True) -> None:
        """Place a drawing sheet on its own landscape page (A3 by default) and return to portrait afterwards."""
        self.landscape(a3=a3)
        h_avail = (29.7 - 2 * 1.2 - 2.4 - 1.6) if a3 else (21.0 - 2 * 1.9 - 2.4)
        self.figure(path, caption, provenance, width_cm=self.usable_cm, max_height_cm=h_avail)
        self.portrait()

    def save(self, path: Path) -> Path:
        """Save the document."""
        path = Path(path)
        self.doc.save(path)
        return path
