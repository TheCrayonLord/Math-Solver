"""Read digital PDFs (and .docx via LibreOffice) into pages of text lines.

Math is rebuilt from the PDF layout:
  * smaller, raised text  -> exponent   (x + small raised 2  ->  x^2)
  * text stacked above/below a short horizontal rule -> fraction  ((3)/(4))
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from collections import Counter

import pymupdf

from .models import Document, Line, Page

PAGE_NUM_RE = re.compile(r"^(?:page\s+)?[-–]?\s*(\d{1,4})\s*[-–]?$", re.I)


def read_document(path: str, name: str | None = None) -> Document:
    name = name or os.path.basename(path)
    if path.lower().endswith(".docx"):
        pdf_path = docx_to_pdf(path)
        doc = read_pdf(pdf_path, name)
        return doc
    return read_pdf(path, name)


def find_soffice() -> str | None:
    for cand in ("soffice", "libreoffice"):
        p = shutil.which(cand)
        if p:
            return p
    for p in (
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ):
        if os.path.exists(p):
            return p
    return None


def docx_to_pdf(path: str) -> str:
    soffice = find_soffice()
    if not soffice:
        raise RuntimeError(
            "Reading .docx files needs LibreOffice (free, libreoffice.org). "
            "Install it, or save the document as PDF from Word and upload the PDF."
        )
    out_dir = tempfile.mkdtemp(prefix="mathverify_")
    subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", out_dir, path],
        check=True, capture_output=True, timeout=300,
    )
    pdf = os.path.join(out_dir, os.path.splitext(os.path.basename(path))[0] + ".pdf")
    if not os.path.exists(pdf):
        raise RuntimeError("LibreOffice could not convert the .docx file to PDF.")
    return pdf


def read_pdf(path_or_bytes, name: str = "document.pdf") -> Document:
    if isinstance(path_or_bytes, (bytes, bytearray)):
        pdf = pymupdf.open(stream=path_or_bytes, filetype="pdf")
    else:
        pdf = pymupdf.open(path_or_bytes)
    pages = []
    for i, pg in enumerate(pdf):
        pages.append(_read_page(pg, i))
    doc = Document(name=name, pages=pages)
    _assign_page_numbers(doc)
    return doc


# ---------------------------------------------------------------- page reading

def _vertical_rules(pg) -> list[tuple[float, float, float]]:
    """Vertical lines (table cell borders): (x, y0, y1)."""
    rules = []
    try:
        drawings = pg.get_drawings()
    except Exception:
        return rules
    for d in drawings:
        for item in d.get("items", []):
            if item[0] == "l":
                p1, p2 = item[1], item[2]
                if abs(p1.x - p2.x) < 0.8 and abs(p2.y - p1.y) > 8:
                    rules.append(((p1.x + p2.x) / 2, min(p1.y, p2.y), max(p1.y, p2.y)))
            elif item[0] == "re":
                r = item[1]
                if r.width < 1.6 and r.height > 8:
                    rules.append(((r.x0 + r.x1) / 2, r.y0, r.y1))
                elif r.width > 20 and r.height > 20 and d.get("color") is not None:
                    # stroked rectangle (a table cell): its left and right edges are rules
                    rules.append((r.x0, r.y0, r.y1))
                    rules.append((r.x1, r.y0, r.y1))
    return rules


def _horizontal_rules(pg) -> list[tuple[float, float, float]]:
    """Short horizontal lines that could be fraction bars: (x0, x1, y)."""
    rules = []
    try:
        drawings = pg.get_drawings()
    except Exception:
        return rules
    for d in drawings:
        for item in d.get("items", []):
            if item[0] == "l":
                p1, p2 = item[1], item[2]
                if abs(p1.y - p2.y) < 0.8 and 3 < abs(p2.x - p1.x) < 160:
                    rules.append((min(p1.x, p2.x), max(p1.x, p2.x), (p1.y + p2.y) / 2))
            elif item[0] == "re":
                r = item[1]
                if r.height < 1.6 and 3 < r.width < 160:
                    rules.append((r.x0, r.x1, (r.y0 + r.y1) / 2))
    return rules


def _split_span_by_baseline(span) -> list[dict]:
    """PyMuPDF can merge characters at different heights into one span; split them apart."""
    chars = span.get("chars") or []
    if not chars:
        return [span] if span.get("text") else []
    runs, cur = [], [chars[0]]
    for ch in chars[1:]:
        if abs(ch["origin"][1] - cur[-1]["origin"][1]) > 0.8:
            runs.append(cur)
            cur = [ch]
        else:
            cur.append(ch)
    runs.append(cur)
    out = []
    for run in runs:
        text = "".join(c["c"] for c in run)
        if not text:
            continue
        out.append({
            "text": text, "size": span["size"], "flags": span["flags"],
            "origin": run[0]["origin"], "chars": run,
            "bbox": (min(c["bbox"][0] for c in run), min(c["bbox"][1] for c in run),
                     max(c["bbox"][2] for c in run), max(c["bbox"][3] for c in run)),
        })
    return out


def _main_baseline(spans) -> float:
    big = max(s["size"] for s in spans)
    main = [s for s in spans if s["size"] >= 0.85 * big and s["text"].strip()] or spans
    return Counter(round(_baseline(s)) for s in main).most_common(1)[0][0]


def _merge_same_baseline(raw_lines):
    """Join line pieces that sit on the same baseline (column splitting happens later)."""
    groups: list[list] = []
    for spans in sorted(raw_lines, key=_main_baseline):
        bl = _main_baseline(spans)
        if groups and abs(_main_baseline(groups[-1]) - bl) <= 1.5:
            groups[-1] = groups[-1] + spans
        else:
            groups.append(list(spans))
    out = []
    for g in groups:
        out.append(_insert_overlays(g))
    return out


def _insert_overlays(spans):
    """A glyph drawn on top of a gap inside another span (e.g. the ∛ in 'Evaluate:  8') must be
    placed at its position in the text: split the outer span around it."""
    spans = sorted(spans, key=lambda s: s["bbox"][0])
    for _ in range(10):
        changed = False
        for big in spans:
            for small in spans:
                if small is big or not small["text"].strip():
                    continue
                if big["bbox"][0] + 1 < small["bbox"][0] and small["bbox"][2] < big["bbox"][2] - 1:
                    parts = _split_span_at(big, (small["bbox"][0] + small["bbox"][2]) / 2)
                    if parts:
                        spans = [x for x in spans if x is not big] + list(parts)
                        changed = True
                        break
            if changed:
                break
        if not changed:
            break
    return sorted(spans, key=lambda s: s["bbox"][0])


def _read_page(pg, index: int) -> Page:
    d = pg.get_text("rawdict")
    raw_lines = []  # list of list of span dicts
    for b in d["blocks"]:
        if b.get("type") != 0:
            continue
        for ln in b["lines"]:
            spans = []
            for s in ln["spans"]:
                spans.extend(_split_span_by_baseline(s))
            if spans:
                raw_lines.append(spans)

    rules = _horizontal_rules(pg)
    if rules:
        raw_lines, _ = _rebuild_fractions(raw_lines, rules)
    raw_lines = _merge_same_baseline(raw_lines)

    vrules = _vertical_rules(pg)
    page = Page(index=index, width=pg.rect.width, height=pg.rect.height)
    for spans in raw_lines:
        for seg in _line_segments(spans, vrules):
            text = _spans_to_text(seg)
            if not text.strip():
                continue
            x0 = min(s["bbox"][0] for s in seg)
            x1 = max(s["bbox"][2] for s in seg)
            y0 = min(s["bbox"][1] for s in seg)
            y1 = max(s["bbox"][3] for s in seg)
            size = max(s["size"] for s in seg)
            page.lines.append(Line(text=" ".join(text.split()), x0=x0, y0=y0, x1=x1, y1=y1,
                                   size=size, page_index=index,
                                   has_fraction=any(s.get("frac") for s in seg)))
    page.lines.sort(key=lambda l: (round(l.y0 / 3), l.x0))
    return page


def _baseline(span) -> float:
    return span["origin"][1]


def _rebuild_fractions(raw_lines, rules):
    """Replace numerator/denominator spans around a fraction bar by one '(n)/(d)' span."""
    used = set()  # (line_idx, span_idx)
    inserts = []  # (target_line_idx or None, span)
    for (rx0, rx1, ry) in rules:
        num, den = [], []
        for li, spans in enumerate(raw_lines):
            for si, s in enumerate(spans):
                if (li, si) in used or not s["text"].strip():
                    continue
                cx = (s["bbox"][0] + s["bbox"][2]) / 2
                if not (rx0 - 2 <= cx <= rx1 + 2):
                    continue
                bl, size = _baseline(s), s["size"]
                if ry - 1.3 * size <= bl <= ry + 0.5:
                    num.append((li, si, s))
                elif ry < bl <= ry + 1.6 * size and s["bbox"][1] > ry - 0.6 * size:
                    den.append((li, si, s))
        if not num or not den:
            continue
        # keep only the closest line above / below
        nb = max(_baseline(s) for _, _, s in num)
        db = min(_baseline(s) for _, _, s in den)
        num = [t for t in num if abs(_baseline(t[2]) - nb) < 2]
        den = [t for t in den if abs(_baseline(t[2]) - db) < 2]
        ntext = "".join(t[2]["text"] for t in sorted(num, key=lambda t: t[2]["bbox"][0])).strip()
        dtext = "".join(t[2]["text"] for t in sorted(den, key=lambda t: t[2]["bbox"][0])).strip()
        if not ntext or not dtext:
            continue
        for li, si, _ in num + den:
            used.add((li, si))
        size = max(t[2]["size"] for t in num + den)
        new_span = {
            "text": (f"({ntext}/{dtext})" if re.fullmatch(r"[\w.]+", ntext) and re.fullmatch(r"[\w.]+", dtext)
                     else f"(({ntext})/({dtext}))"), "size": size, "flags": 0, "frac": True,
            "origin": (rx0, ry + 0.35 * size),
            "bbox": (rx0, ry - size, rx1, ry + size),
        }
        # target line: one whose vertical extent contains the bar and is horizontally near
        target = None
        best = None
        for li, spans in enumerate(raw_lines):
            rem = [s for si, s in enumerate(spans) if (li, si) not in used]
            if not rem:
                continue
            y0 = min(s["bbox"][1] for s in rem)
            y1 = max(s["bbox"][3] for s in rem)
            lx0 = min(s["bbox"][0] for s in rem)
            lx1 = max(s["bbox"][2] for s in rem)
            if y0 <= ry <= y1:
                dist = 0 if lx0 - 40 <= rx0 <= lx1 + 40 else min(abs(rx0 - lx1), abs(lx0 - rx1))
                if dist < 60 and (best is None or dist < best):
                    best, target = dist, li
        inserts.append((target, new_span))

    if not inserts:
        return raw_lines, set()
    new_lines = []
    for li, spans in enumerate(raw_lines):
        new_lines.append([s for si, s in enumerate(spans) if (li, si) not in used])
    frac_lines = set()
    for target, span in inserts:
        if target is None:
            new_lines.append([span])
            frac_lines.add(len(new_lines) - 1)
        else:
            new_lines[target].append(span)
            frac_lines.add(target)
    out, out_frac = [], set()
    for li, spans in enumerate(new_lines):
        if spans:
            spans.sort(key=lambda s: s["bbox"][0])
            if li in frac_lines:
                out_frac.add(len(out))
            out.append(spans)
    return out, out_frac


def _split_span_at(span, x: float):
    """Split one span at page coordinate x (using its characters). Returns (left, right) or None."""
    chars = span.get("chars") or []
    left = [c for c in chars if (c["bbox"][0] + c["bbox"][2]) / 2 < x]
    right = [c for c in chars if (c["bbox"][0] + c["bbox"][2]) / 2 >= x]
    if not left or not right:
        return None
    def mk(cs):
        return {"text": "".join(c["c"] for c in cs), "size": span["size"], "flags": span["flags"],
                "origin": cs[0]["origin"], "chars": cs,
                "bbox": (min(c["bbox"][0] for c in cs), min(c["bbox"][1] for c in cs),
                         max(c["bbox"][2] for c in cs), max(c["bbox"][3] for c in cs))}
    return mk(left), mk(right)


def _line_segments(spans, vrules=()):
    """Split a line where there is a large horizontal gap or a vertical rule (separate columns)."""
    spans = sorted(spans, key=lambda s: s["bbox"][0])
    if vrules:
        y0 = min(s["bbox"][1] for s in spans)
        y1 = max(s["bbox"][3] for s in spans)
        xs = sorted({round(x, 1) for (x, ry0, ry1) in vrules if ry0 <= (y0 + y1) / 2 <= ry1})
        # a span that straddles a rule is split there
        for x in xs:
            out = []
            for s in spans:
                if s["bbox"][0] < x < s["bbox"][2]:
                    parts = _split_span_at(s, x)
                    out.extend(parts if parts else [s])
                else:
                    out.append(s)
            spans = out
    else:
        xs = []
    segs, cur = [], [spans[0]]
    for s in spans[1:]:
        prev = cur[-1]
        gap = s["bbox"][0] - prev["bbox"][2]
        size = max(prev["size"], s["size"])
        ruled = any(prev["bbox"][2] - 1 <= x <= s["bbox"][0] + 1 for x in xs)
        if gap > 3.0 * size or ruled:
            segs.append(cur)
            cur = [s]
        else:
            cur.append(s)
    segs.append(cur)
    return segs


def _spans_to_text(spans) -> str:
    base = max(s["size"] for s in spans)
    main = [s for s in spans if s["size"] >= 0.85 * base] or spans
    base_line = Counter(round(_baseline(s)) for s in main).most_common(1)[0][0]
    out = ""
    prev = None
    for s in spans:
        t = s["text"]
        small = s["size"] < 0.85 * base
        raised = _baseline(s) < base_line - 0.15 * base
        lowered = _baseline(s) > base_line + 0.1 * base
        is_sup = (small or s["flags"] & 1) and raised and t.strip()
        is_sub = small and lowered and t.strip() and not is_sup
        if prev is not None and not is_sup and not is_sub:
            gap = s["bbox"][0] - prev["bbox"][2]
            if gap > 0.25 * s["size"] and not out.endswith(" ") and not t.startswith(" "):
                out += " "
        if is_sup:
            tt = t.strip()
            out += "^" + (tt if re.fullmatch(r"[0-9a-zA-Z]", tt) else f"({tt})")
        elif is_sub:
            out += "_" + t.strip()
        else:
            out += t
        prev = s
    return out


# ---------------------------------------------------------------- page numbers

def _assign_page_numbers(doc: Document) -> None:
    offsets = Counter()
    found = {}
    for p in doc.pages:
        cands = [l for l in p.lines if l.y1 < p.height * 0.09 or l.y0 > p.height * 0.91]
        for l in cands:
            m = PAGE_NUM_RE.match(l.text.strip())
            if m:
                n = int(m.group(1))
                found[p.index] = n
                offsets[n - (p.index + 1)] += 1
                break
    if not offsets:
        return
    offset, count = offsets.most_common(1)[0]
    if count < max(2, len(found) * 0.5) and len(doc.pages) > 2:
        # not consistent enough: only trust explicit numbers
        for p in doc.pages:
            p.printed = found.get(p.index)
        return
    doc.page_offset = offset
    for p in doc.pages:
        n = p.index + 1 + offset
        p.printed = n if n >= 1 else None
    # remove page-number lines from the text so they don't look like problems
    for p in doc.pages:
        if p.printed is None:
            continue
        p.lines = [l for l in p.lines if not (
            (l.y1 < p.height * 0.09 or l.y0 > p.height * 0.91)
            and PAGE_NUM_RE.match(l.text.strip())
            and int(PAGE_NUM_RE.match(l.text.strip()).group(1)) == p.printed)]


def parse_page_ranges(spec: str, doc: Document, printed: bool) -> list[int]:
    """'12-30, 45' -> sorted list of 0-based indices. Raises ValueError on bad input."""
    out = set()
    for part in re.split(r"[,;]", spec):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(\d+)\s*(?:-|–|to)\s*(\d+)", part)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            if a > b:
                a, b = b, a
            nums = range(a, b + 1)
        elif part.isdigit():
            nums = [int(part)]
        else:
            raise ValueError(f"Can't understand page range '{part}'")
        for n in nums:
            if printed:
                idx = doc.printed_to_index(n)
                if idx is not None:
                    out.add(idx)
            elif 1 <= n <= len(doc.pages):
                out.add(n - 1)
    return sorted(out)
