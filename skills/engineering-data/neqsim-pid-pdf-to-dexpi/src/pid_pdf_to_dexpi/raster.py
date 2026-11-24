"""Raster (scanned or image-only) P&ID sheets to the same vector primitives as a CAD PDF.

The image is binarised and split into:

- horizontal and vertical strokes (morphological opening), each with its measured thickness as the
  stroke width, so the same width classes separate process piping from symbols;
- solid blobs (valve bodies, filled balls, arrowheads) with a shape signature that the inline
  classifier understands (``lll`` triangle-like, ``cccccccc`` disc-like);
- thin outline components (vessel shells with heads) whose bounding boxes stand in for the curves
  a raster has lost;
- words from Tesseract OCR on the image with long lines removed.

Diagonal strokes are not recovered, so bowtie valves are found only when filled and pentagon
tips are not seen; connector direction then relies on FROM/TO labels. Results carry
``source.raster = true`` and lower confidence, and always need review.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Optional

from .extract import Page, Word
from .geometry import Rect, Segment

IMAGE_SUFFIXES = (".png", ".tif", ".tiff", ".jpg", ".jpeg", ".bmp")


def is_raster_pdf(pdf_path: str | Path, page_index: int = 0, min_drawings: int = 200) -> bool:
    """True when a PDF page has (almost) no vector paths but carries an image, i.e. a scan."""
    import fitz

    page = fitz.open(str(pdf_path))[page_index]
    return len(page.get_drawings()) < min_drawings and bool(page.get_images())


def load_raster_page(path: str | Path, page_index: int = 0, dpi: int = 300, threshold: int = 160,
                     ocr: bool = True, ocr_lang: str = "eng") -> Page:
    """Loads a scanned PDF page or an image file as page primitives in PDF points."""
    import numpy as np

    src = Path(path)
    gray, scale, width_pt, height_pt = _load_gray(src, page_index, dpi)
    black = gray < threshold
    words = _ocr_words(black, scale, ocr_lang) if ocr else []
    fills, fill_kinds, solid = _solid_blobs(black, scale)
    strokes = black & ~solid
    segments = _axis_strokes(strokes, scale)
    curves = _thin_outlines(strokes, scale)
    source = {"file": src.name, "sha256": hashlib.sha256(src.read_bytes()).hexdigest(), "page": page_index,
              "units": "pt", "raster": True, "rasterDpi": dpi, "ocr": "tesseract" if ocr else "none"}
    del np
    page = Page(width_pt, height_pt, words, segments, curves, fills, source, fill_kinds)
    page.region_lookup = RegionLookup(black, scale)
    return page


def _load_gray(src: Path, page_index: int, dpi: int):
    import numpy as np

    if src.suffix.lower() in IMAGE_SUFFIXES:
        from PIL import Image

        img = Image.open(str(src)).convert("L")
        arr = np.asarray(img)
        scale = 72.0 / dpi
        return arr, scale, arr.shape[1] * scale, arr.shape[0] * scale
    import fitz

    page = fitz.open(str(src))[page_index]
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    return arr, page.rect.width / pix.width, page.rect.width, page.rect.height


def _line_mask(black, length: int):
    from scipy import ndimage as ndi
    import numpy as np

    h = ndi.binary_opening(black, structure=np.ones((1, length), bool))
    v = ndi.binary_opening(black, structure=np.ones((length, 1), bool))
    return h, v


def _ocr_words(black, scale: float, lang: str) -> list[Word]:
    """OCR on the image with long lines removed (boxes and pipes otherwise break the words)."""
    import numpy as np
    import pytesseract
    from PIL import Image
    from scipy import ndimage as ndi

    length = max(20, int(round(10.0 / scale)))
    h, v = _line_mask(black, length)
    lines = ndi.binary_dilation(h | v, structure=np.ones((3, 3), bool))
    text = black & ~lines
    img = Image.fromarray(np.where(text, 0, 255).astype(np.uint8))
    data = pytesseract.image_to_data(img, lang=lang, config="--psm 11", output_type=pytesseract.Output.DICT)
    words = []
    for i, token in enumerate(data["text"]):
        token = token.strip()
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        if not token or conf < 30:
            continue
        x, y, w, hgt = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
        words.append(Word(token, Rect(x * scale, y * scale, (x + w) * scale, (y + hgt) * scale)))
    return words


def _solid_blobs(black, scale: float):
    """Filled symbol bodies: components that survive an erosion wider than any drawn line."""
    import numpy as np
    from scipy import ndimage as ndi

    k = max(3, int(round(2.0 / scale)))  # 2 pt: thicker than process lines (about 1.5 pt)
    core = ndi.binary_erosion(black, structure=np.ones((k, k), bool))
    solid = ndi.binary_dilation(core, structure=np.ones((k + 2, k + 2), bool)) & black
    labels, n = ndi.label(solid)
    fills, kinds = [], []
    for i, sl in enumerate(ndi.find_objects(labels)):
        if sl is None:
            continue
        hgt, wid = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if max(hgt, wid) * scale > 30:
            continue
        area = float((labels[sl] == i + 1).sum())
        ratio = area / max(1.0, hgt * wid)
        aspect = wid / max(1.0, hgt)
        if 0.7 <= ratio <= 0.86 and 0.8 <= aspect <= 1.25:
            kind = "cccccccc"
        elif 0.35 <= ratio <= 0.65:
            kind = "lll"
        else:
            kind = "l" * 4 if ratio > 0.86 else "x"
        fills.append(Rect(float(sl[1].start * scale), float(sl[0].start * scale), float(sl[1].stop * scale),
                          float(sl[0].stop * scale)))
        kinds.append(kind)
    return fills, kinds, solid


def _axis_strokes(strokes, scale: float, min_len_pt: float = 6.0) -> list[Segment]:
    """Horizontal and vertical strokes with their measured thickness as width (pt)."""
    import numpy as np
    from scipy import ndimage as ndi

    length = max(8, int(round(min_len_pt / scale)))
    h, v = _line_mask(strokes, length)
    out: list[Segment] = []
    for mask, horizontal in ((h, True), (v, False)):
        labels, _ = ndi.label(mask)
        for i, sl in enumerate(ndi.find_objects(labels)):
            if sl is None:
                continue
            comp = labels[sl] == i + 1
            rows, cols = np.nonzero(comp)
            if horizontal:
                span = cols.max() - cols.min() + 1
                thick = comp.sum() / float(span)
                y = (sl[0].start + rows.mean() + 0.5) * scale
                x0, x1 = (sl[1].start + cols.min()) * scale, (sl[1].start + cols.max() + 1) * scale
                out.append(Segment(float(x0), float(y), float(x1), float(y), float(thick * scale), False))
            else:
                span = rows.max() - rows.min() + 1
                thick = comp.sum() / float(span)
                x = (sl[1].start + cols.mean() + 0.5) * scale
                y0, y1 = (sl[0].start + rows.min()) * scale, (sl[0].start + rows.max() + 1) * scale
                out.append(Segment(float(x), float(y0), float(x), float(y1), float(thick * scale), False))
    return out


def _thin_outlines(strokes, scale: float, min_size_pt: float = 40.0) -> list[Segment]:
    """Bounding boxes of large thin-line components (vessel shells with heads) as closed 'curves'.

    Thick piping is removed first so a shell is not merged with the pipes on its nozzles.
    """
    import numpy as np
    from scipy import ndimage as ndi

    k = max(2, int(round(0.9 / scale)))
    thick = ndi.binary_opening(strokes, structure=np.ones((k, k), bool))
    thick = ndi.binary_dilation(thick, structure=np.ones((k + 2, k + 2), bool))
    thin = strokes & ~thick
    labels, _ = ndi.label(thin, structure=np.ones((3, 3), bool))
    out: list[Segment] = []
    limit = min_size_pt / scale
    for sl in ndi.find_objects(labels):
        if sl is None:
            continue
        hgt, wid = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
        if wid < limit or hgt < 0.5 * limit or wid * hgt > 0.25 * strokes.size:
            continue
        x0, y0, x1, y1 = (float(v * scale) for v in (sl[1].start, sl[0].start, sl[1].stop, sl[0].stop))
        for a, b in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
            out.append(Segment(a[0], a[1], b[0], b[1], 0.48, False))
    return out


class RegionLookup:
    """Bounding box (pt) of the white region containing a point.

    The image is max-pooled by ``factor`` so thin outlines survive; dashed internals keep their gaps
    and do not split the region.
    """

    def __init__(self, black, scale: float, factor: int = 4):
        from scipy import ndimage as ndi

        hgt = black.shape[0] // factor * factor
        wid = black.shape[1] // factor * factor
        pooled = black[:hgt, :wid].reshape(hgt // factor, factor, wid // factor, factor).any(axis=(1, 3))
        self.labels, _ = ndi.label(~pooled)
        self.boxes = ndi.find_objects(self.labels)
        self.step = scale * factor

    def __call__(self, point):
        r, c = int(point[1] / self.step), int(point[0] / self.step)
        if not (0 <= r < self.labels.shape[0] and 0 <= c < self.labels.shape[1]):
            return None
        lab = self.labels[r, c]
        if lab == 0 or self.boxes[lab - 1] is None:
            return None
        sl = self.boxes[lab - 1]
        s = self.step
        return Rect(float(sl[1].start * s), float(sl[0].start * s), float(sl[1].stop * s), float(sl[0].stop * s))

def raster_config_overrides() -> dict[str, Any]:
    """Settings that suit raster input (thicker measured strokes, no diagonals)."""
    return {"process_min_width": 1.2, "endpoint_tol": 2.5, "gap_lateral_tol": 2.0, "outline_width_tol": 0.35, "corner_gap": 12.0}


def load_page(path: str | Path, page_index: int = 0, dpi: int = 300) -> tuple[Page, Optional[dict[str, Any]]]:
    """Loads any sheet: vector PDF directly, scanned PDF or image through the raster route."""
    from .extract import load_pdf_page

    p = Path(path)
    if p.suffix.lower() in IMAGE_SUFFIXES or is_raster_pdf(p, page_index):
        return load_raster_page(p, page_index, dpi), raster_config_overrides()
    return load_pdf_page(p, page_index), None
