"""Command line:  python -m verifier book.pdf [--pages 12-30] [--printed] [--key-pages 600-640] [--csv out.csv]"""
from __future__ import annotations

import argparse
import sys

from .ingest import parse_page_ranges, read_document
from .models import VERDICT_ICONS, VERDICT_INCOMPLETE, VERDICT_REVIEW, VERDICT_WRONG
from .pipeline import run, summarize_errors
from .report import to_csv


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m verifier",
                                 description="Check a math book's answer key.")
    ap.add_argument("file", help=".pdf or .docx file")
    ap.add_argument("--pages", help="pages to check, e.g. '12-30, 45' (default: all)")
    ap.add_argument("--printed", action="store_true",
                    help="page numbers are the numbers printed in the book (default: PDF page numbers)")
    ap.add_argument("--key-pages", help="answer key pages (default: detected automatically)")
    ap.add_argument("--csv", help="write all results to this CSV file")
    ap.add_argument("--all", action="store_true", help="also list problems that need review")
    ap.add_argument("--workers", type=int, default=None, help="parallel workers (0 = none)")
    a = ap.parse_args(argv)

    doc = read_document(a.file)
    pages = parse_page_ranges(a.pages, doc, a.printed) if a.pages else list(range(len(doc.pages)))
    key_pages = parse_page_ranges(a.key_pages, doc, a.printed) if a.key_pages else None

    def prog(i, n):
        print(f"\rChecking problem {i}/{n}", end="", file=sys.stderr, flush=True)

    rep = run(doc, pages, key_pages, progress=prog, workers=a.workers)
    print(file=sys.stderr)
    print(f"\n{doc.name}: {len(rep.results)} problems, {rep.key_entries} key entries")
    for v, icon in VERDICT_ICONS.items():
        n = rep.count(v)
        if n:
            print(f"  {icon} {v}: {n}")
    for note in rep.notes:
        print(f"\nNOTE: {note}")
    errs = summarize_errors(rep)
    if errs:
        print("\nProblems with the answer key:")
    for r in errs:
        print(f"\n{VERDICT_ICONS[r.verdict]} {r.problem.page} — {r.problem.label}"
              f"   [{r.error_type}]")
        print(f"   Problem: {r.problem.text}")
        if r.key:
            print(f"   Key says ({r.key.page.replace(' (', ', ').rstrip(')')}): {r.key.answer}")
        print(f"   Correct answer: {r.computed}")
        print(f"   What's wrong: {r.message}")
        for c in r.checks:
            print(f"     · {c}")
    if a.all:
        for r in rep.results:
            if r.verdict == VERDICT_REVIEW:
                print(f"\n🔍 {r.problem.page} — {r.problem.label}: {r.problem.text}\n   {r.message}")
    if a.csv:
        with open(a.csv, "w", newline="", encoding="utf-8") as f:
            f.write(to_csv(rep))
        print(f"\nWrote {a.csv}")
    return 1 if any(r.verdict in (VERDICT_WRONG, VERDICT_INCOMPLETE) for r in rep.results) else 0


if __name__ == "__main__":
    sys.exit(main())
