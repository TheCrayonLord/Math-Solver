"""Multiple-choice problems: 'Simplify: √27 + √12  A 6√3  B 5√6  C 8√3  D 5√3'."""
from __future__ import annotations

import re
from typing import Optional

CHOICE_RE = re.compile(r"(?:(?<=\s)|^)(?:\(([A-E])\)|([A-E])[).:]?)\s+(?![=<>≤≥*/^])")
KEY_LETTER_RE = re.compile(r"^\s*\(?([A-E])\)?(?=\s|$|\(|\.)")


def split_choices(text: str) -> Optional[tuple[str, dict[str, str]]]:
    """Return (stem, {'A': '...', ...}) when the text ends with lettered answer choices A, B, C...."""
    ms = list(CHOICE_RE.finditer(text))
    seq, expect = [], "A"
    for m in ms:
        letter = m.group(1) or m.group(2)
        if letter == expect:
            seq.append((letter, m))
            expect = chr(ord(expect) + 1)
        elif letter == "A":  # restart: an earlier "A" was part of the stem (e.g. "Solve A = lw")
            seq, expect = [(letter, m)], "B"
    if len(seq) < 3:
        return None
    stem = text[:seq[0][1].start()].strip()
    opts = {}
    for i, (letter, m) in enumerate(seq):
        end = seq[i + 1][1].start() if i + 1 < len(seq) else len(text)
        body = text[m.end():end].strip()
        if not body:
            return None
        opts[letter] = body
    if not stem:
        return None
    return stem, opts


def key_letter(answer: str) -> Optional[str]:
    m = KEY_LETTER_RE.match(answer)
    return m.group(1) if m else None
