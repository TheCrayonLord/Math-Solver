"""Generate samples/sample_book.pdf: a small digital 'textbook' with an answer key in the back.

Some key answers are deliberately wrong (PLANTED_ERRORS) so the verifier can be tested.
Run:  python tests/make_sample.py
"""
from __future__ import annotations

import os

from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "samples", "sample_book.pdf")

FONT = "Helvetica"
for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "C:/Windows/Fonts/arial.ttf", "/Library/Fonts/Arial Unicode.ttf"):
    if os.path.exists(path):
        pdfmetrics.registerFont(TTFont("Body", path))
        FONT = "Body"
        break

# Each section: (id, title, instruction, problems[list of str], key answers[list of str])
# "^n" in a problem means "draw n as a superscript".  "[a|b]" means a stacked fraction a over b.
SECTIONS = [
    ("1.1", "Whole Numbers and Fractions", "Simplify. Write fractions in simplest form.",
     ["3/4 + 1/6", "2 1/2 + 3/4", "5 − 8 × 2", "(−3)^2 + 4", "[7|8] − [1|4]", "0.25 × 12",
      "18 ÷ 0.3", "2/3 × 9/10"],
     ["11/12", "3 1/4", "−11", "13", "5/8", "3", "60", "3/5"]),
    ("1.2", "Percents and Rounding", None,
     ["What is 15% of 80?", "18 is what percent of 72?", "Round 3.456 to the nearest tenth.",
      "Round 12,449 to the nearest hundred.", "Find the GCF of 24 and 36.",
      "Find the LCM of 6 and 8.", "Find the mean of 4, 8, 15, 16, 23, 42.",
      "Find the median of 7, 3, 9, 1, 5, 11."],
     ["12", "25%", "3.5", "12,400", "12", "24", "18", "6"]),
    ("2.1", "Solving Linear Equations", "Solve each equation. Check your solution.",
     ["2x + 3 = 11", "5x − 7 = 3x + 9", "4(x − 2) = 20", "x/3 + 2 = 7", "−3x + 4 = 19",
      "0.5x − 1.2 = 2.3", "7 − 2(x + 1) = 3x", "6x + 2 = 2(3x + 1)", "3x + 5 = 3x − 1",
      "2/3 x = 8"],
     ["x = 4", "x = 8", "x = 7", "x = 15", "x = −5", "x = 7", "x = 1", "all real numbers",
      "no solution", "x = 12"]),
    ("2.2", "Inequalities and Systems", "Solve. Write the solution as an inequality or an ordered pair.",
     ["3x − 4 > 8", "−2x + 1 ≤ 9", "−1 < 2x + 3 ≤ 11", "x + y = 10; x − y = 2",
      "2x + 3y = 12; x − y = 1", "y = 2x + 1; y = −x + 7"],
     ["x > 4", "x ≥ −4", "−2 < x ≤ 4", "(6, 4)", "(3, 2)", "(2, 5)"]),
    ("2.3", "Quadratics and Factoring", "Factor completely.",
     ["x^2 + 5x + 6", "x^2 − 9", "2x^2 − 18", "x^2 + 4", "3x^2 + 6x"],
     ["(x + 2)(x + 3)", "(x + 3)(x − 3)", "(2x + 6)(x − 3)", "prime", "3x(x + 2)"]),
    ("2.4", "Solving Quadratic Equations", "Solve each equation.",
     ["x^2 − 5x + 6 = 0", "x^2 = 49", "x^2 + 2x − 15 = 0", "2x^2 − 8 = 0", "x^2 + 6x + 9 = 0"],
     ["x = 2, 3", "x = 7", "x = −5, 3", "x = ±2", "x = −3"]),
    ("2.5", "Expressions and Functions", None,
     ["Evaluate 3x^2 − 2x + 1 when x = −2.", "If f(x) = 2x^2 − 3x, find f(4).",
      "Find the slope through (1, 2) and (4, 11).", "Simplify 3(2x − 4) − 2(x + 1).",
      "Expand (x + 4)(x − 2).", "Simplify √50."],
     ["17", "20", "3", "4x − 14", "x^2 + 2x − 8", "5√2"]),
]

# Key answers deliberately changed to be wrong
PLANTS = {
    ("1.1", 5): "3/8",        # correct 5/8
    ("1.1", 7): "6",          # decimal point, correct 60
    ("1.2", 6): "48",         # correct LCM is 24
    ("1.2", 2): "4%",         # correct 25%
    ("1.2", 3): "3.4",        # rounding error, correct 3.5
    ("2.1", 2): "x = −8",     # sign error, correct 8
    ("2.1", 5): "x = 5",      # sign error, correct −5
    ("2.1", 6): "x = 7.5",    # wrong, correct 7
    ("2.2", 5): "(2, 3)",     # swapped, correct (3, 2)
    ("2.2", 2): "x ≤ −4",     # sign not flipped, correct x ≥ −4
    ("2.2", 6): "(5, 2)",     # swapped, correct (2, 5)
    ("2.4", 2): "x = 7",      # missing −7 (already incomplete)
    ("2.5", 1): "15",         # correct 17
}
# Every key problem the verifier should report: (section, number) -> expected error type
PLANTED_ERRORS = {
    ("1.1", 5): "Wrong value", ("1.1", 7): "Decimal point error", ("1.2", 6): "Wrong value",
    ("1.2", 2): "Wrong value", ("1.2", 3): "Rounding error",
    ("2.1", 2): "Sign error", ("2.1", 5): "Sign error", ("2.2", 5): "Coordinates swapped", ("2.1", 6): "Wrong value", ("2.2", 2): "Inequality sign reversed",
    ("2.2", 6): "Coordinates swapped", ("2.4", 2): "Missing solution", ("2.5", 1): "Wrong value",
    ("2.3", 3): "Not completely factored",
}


def draw_math(c: canvas.Canvas, x: float, y: float, s: str, size: float = 11) -> float:
    """Draw text with ^superscripts and [a|b] stacked fractions. Returns end x."""
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "^":
            j = i + 1
            while j < len(s) and s[j].isalnum():
                j += 1
            sup = s[i + 1:j]
            c.setFont(FONT, size * 0.65)
            c.drawString(x, y + size * 0.4, sup)
            x += c.stringWidth(sup, FONT, size * 0.65)
            i = j
            continue
        if ch == "[":
            j = s.index("]", i)
            num, den = s[i + 1:j].split("|")
            c.setFont(FONT, size)
            w = max(c.stringWidth(num, FONT, size), c.stringWidth(den, FONT, size)) + 2
            c.drawString(x + (w - c.stringWidth(num, FONT, size)) / 2, y + size * 0.55, num)
            c.drawString(x + (w - c.stringWidth(den, FONT, size)) / 2, y - size * 0.75, den)
            c.setLineWidth(0.6)
            c.line(x, y + size * 0.33, x + w, y + size * 0.33)
            x += w + 2
            i = j + 1
            continue
        j = i
        while j < len(s) and s[j] not in "^[":
            j += 1
        chunk = s[i:j]
        c.setFont(FONT, size)
        c.drawString(x, y, chunk)
        x += c.stringWidth(chunk, FONT, size)
        i = j
    return x


def build(path: str = OUT) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    c = canvas.Canvas(path, pagesize=letter)
    W, H = letter
    printed = 10  # book starts at printed page 10 (front matter offset)

    def footer():
        c.setFont(FONT, 9)
        c.drawCentredString(W / 2, 30, str(printed))

    # title page (no page number)
    c.setFont(FONT, 20)
    c.drawString(72, H - 120, "Sample Algebra Workbook")
    c.setFont(FONT, 11)
    c.drawString(72, H - 150, "For testing the answer-key verifier.")
    c.showPage()
    printed_start = printed

    for sec_i, (sid, title, instr, probs, _) in enumerate(SECTIONS):
        y = H - 72
        c.setFont(FONT, 14)
        c.drawString(72, y, f"{sid} {title}")
        y -= 28
        if instr:
            c.setFont(FONT, 11)
            c.drawString(72, y, instr)
            y -= 24
        # two columns
        half = (len(probs) + 1) // 2
        for col, chunk in enumerate((probs[:half], probs[half:])):
            yy = y
            for k, p in enumerate(chunk):
                n = k + 1 + (half if col else 0)
                x = 72 if col == 0 else 320
                draw_math(c, x, yy, f"{n}.  {p}")
                yy -= 30
        footer()
        c.showPage()
        printed += 1

    # answer key
    c.setFont(FONT, 16)
    y = H - 72
    c.drawString(72, y, "Selected Answers")
    y -= 30
    for sid, title, _, probs, key in SECTIONS:
        if y < 120:
            footer(); c.showPage(); printed += 1; y = H - 72
        c.setFont(FONT, 12)
        c.drawString(72, y, f"{sid} {title}")
        y -= 20
        answers = []
        for n, a in enumerate(key, 1):
            a = PLANTS.get((sid, n), a)
            answers.append(f"{n}. {a}")
        line = ""
        for a in answers:
            trial = (line + "    " + a) if line else a
            if c.stringWidth(trial, FONT, 11) > W - 144:
                draw_math(c, 72, y, line)
                y -= 18
                line = a
            else:
                line = trial
        if line:
            draw_math(c, 72, y, line)
            y -= 26
    footer()
    c.showPage()
    c.save()
    return path


if __name__ == "__main__":
    print(build())
