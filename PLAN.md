# Math Answer-Key Verifier — Project Plan (v2)

## 1. Goal

A free program that runs on your own computer. You drop in a **digital PDF** (or `.docx`) of a math book or worksheet, pick which pages to check (or all), and the program:

1. Pulls every problem off the selected pages.
2. Reads the answer key at the back of the book and matches each key entry to its problem.
3. Solves each problem on its own, without looking at the key.
4. Compares its answer with the key.
5. For every mismatch, reports **what is wrong** and **on which page**: the problem's page and the key entry's page.

**Accuracy matters most.** If the program can't verify a problem with confidence, it says "Needs review". It never guesses.

**Decisions so far**

| Topic | Decision |
|---|---|
| Where it runs | Your own computer, as a local web page (opens in your browser at `localhost`). No hosting, no account |
| Cost | **No paid APIs.** All solving runs locally with free, open-source tools |
| Input | Digital PDFs (with real, selectable text). `.docx` is also supported. Scanned books are out of scope for now |
| Equivalent answers | `1/2`, `0.5`, `.5`, and `50%` (where a percent makes sense) all count as **equal**. So do other equivalent forms, like `(x+1)²` = `x²+2x+1` |
| Corrections | **Out of scope.** The program reports problems; it does not edit files |

**Courses:** Grades K–8, Algebra 1, Geometry, Algebra 2, Precalculus, Calculus AB, Calculus BC, AP Statistics, Calculus 1, Calculus 2, Calculus 3, Differential Equations.

---

## 2. How solving works without a paid AI

Ruling out the Claude API changes the design. The core becomes **computer algebra (SymPy/SciPy)**, which is exact and fully trustworthy once a problem has been translated into math correctly. The hard part is the *translation*: turning book text into something SymPy can run.

Problems are routed through tiers, from most reliable to least:

```
problem text
    │
    ▼
┌─────────────────────────────────────────┐
│ Tier 1: Rule-based parsing (no AI)      │  "Solve 3x − 7 = 11", "Find dy/dx if y = x²sin x",
│ instruction pattern + math expression   │  "Evaluate ∫₀² x³ dx", "Simplify (x²−9)/(x−3)"
│ → SymPy → exact answer                  │  Expected to cover most drill/practice problems
└────────────────┬────────────────────────┘
                 │ can't parse
                 ▼
┌─────────────────────────────────────────┐
│ Tier 2: Local AI translator (optional)  │  Word problems, geometry with given values,
│ free open-source model on your computer │  stats scenarios. The AI only WRITES the setup
│ (via Ollama) → SymPy code → run it      │  (equations/code). SymPy computes the answer.
└────────────────┬────────────────────────┘
                 │ can't translate confidently
                 ▼
┌─────────────────────────────────────────┐
│ Tier 3: Needs human review              │  Proofs, "explain", sketch-a-graph, problems
│ shown with page, problem, and key answer│  that depend on a picture the program can't read
└─────────────────────────────────────────┘
```

### Tier 1: rule-based parsing (the reliable core)
- Detect the **instruction** ("Solve", "Simplify", "Factor", "Evaluate", "Find the derivative", "Integrate", "Find the limit", "Find the slope", …), including instructions written once above a group of problems ("Solve each equation. Round to the nearest tenth.").
- Parse the **math expression** into SymPy using `sympy.parsing` (plain-text math) and `latex2sympy2` (for math rebuilt as LaTeX; see §4).
- Map instruction → SymPy operation (`solveset`, `simplify`, `factor`, `diff`, `integrate`, `limit`, `dsolve`, `Matrix` ops, etc.).
- Fully deterministic and repeatable. No AI is involved, so no AI mistakes.

### Tier 2: local AI translator (optional, free)
- Runs a free open-source math model on your computer through **Ollama** (candidates to compare: Qwen2.5-Math-7B, Qwen3-8B, DeepSeek-R1-Distill-Qwen-7B; we choose based on our own benchmark).
- The AI is **never trusted for the answer**. It only writes the setup (equations or SymPy code); SymPy does the arithmetic.
- Safety checks on what the AI produces:
  - Run the translation **3 times**. If the setups give different answers → Needs review.
  - Plug the result back into the problem's stated conditions where possible.
  - The key is only flagged wrong if the translated setup is consistent *and* the key fails a direct check (below).
- **Hardware:** roughly 8 GB of free RAM (16 GB recommended). A GPU makes it faster but isn't required. If your computer can't run it, Tier 2 is skipped and those problems go to Needs review. The rest of the program works normally.

### Direct check of the key's answer (any tier)
Whenever possible, the program checks the **key's** answer directly instead of only comparing it with its own:
- Plug roots into the equation; test points for inequalities.
- Differentiate the key's antiderivative and compare with the integrand.
- Substitute the key's DE solution into the equation and the initial conditions (`checkodesol`).
- Expand the key's factored form; evaluate the key's limit numerically.

**When a key is reported wrong:** the program's answer must come from a successful solve, the key's answer must *fail* the direct check (where one exists), and the equivalence engine (§6) must confirm the two really differ. Otherwise the problem goes to "Needs review".

---

## 3. Verdicts

| Verdict | Meaning |
|---|---|
| ✅ **Correct** | Key matches the computed answer (any equivalent form) |
| ❌ **Key is wrong** | Confident mismatch. Report gives the specifics and pages |
| ⚠️ **Key is incomplete** | Partly right: missing a solution, wrong rounding, missing `+ C`, missing units |
| 🔍 **Needs review** | Couldn't verify confidently (proof, graph, ambiguous wording, solvers disagree) |
| ➖ **No key entry** | Problem has no answer in the key (e.g. odd answers only). Still solved and listed |
| ⛔ **Couldn't read** | Text extraction failed for that problem |

---

## 4. Reading digital PDFs

Digital PDFs have a text layer, but math is often stored awkwardly: fractions as two lines stacked up, exponents as smaller raised text, symbols in special fonts. Plan:

1. **PyMuPDF** extracts every character with its **position, font, and size**.
2. A **math rebuild step** uses that layout information:
   - Smaller, raised text → exponent (`x2` with a raised "2" → `x^2`)
   - Lowered text → subscript
   - Text stacked above and below a horizontal line → fraction
   - Symbol-font characters mapped to real symbols (√, ∫, π, θ, ≤, …)
   - Radical signs with an overline → square root
3. **Cross-check with a free local math OCR model** (e.g. `pix2tex` / LaTeX-OCR, or the Texify/Marker models): render the problem as an image and read the math a second way. If the two readings disagree mathematically → the problem is marked ⛔/🔍 instead of being solved from possibly wrong text. This is the main protection against reading errors.
4. Figures (graphs, triangles, tables) are saved as images and linked to their problems. Tables of numbers (common in stats) are extracted as data.

**`.docx` files:** read with `python-docx`. Word equations (OMML) are converted to LaTeX, then to SymPy. Word's automatic numbering is rebuilt so problem numbers are correct. Page numbers come from rendering the `.docx` to PDF with LibreOffice (only used to label pages).

---

## 5. Pages, problems, and the answer key

### Page selection
- The page shows thumbnails of the uploaded PDF. Choose **All pages** or type ranges like `12-30, 45, 51-60`.
- The program reads the **printed page numbers** (the numbers in the book's corners) and works out the difference from the PDF's page count. Both are shown everywhere: *"Page 147 (PDF page 163)"*.
- The answer key section is found automatically (headings like "Answers", "Selected Answers", "Answer Key"). You can confirm it or type its page range.

### Problem extraction
Each problem is stored with: chapter/section, problem number and part (17b), **printed page and PDF page**, the instruction that applies to it, the math, any shared context ("Use the table for Exercises 15–20"), and linked figures.

### Answer key matching
- Key entries are parsed into `(section, problem number, part) → answer`, with the **key's page number** recorded.
- Handles multi-column keys, odd-only keys, and answers that continue onto the next column or page.
- **Shift detection:** if a run of answers would all match after shifting by one problem, the program reports *"Answers for Section 3.2, #14–20 appear shifted by one"* once, instead of seven separate errors.

---

## 6. Comparing answers (equivalence engine)

This is what stops false alarms. Two answers are treated as **equal** when:

| Answer type | Rule |
|---|---|
| Numbers | Same value: `1/2 = 0.5 = .5 = 50%`. Decimals are compared at the book's rounding instruction (e.g. "nearest tenth"), otherwise within a small tolerance for rounded values |
| Expressions | `simplify(a − b) = 0`, **and** the two agree at 20+ random points (catches SymPy mistakes in both directions) |
| Equations | Same solutions, or one equation is a multiple of the other |
| Solution sets | Same set, any order (`x = 3, −3` = `x = ±3`) |
| Inequalities / intervals | Same set (`x > 2` = `(2, ∞)`), including open vs. closed endpoints |
| Points, vectors | Same coordinates in order |
| Matrices | Same entries (eigenvectors: equal up to scaling) |
| Indefinite integrals | Key's derivative equals the integrand. Differing by a constant is fine. Missing `+ C` → ⚠️ |
| Trig equations | Same solutions on the requested interval, or the same general solution |
| DE general solutions | Satisfies the equation; constants may be renamed or combined |
| Units | Converted with `pint` (`12 in` = `1 ft`). Missing or wrong units → ⚠️ |
| Multiple choice | Letter matches. Also checks that the option's content is the correct answer |
| Stats | Small tolerance for table-vs-calculator differences (e.g. z-table rounding) |

---

## 7. The report: specific and page-exact

Each ❌ / ⚠️ item looks like:

> **❌ Page 147 (PDF 163) — Section 3.2, Problem 17b**
> **Problem:** Solve 2x + 3 = 11
> **Key (page 612, PDF 628) says:** x = −4
> **Correct answer:** x = 4
> **What's wrong:** Sign error. Substituting the key's answer: 2(−4) + 3 = −5, not 11. Substituting x = 4: 2(4) + 3 = 11 ✓.
> **Steps:** 2x + 3 = 11 → 2x = 8 → x = 4

The "What's wrong" line names the **type** of error whenever it can be identified:
- Sign error, arithmetic error, or wrong value (with the substitution check shown)
- Missing solution(s), e.g. "x² = 9 also has x = −3", or extra/extraneous solution(s)
- Rounding error ("12.47 rounds to 12.5, not 12.4")
- Missing `+ C`, missing units, wrong endpoint (open vs. closed)
- Answer belongs to a different problem / key shifted
- Wrong multiple-choice letter (the letter given is option B = 7, but the answer is 9 = option D)

**Summary at the top:** number of problems checked, counts for each verdict, and a list of every error by page. Results can be downloaded as **PDF** or **CSV**.

---

## 8. Strategy by course

| Course | Main problem types | How they're verified |
|---|---|---|
| **K–8** | Arithmetic, fractions, decimals, percents, ratios, unit conversion, area/perimeter, mean/median/mode | Exact fractions (`Fraction`), `pint` for units. Word problems → Tier 2 |
| **Algebra 1** | Linear equations/inequalities, systems, slope, exponents, polynomials, factoring, quadratics, radicals | `solveset`, `linsolve`, `factor`, `expand`; plug-in checks |
| **Geometry** | Angles, triangles, Pythagorean theorem, trig ratios, circles, area/volume, coordinate geometry | Formula library plus SymPy. Problems needing values read off a figure → Tier 2 or review. Proofs → review |
| **Algebra 2** | Polynomials, rational, exponential/log, sequences/series, complex numbers, matrices, conics, probability | Solve over complex numbers; check for extraneous roots and domains |
| **Precalculus** | Trig identities and equations, inverse trig, polar/parametric, vectors, intro limits | `trigsimp`; random-point testing for identities; interval-aware solution sets |
| **Calc AB / Calc 1** | Limits, derivatives, implicit differentiation, related rates, optimization, integrals, FTC | `limit`, `diff`, `idiff`, `integrate`; numerical double-checks (mpmath) |
| **Calc BC / Calc 2** | Integration techniques, improper integrals, series, Taylor polynomials, polar/parametric calculus | `integrate`, `series`, `summation`; numeric partial sums and integrals |
| **AP Stats** | Descriptive stats, regression, probability, distributions, CIs, hypothesis tests | SciPy/statsmodels recomputation from the data; tolerance for table values |
| **Calc 3** | Vectors, partial derivatives, gradients, multiple and line/surface integrals | Iterated integrals in two orders; numeric integration cross-check |
| **Diff Eqs** | Separable, linear, exact, 2nd order, Laplace, systems | `dsolve`, `laplace_transform`; **substitute the key's solution** into the equation; numeric ODE solve |

**Expected coverage:** drill problems in Algebra through Calculus and Diff Eqs (most of a typical exercise set) are handled by Tier 1 with very high accuracy. Word problems, geometry figures, and stats scenarios depend on Tier 2 and will have a higher Needs review rate. Proofs and sketches are always Needs review.

---

## 9. Technology (all free)

| Part | Tool |
|---|---|
| Language | Python 3.12 |
| Local web page | **Streamlit**: one command (`math-verifier`) opens the app in your browser. Has drag-and-drop upload, page picker, and results tables built in |
| PDF reading | PyMuPDF |
| DOCX reading | python-docx (+ OMML→LaTeX conversion) |
| Math OCR cross-check | pix2tex (LaTeX-OCR) or Texify, running locally |
| Math parsing | SymPy parser, latex2sympy2 |
| Solving | SymPy, SciPy, NumPy, mpmath, statsmodels, pint |
| Local AI (optional) | Ollama + an open-source math model |
| Install | `pip install` package, plus an optional Windows/Mac installer later |

Safety: AI-written SymPy code runs in a separate process with a time limit, no network, and only math libraries allowed.

---

## 10. Proving accuracy

1. **Test books:** free textbooks (OpenStax Prealgebra, Algebra 1/2, Precalculus, Calculus Vol. 1–3, Statistics, plus free K–8 and Diff Eq materials). Their keys serve as a starting ground truth.
2. **Planted errors:** copy real keys and insert realistic mistakes (sign flips, dropped roots, bad rounding, missing `+C`, answers shifted by one, wrong letters). Measure how many are caught.
3. **Equivalent-form tests:** thousands of pairs that must **not** be flagged (`1/2` vs `0.5`, `(x+1)²` vs `x²+2x+1`, alternate antiderivatives, alternate DE solution forms).
4. **Targets, measured for each course:**
   - Of the items flagged ❌, **≥ 99% are real errors** (precision)
   - Of the real errors, **≥ 95% are caught** (recall) among problems that weren't sent to review
   - Needs review rate is reported for each course so you know the coverage
5. Every code change reruns these tests automatically.

---

## 11. Project layout

```
math-solver/
├── app.py                 # Streamlit UI: upload, page picker, results
├── verifier/
│   ├── ingest/            # pdf_reader.py, math_rebuild.py, docx_reader.py, ocr_check.py, page_numbers.py
│   ├── extract/           # problems.py, instructions.py, answer_key.py, matcher.py
│   ├── solve/
│   │   ├── router.py      # picks Tier 1 / 2 / 3 and the course strategy
│   │   ├── rules/         # Tier 1 instruction → SymPy handlers, one file per topic
│   │   ├── local_ai.py    # Tier 2 (Ollama) translator + consistency checks
│   │   ├── sandbox.py     # safe runner for generated code
│   │   └── checks/        # direct key verification (plug-in, differentiate, checkodesol, …)
│   ├── compare/           # equivalence engine, error-type diagnosis, shift detection
│   └── report/            # on-screen report, PDF/CSV export
├── eval/                  # test books, planted-error generator, accuracy metrics
└── tests/
```

---

## 12. Build order

| Phase | What gets built | Done when |
|---|---|---|
| **1. Skeleton** | Streamlit app, PDF upload, page picker with printed/PDF page numbers, test harness | Upload a PDF, choose pages, see them listed |
| **2. Extraction** | Problem extraction, math rebuild from PDF layout, answer-key detection and matching | ≥ 98% of problems and key entries read correctly on test books |
| **3. Algebra 1 + K–8 solving** | Tier 1 rules, equivalence engine, direct checks, report with error types and pages | ❌ precision ≥ 99% on planted-error tests |
| **4. Algebra 2, Precalc, Geometry** | Trig, logs, complex, intervals, geometry formulas | Targets met for each course |
| **5. Calculus (AB/BC/1/2/3) + Diff Eqs** | Limits, derivatives, integrals, series, multivariable, ODE checks | Targets met for each course |
| **6. AP Stats** | Table/data extraction, stats recomputation, tolerances | Targets met |
| **7. Local AI (Tier 2) + OCR cross-check** | Ollama integration, word-problem translation, math OCR double-read | Lower review rate without losing precision |
| **8. Polish** | `.docx` input, PDF/CSV export, installer, shift detection and summaries | Ready for everyday use |

---

## 13. Honest limits

- **Without a paid AI, word problems are the weak spot.** The free local model helps, but more of them will land in "Needs review" than with a top paid model. Drill-style problems (most textbook exercises) are not affected, since they're solved by exact computer algebra.
- **Proofs, "explain your reasoning", and sketch-the-graph** answers can't be checked automatically. They're listed as Needs review with the page number.
- **Scanned books** aren't supported in this version. Digital PDFs only.
