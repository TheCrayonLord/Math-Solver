import os
import sys

import pytest
import sympy as sp

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from verifier.compare import compare, exprs_equal, numbers_equal  # noqa: E402
from verifier.mathparse import parse_math  # noqa: E402
from verifier.models import (  # noqa: E402
    Problem, VERDICT_CORRECT, VERDICT_INCOMPLETE, VERDICT_REVIEW, VERDICT_WRONG,
)
from verifier.solver import Unsupported, solve_problem  # noqa: E402


def P(text, instruction=""):
    return Problem(section=None, number=1, part=None, text=text, instruction=instruction,
                   page_index=0, printed_page=1)


def verdict(text, key, instruction=""):
    sol = solve_problem(P(text, instruction))
    return compare(sol, key)


# ------------------------------------------------------------ equivalent answers must NOT be flagged

@pytest.mark.parametrize("text,key,instr", [
    ("1/4 + 1/4", "1/2", ""),
    ("1/4 + 1/4", "0.5", ""),
    ("1/4 + 1/4", ".5", ""),
    ("1/4 + 1/4", "50%", ""),
    ("2x + 3 = 11", "4", ""),
    ("2x + 3 = 11", "x = 4", ""),
    ("2x + 3 = 11", "x = 4.0", ""),
    ("x^2 = 9", "x = ±3", ""),
    ("x^2 = 9", "x = 3 or x = −3", ""),
    ("x^2 = 9", "{−3, 3}", ""),
    ("x^2 = 9", "−3, 3", ""),
    ("(x + 1)^2", "x^2 + 2x + 1", "Simplify."),
    ("(x+1)(x-1)", "x^2 − 1", "Multiply."),
    ("x^2 − 9", "(x − 3)(x + 3)", "Factor."),
    ("x^2 − 9", "(x + 3)(x − 3)", "Factor."),
    ("3x − 4 > 8", "x > 4", ""),
    ("3x − 4 > 8", "(4, ∞)", ""),
    ("−1 < 2x + 3 ≤ 11", "−2 < x ≤ 4", ""),
    ("x + y = 10; x − y = 2", "(6, 4)", ""),
    ("x + y = 10; x − y = 2", "x = 6, y = 4", ""),
    ("2/3 × 9/10", "3/5", ""),
    ("2/3 × 9/10", "0.6", ""),
    ("1/3 + 0", "0.33", ""),                    # rounded decimal of 1/3
    ("√50", "5√2", "Simplify."),
    ("2 1/2 + 3/4", "3 1/4", ""),
    ("2 1/2 + 3/4", "13/4", ""),
    ("2 1/2 + 3/4", "3.25", ""),
    ("6x + 2 = 2(3x + 1)", "all real numbers", ""),
    ("3x + 5 = 3x − 1", "no solution", ""),
    ("x^2 + 4", "prime", "Factor."),
    ("y + 2x = 6", "y = 6 − 2x", "Solve for y."),
    ("What is 15% of 80?", "12", ""),
    ("18 is what percent of 72?", "25%", ""),
    ("18 is what percent of 72?", "25", ""),
    ("Round 3.456 to the nearest tenth.", "3.5", ""),
    ("Find the slope through (1, 2) and (4, 11).", "3", ""),
    ("Find the slope through (2, 1) and (2, 5).", "undefined", ""),
    ("x^2 + 2x − 15 = 0", "x = 3, −5", ""),
    ("(x^2 − 9)/(x − 3)", "x + 3", "Simplify."),
    ("|x − 2| = 5", "x = 7 or x = −3", ""),
    ("2x^2 = 7", "x = ±1.87", "Round to the nearest hundredth."),
])
def test_equivalent_answers_are_correct(text, key, instr):
    c = verdict(text, key, instr)
    assert c.verdict == VERDICT_CORRECT, c.message


# ------------------------------------------------------------ wrong keys must be caught

@pytest.mark.parametrize("text,key,instr,etype", [
    ("2x + 3 = 11", "x = −4", "", "Sign error"),
    ("5x − 7 = 3x + 9", "x = 7", "", "Wrong value"),
    ("18 ÷ 0.3", "6", "", "Decimal point error"),
    ("3/4", "4/3", "", "Reciprocal"),
    ("Round 3.456 to the nearest tenth.", "3.4", "", "Rounding error"),
    ("−2x + 1 ≤ 9", "x ≤ −4", "", "Inequality sign reversed"),
    ("3x ≤ 12", "x < 4", "", "Endpoint error"),
    ("2x + 3y = 12; x − y = 1", "(2, 3)", "", "Coordinates swapped"),
    ("x^2 + 5x + 6", "(x + 1)(x + 6)", "Factor.", "Wrong factoring"),
    ("3x + 5 = 3x − 1", "x = 2", "", "Wrong value"),
    ("2x + 4 = 2(x + 2)", "x = 0", "", "Wrong: every number works"),
    ("x + 1 = 3", "no solution", "", "Wrong: there is a solution"),
    ("x/(x − 2) = 2/(x − 2)", "x = 2", "", "Extraneous solution"),
    ("Simplify 3(2x − 4) − 2(x + 1).", "4x − 10", "", "Wrong expression"),
])
def test_wrong_keys_are_flagged(text, key, instr, etype):
    c = verdict(text, key, instr)
    assert c.verdict == VERDICT_WRONG, c.message
    assert c.error_type == etype, (c.error_type, c.message)


@pytest.mark.parametrize("text,key,instr,etype", [
    ("x^2 = 49", "x = 7", "", "Missing solution"),
    ("2x^2 − 18", "(2x + 6)(x − 3)", "Factor completely.", "Not completely factored"),
    ("1/4 + 1/2", "6/8", "Write in simplest form.", "Not in simplest form"),
])
def test_incomplete_keys(text, key, instr, etype):
    c = verdict(text, key, instr)
    assert c.verdict == VERDICT_INCOMPLETE, c.message
    assert c.error_type == etype


def test_wrong_answer_message_names_the_check():
    c = verdict("2x + 3 = 11", "x = −4")
    assert "left side = -5" in " ".join(c.checks)
    assert "x = 4" in c.message


def test_unreadable_key_goes_to_review():
    c = verdict("2x + 3 = 11", "see graph")
    assert c.verdict == VERDICT_REVIEW


@pytest.mark.parametrize("text", [
    "Maria has 3 more apples than Juan. Together they have 15. How many does Juan have?",
    "Prove that the sum of two even numbers is even.",
    "Graph y = 2x + 1.",
])
def test_unsupported_problems_are_not_guessed(text):
    with pytest.raises(Unsupported):
        solve_problem(P(text))


# ------------------------------------------------------------ helpers

def test_numbers_equal_rounding():
    assert numbers_equal(sp.pi, parse_math("3.14"), "3.14")
    assert not numbers_equal(sp.pi, parse_math("3.15"), "3.15")
    assert numbers_equal(sp.Rational(2, 3), parse_math("0.67"), "0.67")
    assert not numbers_equal(sp.Rational(2, 3), parse_math("0.66"), "0.66")


def test_exprs_equal():
    x = sp.Symbol("x")
    assert exprs_equal((x + 1) ** 2, x ** 2 + 2 * x + 1) is True
    assert exprs_equal((x + 1) ** 2, x ** 2 + 1) is False


# ------------------------------------------------------------ end to end on the sample book

def test_sample_book_end_to_end(tmp_path):
    from tests.make_sample import PLANTED_ERRORS, build
    from verifier.ingest import read_pdf
    from verifier.pipeline import run

    pdf = build(str(tmp_path / "book.pdf"))
    doc = read_pdf(pdf)
    rep = run(doc, list(range(len(doc.pages))), workers=0)
    flagged = {(r.problem.section, r.problem.number): r for r in rep.results
               if r.verdict in (VERDICT_WRONG, VERDICT_INCOMPLETE)}
    assert set(flagged) == set(PLANTED_ERRORS)
    for k, etype in PLANTED_ERRORS.items():
        assert flagged[k].error_type == etype, (k, flagged[k].error_type, flagged[k].message)
    others = [r for r in rep.results if (r.problem.section, r.problem.number) not in PLANTED_ERRORS]
    assert all(r.verdict == VERDICT_CORRECT for r in others), \
        [(r.problem.label, r.verdict, r.message) for r in others if r.verdict != VERDICT_CORRECT]
    # page numbers: book printed numbering starts at 10 on PDF page 2
    first = min(rep.results, key=lambda r: r.problem.page_index)
    assert first.problem.printed_page == 10 and first.problem.page_index == 1


# ------------------------------------------------------------ structure

def test_split_numbered_odd_only_key():
    from verifier.structure import _split_numbered
    assert _split_numbered("1. 4 3. −2 5. x = 7", None) == [(1, "4"), (3, "−2"), (5, "x = 7")]
    # ")" inside an answer must not split it
    assert _split_numbered("1. (x + 2)(x + 3) 2. (x − 1)", None) == [(1, "(x + 2)(x + 3)"), (2, "(x − 1)")]
    # decimals are not problem numbers
    assert _split_numbered("4. 3.5 5. 2.25", None) == [(4, "3.5"), (5, "2.25")]


def test_section_headings():
    from verifier.structure import section_from_text
    assert section_from_text("Lesson 4-1") == "4.1"
    assert section_from_text("Section 3.2 Exercises") == "3.2"
    assert section_from_text("2.5 Expressions and Functions") == "2.5"
    assert section_from_text("Chapter 3 Review") == "3 Review"
    assert section_from_text("1. 2x + 3 = 11") is None


def test_docx_worksheet(tmp_path):
    from verifier.ingest import find_soffice, read_document
    from verifier.pipeline import run
    if not find_soffice():
        pytest.skip("LibreOffice not installed")
    from docx import Document
    d = Document()
    d.add_heading("Lesson 4-1 Quadratic Equations", 1)
    d.add_paragraph("Solve each equation.")
    for runs in ([("x", 0), ("2", 1), (" − 7x + 12 = 0", 0)], [("3x + 2 = 17", 0)], [("x", 0), ("2", 1), (" = 81", 0)]):
        p = d.add_paragraph(style="List Number")
        for t, sup in runs:
            p.add_run(t).font.superscript = bool(sup)
    d.add_page_break()
    d.add_heading("Answers", 1)
    d.add_paragraph("Lesson 4-1")
    d.add_paragraph("1. x = 3, 4    2. x = 5    3. x = 9")
    path = tmp_path / "ws.docx"
    d.save(path)
    doc = read_document(str(path))
    rep = run(doc, list(range(len(doc.pages))), workers=0)
    v = {r.problem.number: r.verdict for r in rep.results}
    assert v == {1: VERDICT_CORRECT, 2: VERDICT_CORRECT, 3: VERDICT_INCOMPLETE}
