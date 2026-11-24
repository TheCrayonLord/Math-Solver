"""Shared data structures."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Line:
    """One visual line (or column segment of a line) of text on a page."""
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    size: float
    page_index: int  # 0-based PDF page index
    has_fraction: bool = False  # a stacked fraction was rebuilt in this line


@dataclass
class Page:
    index: int  # 0-based
    width: float
    height: float
    lines: list[Line] = field(default_factory=list)
    printed: Optional[int] = None  # printed page number, if known

    @property
    def label(self) -> str:
        return page_label(self.index, self.printed)


def page_label(index: int, printed: Optional[int]) -> str:
    if printed is None:
        return f"PDF page {index + 1}"
    if printed == index + 1:
        return f"page {printed}"
    return f"page {printed} (PDF page {index + 1})"


@dataclass
class Document:
    name: str
    pages: list[Page]
    page_offset: Optional[int] = None  # printed = index + 1 + offset

    def printed_to_index(self, printed: int) -> Optional[int]:
        for p in self.pages:
            if p.printed == printed:
                return p.index
        if self.page_offset is not None:
            idx = printed - 1 - self.page_offset
            if 0 <= idx < len(self.pages):
                return idx
        return None


@dataclass
class Problem:
    section: Optional[str]
    number: int
    part: Optional[str]
    text: str
    instruction: str
    page_index: int
    printed_page: Optional[int]
    warnings: list[str] = field(default_factory=list)
    group: Optional[str] = None  # how the answer key groups problems, e.g. "page 10"

    @property
    def key(self) -> tuple:
        return (self.group or self.section, self.number, self.part)

    @property
    def label(self) -> str:
        s = f"#{self.number}{self.part or ''}"
        if self.section and not self.group:
            s = f"Section {self.section}, {s}"
        return s

    @property
    def page(self) -> str:
        return page_label(self.page_index, self.printed_page)


@dataclass
class KeyEntry:
    section: Optional[str]
    number: int
    part: Optional[str]
    answer: str
    page_index: int
    printed_page: Optional[int]

    @property
    def page(self) -> str:
        return page_label(self.page_index, self.printed_page)


@dataclass
class Solution:
    """What the solver computed for a problem."""
    kind: str  # number | expr | solutions | interval | tuple | factor | equation
    value: Any  # sympy object (or tuple / set)
    display: str
    steps: list[str] = field(default_factory=list)
    equations: list[Any] = field(default_factory=list)  # sympy relationals for plug-in checks
    variables: list[Any] = field(default_factory=list)
    places: Optional[int] = None  # rounding requested by the problem (decimal places)
    simplest_form: bool = False
    method: str = ""


VERDICT_CORRECT = "Correct"
VERDICT_WRONG = "Key is wrong"
VERDICT_INCOMPLETE = "Key is incomplete"
VERDICT_REVIEW = "Needs review"
VERDICT_NO_KEY = "No key entry"
VERDICT_UNREADABLE = "Couldn't read"

VERDICT_ICONS = {
    VERDICT_CORRECT: "✅",
    VERDICT_WRONG: "❌",
    VERDICT_INCOMPLETE: "⚠️",
    VERDICT_REVIEW: "🔍",
    VERDICT_NO_KEY: "➖",
    VERDICT_UNREADABLE: "⛔",
}


@dataclass
class Result:
    problem: Problem
    key: Optional[KeyEntry]
    verdict: str
    computed: str = ""
    error_type: str = ""
    message: str = ""
    checks: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    # raw values kept for cross-problem analysis (shift detection)
    computed_value: Any = None
    key_value: Any = None
    kind: str = ""
