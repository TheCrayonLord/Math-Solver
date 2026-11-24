"""Export results."""
from __future__ import annotations

import csv
import io

from .pipeline import Report

COLUMNS = ["Verdict", "Problem page", "PDF page", "Section", "Problem", "Problem text",
           "Key page", "Key answer", "Correct answer", "Error type", "What's wrong", "Checks"]


def to_csv(rep: Report) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(COLUMNS)
    for r in sorted(rep.results, key=lambda r: (r.problem.page_index, r.problem.section or "",
                                                 r.problem.number, r.problem.part or "")):
        p = r.problem
        w.writerow([
            r.verdict, p.printed_page if p.printed_page is not None else "", p.page_index + 1,
            p.section or "", f"{p.number}{p.part or ''}", p.text,
            r.key.page if r.key else "", r.key.answer if r.key else "",
            r.computed, r.error_type, r.message, " | ".join(r.checks),
        ])
    return buf.getvalue()
