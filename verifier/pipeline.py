"""End-to-end: document -> problems + key -> solve -> compare -> results."""
from __future__ import annotations

import multiprocessing as mp
import os
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from .compare import compare, numbers_equal
from .models import (
    Document, KeyEntry, Problem, Result, VERDICT_CORRECT, VERDICT_INCOMPLETE, VERDICT_NO_KEY,
    VERDICT_REVIEW, VERDICT_UNREADABLE, VERDICT_WRONG,
)
from .solver import Unsupported, decimalize, solve_problem
from .structure import extract_key, extract_problems, find_key_pages, match_key

TIMEOUT_SECONDS = 20


@dataclass
class Report:
    document: str
    results: list[Result]
    notes: list[str] = field(default_factory=list)
    problem_pages: list[int] = field(default_factory=list)
    key_pages: list[int] = field(default_factory=list)
    key_entries: int = 0

    def count(self, verdict: str) -> int:
        return sum(1 for r in self.results if r.verdict == verdict)


def check_one(problem: Problem, key: Optional[KeyEntry]) -> Result:
    """Solve one problem and compare with its key entry. Never raises."""
    try:
        sol = solve_problem(problem)
    except Unsupported as exc:
        return Result(problem, key, VERDICT_REVIEW, error_type="Not solved automatically",
                      message=f"Not checked automatically: {exc}.")
    except Exception as exc:  # noqa: BLE001
        return Result(problem, key, VERDICT_REVIEW, error_type="Solver error",
                      message=f"The solver hit an error on this problem ({type(exc).__name__}).")
    res = Result(problem, key, VERDICT_NO_KEY, computed=sol.display, steps=sol.steps,
                 computed_value=_plain(sol.value), kind=sol.kind)
    if key is None:
        res.message = "No answer for this problem in the answer key."
        return res
    try:
        cmp = compare(sol, key.answer)
    except Exception as exc:  # noqa: BLE001
        res.verdict = VERDICT_REVIEW
        res.error_type = "Comparison error"
        res.message = f"Couldn't compare with the key ({type(exc).__name__})."
        return res
    res.verdict = cmp.verdict
    res.error_type = cmp.error_type
    res.message = cmp.message
    res.checks = cmp.checks
    if re.search(r"\d\.\d", problem.text):
        res.message = decimalize(res.message)
        res.checks = [decimalize(c) for c in res.checks]
    res.key_value = _plain(cmp.key_value)
    if res.verdict in (VERDICT_WRONG, VERDICT_INCOMPLETE) and problem.warnings:
        # math rebuilt from layout (e.g. stacked fractions) is less certain: be cautious
        res.message += f" (Note: {', '.join(problem.warnings)} — please double-check the problem was read correctly.)"
    return res


def _plain(v):
    """Make values picklable/comparable (sympy sets -> lists)."""
    import sympy as sp
    if isinstance(v, sp.FiniteSet):
        return list(v)
    return v


def _worker(args):
    return check_one(*args)


def run(doc: Document, problem_pages: list[int], key_pages: Optional[list[int]] = None,
        progress: Optional[Callable[[int, int], None]] = None, workers: Optional[int] = None) -> Report:
    if key_pages is None:
        key_pages = find_key_pages(doc)
    key_set = set(key_pages)
    problem_pages = [p for p in problem_pages if p not in key_set]
    problems = extract_problems(doc, problem_pages)
    # The same number twice in one section (e.g. numbered steps in a worked example, then the
    # exercises): keep the last one, which is normally the exercise.
    last = {}
    for p in problems:
        last[p.key] = p
    dropped = len(problems) - len(last)
    problems = [p for p in problems if last[p.key] is p]
    entries = extract_key(doc, key_pages) if key_pages else []
    matched = match_key(problems, entries)
    tasks = [(p, matched.get(p.key)) for p in problems]

    results: list[Result] = []
    if workers is None:
        workers = max(1, min(4, (os.cpu_count() or 2) - 1))
    pool = None
    if workers > 0 and len(tasks) >= 4:
        try:
            pool = mp.get_context("spawn").Pool(workers)
        except Exception:  # noqa: BLE001 - fall back to solving in this process
            pool = None
    if pool is None:
        for i, t in enumerate(tasks):
            results.append(_worker(t))
            if progress:
                progress(i + 1, len(tasks))
    else:
        try:
            pending = [pool.apply_async(_worker, (t,)) for t in tasks]
            for i, (t, fut) in enumerate(zip(tasks, pending)):
                try:
                    results.append(fut.get(timeout=TIMEOUT_SECONDS))
                except mp.TimeoutError:
                    results.append(Result(t[0], t[1], VERDICT_REVIEW, error_type="Timed out",
                                          message="The solver took too long on this problem."))
                except Exception as exc:  # noqa: BLE001
                    results.append(Result(t[0], t[1], VERDICT_REVIEW, error_type="Solver error",
                                          message=f"The solver crashed on this problem ({type(exc).__name__})."))
                if progress:
                    progress(i + 1, len(tasks))
        finally:
            pool.terminate()

    report = Report(doc.name, results, problem_pages=problem_pages, key_pages=key_pages,
                    key_entries=len(entries))
    if dropped:
        report.notes.append(f"{dropped} numbered item(s) repeated a problem number already used in the same "
                            f"section (often numbered steps in an example); only the last one was checked.")
    if not key_pages:
        report.notes.append("No answer key section was found. Set the answer key pages manually.")
    elif not entries:
        report.notes.append("The answer key pages were found, but no numbered answers could be read from them.")
    _detect_shifts(report)
    _section_sanity(report)
    return report


# ----------------------------------------------------------------- cross-problem analysis

def _values_equal(a, b) -> bool:
    if a is None or b is None:
        return False
    if isinstance(a, (list, tuple)) or isinstance(b, (list, tuple)):
        la = list(a) if isinstance(a, (list, tuple)) else [a]
        lb = list(b) if isinstance(b, (list, tuple)) else [b]
        if len(la) != len(lb):
            return False
        return all(any(numbers_equal(x, y) for y in lb) for x in la)
    try:
        return numbers_equal(a, b)
    except Exception:  # noqa: BLE001
        return False


def _detect_shifts(report: Report) -> None:
    by_section: dict = {}
    for r in report.results:
        by_section.setdefault(r.problem.section, []).append(r)
    for section, rs in by_section.items():
        rs_sorted = sorted(rs, key=lambda r: (r.problem.number, r.problem.part or ""))
        wrong = [r for r in rs_sorted if r.verdict == VERDICT_WRONG and r.key_value is not None]
        offsets: dict[int, list[Result]] = {}
        for r in wrong:
            for other in rs_sorted:
                if other is r or other.problem.part != r.problem.part:
                    continue
                if _values_equal(other.computed_value, r.key_value):
                    off = other.problem.number - r.problem.number
                    r.message += (f" Note: the key's answer here matches the correct answer to "
                                  f"#{other.problem.number}{other.problem.part or ''}.")
                    offsets.setdefault(off, []).append(r)
                    break
        for off, group in offsets.items():
            if len(group) >= 3:
                nums = sorted(g.problem.number for g in group)
                where = f"Section {section}" if section else "The answer key"
                direction = "later" if off > 0 else "earlier"
                report.notes.append(
                    f"{where}: the key answers for #{nums[0]}–#{nums[-1]} appear to be shifted — each one "
                    f"is the answer to the problem {abs(off)} {direction}. Key page: {group[0].key.page}.")
                for g in group:
                    g.error_type = "Key answers shifted"


def _section_sanity(report: Report) -> None:
    """If almost every answer in a section disagrees, suspect a reading/matching problem, not the key."""
    by_section: dict = {}
    for r in report.results:
        by_section.setdefault(r.problem.section, []).append(r)
    for section, rs in by_section.items():
        compared = [r for r in rs if r.verdict in (VERDICT_CORRECT, VERDICT_WRONG, VERDICT_INCOMPLETE)]
        wrong = [r for r in compared if r.verdict == VERDICT_WRONG and r.error_type != "Key answers shifted"]
        if len(compared) >= 5 and len(wrong) / len(compared) > 0.6:
            where = f"Section {section}" if section else "This document"
            report.notes.append(
                f"{where}: {len(wrong)} of {len(compared)} answers disagree with the key. That usually means "
                f"the key section was matched to the wrong problems or the page was misread, so these "
                f"were moved to 'Needs review' instead of being reported as key errors.")
            for r in wrong:
                r.verdict = VERDICT_REVIEW
                r.error_type = "Section mostly disagrees"


def summarize_errors(report: Report) -> list[Result]:
    errs = [r for r in report.results if r.verdict in (VERDICT_WRONG, VERDICT_INCOMPLETE)]
    return sorted(errs, key=lambda r: (r.problem.page_index, r.problem.number, r.problem.part or ""))
