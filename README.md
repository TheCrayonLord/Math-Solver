# Answer Key Checker

Drop in a math book or worksheet (digital **PDF** or **.docx**). The program finds every problem on
the pages you choose, solves each one exactly, compares the result with the answer key in the back
of the book, and tells you **what is wrong and on which page**.

Everything runs on your own computer. Nothing is uploaded, and no paid services are used.

```
❌ Page 12 (PDF page 4) — Section 2.1, #2   [Sign error]
   Problem: 5x − 7 = 3x + 9
   Key says (page 17, PDF page 9): x = −8
   Correct answer: x = 8
   What's wrong: The key says x = −8, but x = -8 does not satisfy the equation.
                 The correct answer is x = 8. The key has the opposite sign.
     · Check x = -8 in 5x - 7 = 3x + 9: left side = -47, right side = -15 ✗
```

## Install (once)

1. Install **Python 3.10 or newer** from <https://www.python.org/downloads/>.
   On Windows, tick **"Add Python to PATH"** during setup.
2. *(Only for .docx files)* Install **LibreOffice** (free) from <https://www.libreoffice.org/>.
   PDFs don't need it.

## Start

- **Windows:** double-click `start_windows.bat`
- **Mac / Linux:** double-click `start_mac_linux.command` (or run `./start_mac_linux.command` in a terminal)

The first start installs the needed packages, then the app opens in your web browser.
To stop it, close the black terminal window.

Manual start: `pip install -r requirements.txt` then `streamlit run app.py`.

## Using it

1. Drop the PDF/.docx onto the page.
2. In the left panel choose **All pages** or **Choose pages** (e.g. `12-30, 45`). You can type the
   page numbers printed in the book or the PDF's own page numbers.
3. Check that the answer key pages were found (or type them yourself), then press **Check answers**.
4. Read the results:

| Result | Meaning |
|---|---|
| ❌ Key is wrong | The key's answer is wrong. You'll see the correct answer, the type of mistake, and a plug-in check that proves it |
| ⚠️ Key is incomplete | Partly right, e.g. a missing solution (`x = ±7` written as `x = 7`), not completely factored, not in simplest form |
| ✅ Correct | Matches. Equivalent forms count: `1/2 = 0.5 = .5 = 50%`, `(x+1)² = x²+2x+1`, `x = ±3` = `x = 3, −3` |
| 🔍 Needs review | Couldn't be checked automatically (e.g. word problems, proofs, graphs). Never guessed |
| ➖ No key entry | The key has no answer for this problem (e.g. odd answers only) |

Download everything as a CSV file with **Download results**.

### Command line

```
python -m verifier book.pdf                          # all pages
python -m verifier book.pdf --pages 112-130 --printed # pages as printed in the book
python -m verifier book.pdf --key-pages 600-650 --csv results.csv --all
```

## What it can check today

Grades K–8 and Algebra 1:

- arithmetic with fractions, mixed numbers, decimals, and order of operations
- percents ("15% of 80", "18 is what percent of 72"), rounding, GCF/LCM, mean/median/mode/range
- linear equations, including no solution and all real numbers
- quadratic and absolute-value equations; finds missing and extraneous solutions
- literal equations ("solve for y"), inequalities (including compound), and 2–3 variable systems
- simplifying, expanding, and factoring, with checks for "completely factored"
- evaluating expressions and functions, and the slope through two points
- radicals including cube roots, distance and midpoint, parallel/perpendicular slopes,
  equations of lines (slope-intercept), and standard deviation (population or sample)
- multiple choice: checks the key's letter and that any answer written next to it matches

Layouts it understands: section-numbered books ("3.2", "Lesson 3-2"), keys organized by page
("Page 10 · Multi-Step Equations"), two-column pages, worksheet tables and grids, `1.` or `1)`
numbering, answers that wrap onto the next line, and example boxes and "Answer: ____" blanks,
which are ignored.

The next phases add Geometry, Algebra 2, Precalculus, Calculus (AB/BC/1/2/3), AP Statistics, and
Differential Equations. See [PLAN.md](PLAN.md).

## How it stays accurate

- Problems are solved with exact computer algebra (SymPy), not estimates.
- A key is only reported wrong if its answer **fails a direct check** (e.g. plugging it back into the
  equation). If the key's answer checks out but differs from the solver, the problem goes to
  🔍 review instead.
- If most answers in a section disagree, the program assumes a page-reading or matching problem,
  not 20 key errors, and sends those problems to review.
- Answer keys that are shifted by one problem are detected and reported once.
- Anything it doesn't understand (word problems, proofs, graphs) is sent to review, never guessed.

## Limits right now

- Digital PDFs only (with selectable text). Scanned pages aren't supported yet.
- Word problems go to review. An optional free local AI translator is planned (PLAN.md, phase 7).
- Math drawn as images, or unusual equation layouts, may not be read. Problems with rebuilt stacked
  fractions carry a note to double-check them.

## Development

```
pip install -r requirements.txt pytest reportlab python-docx
python tests/make_sample.py      # regenerates samples/sample_book.pdf (has planted key errors)
python -m pytest -q
```
