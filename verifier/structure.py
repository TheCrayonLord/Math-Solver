"""Turn page lines into problems and answer-key entries."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from .models import Document, KeyEntry, Line, Page, Problem

# ----------------------------------------------------------------- patterns

SECTION_PATTERNS = [
    re.compile(r"^(?:section|lesson|§)\s*(\d+)\s*[.\-–]\s*(\d+)\b", re.I),
    re.compile(r"^(\d+)\.(\d+)\s+[A-Z]"),            # "3.2 Solving Equations"
    re.compile(r"^(\d+)\s*[-–]\s*(\d+)\s+[A-Z]"),     # "3-2 Solving Equations"
    re.compile(r"^(\d+)\.(\d+)\s*$"),                 # "3.2" alone (common in keys)
]
CHAPTER_RE = re.compile(r"^(?:chapter|unit)\s+(\d+)\b\s*[:.\-–]?\s*(.*)$", re.I)
CHAPTER_EXTRA = ("review", "test", "practice", "quiz", "assessment", "cumulative")
KEY_HEADING_RE = re.compile(
    r"^(?:selected\s+|odd[- ]numbered\s+|student\s+)?(?:answers?|solutions)"
    r"(?:\s+(?:key|to\s+.*|section))?\s*$|^answer\s+key\b", re.I)
END_OF_KEY_RE = re.compile(r"^(?:index|glossary|credits|appendix)\b", re.I)

NUM_START_RE = re.compile(r"^(\d{1,3})\s*[.)]\s+(.*)$")
NUM_SPLIT_RE = re.compile(r"(?:(?<=\s)|^)(\d{1,3})\s*([.)])\s+")
PART_SPLIT_RE = re.compile(r"(?:(?<=\s)|^)(?:\(([a-h])\)|([a-h])[.)])\s+")

INSTRUCTION_VERBS = (
    "solve", "simplify", "evaluate", "factor", "find", "expand", "multiply", "add",
    "subtract", "divide", "compute", "write", "graph", "round", "use", "determine",
    "calculate", "estimate", "convert", "identify", "tell", "name", "classify",
    "for exercises", "in exercises", "exercises", "order", "compare", "express",
)


def section_from_text(text: str) -> Optional[str]:
    t = text.strip()
    for pat in SECTION_PATTERNS:
        m = pat.match(t)
        if m:
            return f"{int(m.group(1))}.{int(m.group(2))}"
    m = CHAPTER_RE.match(t)
    if m:
        rest = m.group(2).lower()
        for w in CHAPTER_EXTRA:
            if w in rest:
                return f"{int(m.group(1))} {w.title()}"
        return f"{int(m.group(1))}"
    return None


def is_instruction(text: str) -> bool:
    t = text.strip().lower()
    if NUM_START_RE.match(text.strip()):
        return False
    if len(t.split()) < 2:
        return False
    return t.startswith(INSTRUCTION_VERBS) or t.endswith(":") or " each " in f" {t} "


# ----------------------------------------------------------------- markers

@dataclass
class _Marker:
    kind: str  # "section" | "instruction"
    value: str
    page: int
    y: float
    x0: float
    x1: float
    col: int


def _col(line: Line, page: Page) -> int:
    return 0 if line.x0 < page.width * 0.45 else 1


def _overlaps(a0, a1, b0, b1) -> bool:
    return min(a1, b1) - max(a0, b0) > -5


@dataclass
class _Item:
    number: int
    text: str
    page: int
    y: float
    x0: float
    x1: float
    last_y: float
    has_fraction: bool = False
    section: Optional[str] = None
    instruction: str = ""


def _split_numbered(text: str, last_num: Optional[int]) -> list[tuple[int, str]]:
    """Split 'N. aaa  M. bbb' into pieces, accepting only increasing numbers."""
    matches = list(NUM_SPLIT_RE.finditer(text))
    if not matches or matches[0].start() != 0:
        return []
    delim = matches[0].group(2)
    accepted = []
    prev = last_num
    for m in matches:
        n = int(m.group(1))
        if m.start() != 0 and (m.group(2) != delim or delim == ")" and text[m.start() - 1:m.start()] != " "):
            continue
        if m.start() != 0 and not (prev is not None and prev < n <= prev + 4):
            continue
        if m.start() == 0 or prev is None or prev < n <= prev + 12:
            if accepted and n <= accepted[-1][0]:
                continue
            if m.start() != 0 and accepted == [] and prev is None:
                continue
            accepted.append((n, m))
            prev = n
    if not accepted or accepted[0][1].start() != 0:
        return []
    out = []
    for i, (n, m) in enumerate(accepted):
        end = accepted[i + 1][1].start() if i + 1 < len(accepted) else len(text)
        out.append((n, text[m.end():end].strip()))
    return out


def _scan(doc: Document, page_indices: list[int], key_mode: bool):
    """Collect numbered items with their section and instruction."""
    items: list[_Item] = []
    carry_section: Optional[str] = None
    carry_instruction = ""
    for pi in page_indices:
        page = doc.pages[pi]
        markers: list[_Marker] = []
        page_items: list[_Item] = []
        last_by_col: dict[int, _Item] = {}
        last_num_by_col: dict[int, Optional[int]] = {}
        pending_instr: Optional[_Marker] = None
        for line in page.lines:
            text = line.text.strip()
            col = _col(line, page)
            if key_mode and KEY_HEADING_RE.match(text):
                continue
            sec = section_from_text(text)
            if sec is not None and not NUM_START_RE.match(text):
                markers.append(_Marker("section", sec, pi, line.y0, line.x0, line.x1, col))
                last_by_col.pop(col, None)
                last_num_by_col[col] = None
                pending_instr = None
                continue
            pieces = _split_numbered(text, last_num_by_col.get(col))
            if pieces:
                pending_instr = None
                for n, body in pieces:
                    it = _Item(n, body, pi, line.y0, line.x0, line.x1, line.y1, line.has_fraction)
                    page_items.append(it)
                    last_by_col[col] = it
                    last_num_by_col[col] = n
                continue
            if not key_mode and is_instruction(text):
                if pending_instr is not None and line.y0 - pending_instr.y < 3 * line.size:
                    pending_instr.value += " " + text
                else:
                    pending_instr = _Marker("instruction", text, pi, line.y0, line.x0, line.x1, col)
                    markers.append(pending_instr)
                continue
            # continuation of the previous item in this column
            prev = last_by_col.get(col)
            if prev is not None and 0 <= line.y0 - prev.last_y < 2.2 * line.size \
                    and line.x0 >= prev.x0 - 5:
                prev.text += " " + text
                prev.last_y = line.y1
                prev.has_fraction = prev.has_fraction or line.has_fraction
            elif pending_instr is not None and line.y0 - pending_instr.y < 3 * line.size \
                    and not key_mode and not page_items:
                pending_instr.value += " " + text

        # assign markers to items
        col_top = {}
        for o in page_items:
            c = _col_of_x(o.x0, page)
            col_top[c] = min(col_top.get(c, o.y), o.y)

        def applies(m, it):
            if m.y > it.y + 1:
                return False
            icol = _col_of_x(it.x0, page)
            if _overlaps(m.x0, m.x1, it.x0, it.x1) or m.col == icol:
                return True
            # a heading above the top of the item's column spans both columns
            return m.y <= col_top.get(icol, it.y) + 1

        def nearest(kind, it):
            best = None
            for m in markers:
                if m.kind == kind and applies(m, it) and (best is None or m.y > best.y):
                    best = m
            return best

        for it in page_items:
            sm = nearest("section", it)
            it.section = sm.value if sm else carry_section
            im = nearest("instruction", it)
            # an instruction from before the latest section header doesn't apply
            if im and not (sm and im.y < sm.y):
                it.instruction = im.value
            elif sm:
                it.instruction = ""
            else:
                it.instruction = carry_instruction
            items.append(it)

        ordered = sorted(markers, key=lambda m: (m.col, m.y))
        secs = [m for m in ordered if m.kind == "section"]
        if secs:
            carry_section = secs[-1].value
            carry_instruction = ""
        instrs = [m for m in ordered if m.kind == "instruction"
                  and (not secs or (m.col, m.y) > (secs[-1].col, secs[-1].y))]
        if instrs:
            carry_instruction = instrs[-1].value
    return items


def _col_of_x(x: float, page: Page) -> int:
    return 0 if x < page.width * 0.45 else 1


def _split_parts(text: str) -> tuple[str, list[tuple[str, str]]]:
    """'stem a) aaa b) bbb' -> (stem, [('a','aaa'), ('b','bbb')]); parts must run a, b, c..."""
    ms = list(PART_SPLIT_RE.finditer(text))
    seq = []
    expect = "a"
    for m in ms:
        letter = m.group(1) or m.group(2)
        if letter == expect:
            seq.append((letter, m))
            expect = chr(ord(expect) + 1)
    if len(seq) < 2:
        return text, []
    stem = text[:seq[0][1].start()].strip()
    parts = []
    for i, (letter, m) in enumerate(seq):
        end = seq[i + 1][1].start() if i + 1 < len(seq) else len(text)
        parts.append((letter, text[m.end():end].strip()))
    return stem, parts


# ----------------------------------------------------------------- public API

def find_key_pages(doc: Document) -> list[int]:
    """Guess the answer-key pages: from an 'Answers' heading to the end (or Index)."""
    start = None
    n = len(doc.pages)
    for p in doc.pages:
        if p.index < n * 0.3 and n > 4:
            continue
        top = [l for l in p.lines if l.y0 < p.height * 0.3]
        if any(KEY_HEADING_RE.match(l.text.strip()) for l in top):
            start = p.index
            break
    if start is None:
        return []
    end = n - 1
    for p in doc.pages[start + 1:]:
        top = [l for l in p.lines if l.y0 < p.height * 0.2]
        if any(END_OF_KEY_RE.match(l.text.strip()) for l in top):
            end = p.index - 1
            break
    return list(range(start, end + 1))


def extract_problems(doc: Document, page_indices: list[int]) -> list[Problem]:
    problems = []
    for it in _scan(doc, page_indices, key_mode=False):
        printed = doc.pages[it.page].printed
        stem, parts = _split_parts(it.text)
        warnings = []
        if it.has_fraction:
            warnings.append("stacked fraction rebuilt from layout")
        if parts:
            for letter, body in parts:
                text = f"{stem} {body}".strip() if stem and not stem.endswith(".") else body
                instr = (it.instruction + " " + stem).strip() if stem.endswith(".") else it.instruction
                problems.append(Problem(it.section, it.number, letter, text, instr,
                                        it.page, printed, list(warnings)))
        else:
            problems.append(Problem(it.section, it.number, None, it.text, it.instruction,
                                    it.page, printed, warnings))
    return problems


def extract_key(doc: Document, page_indices: list[int]) -> list[KeyEntry]:
    entries = []
    for it in _scan(doc, page_indices, key_mode=True):
        printed = doc.pages[it.page].printed
        stem, parts = _split_parts(it.text)
        if parts and not stem:
            for letter, body in parts:
                entries.append(KeyEntry(it.section, it.number, letter, body, it.page, printed))
        else:
            entries.append(KeyEntry(it.section, it.number, None, it.text, it.page, printed))
    return entries


def match_key(problems: list[Problem], entries: list[KeyEntry]) -> dict[tuple, KeyEntry]:
    """Map problem.key -> KeyEntry."""
    by_key = {}
    for e in entries:
        by_key.setdefault((e.section, e.number, e.part), e)
    key_has_sections = any(e.section for e in entries)
    by_num: dict[tuple, list[KeyEntry]] = {}
    for e in entries:
        by_num.setdefault((e.number, e.part), []).append(e)

    out = {}
    for p in problems:
        e = by_key.get((p.section, p.number, p.part))
        if e is None and p.part is None:
            # whole-problem key for a problem without parts
            e = by_key.get((p.section, p.number, None))
        if e is None and (not key_has_sections or p.section is None):
            cands = by_num.get((p.number, p.part), [])
            if len(cands) == 1:
                e = cands[0]
        if e is not None:
            out[p.key] = e
    return out
