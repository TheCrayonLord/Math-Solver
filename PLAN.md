# Math Answer-Key Verifier — Project Plan

## 1. Goal

Users drop in a textbook or worksheet (`.pdf` or `.docx`). The program:

1. Pulls out every problem on the pages the user picks (or all pages).
2. Finds the answer key, usually at the back of the book, and matches each key entry to its problem.
3. Solves each problem on its own, without looking at the key.
4. Compares its answer with the key's answer.
5. For each mismatch, says **exactly what is wrong and what it should change to**, with a worked solution.

**Accuracy matters most.** When the program isn't sure, it says so and flags the item for human review. It never presents a guess as a finding.

**Nice to have:** write the corrections into the `.docx` (as tracked changes) and export the corrected document to PDF.

### Subjects in scope

| Group | Courses |
|---|---|
| Elementary / middle | Grades K–8 (arithmetic, fractions, decimals, ratios, percents, basic geometry, pre-algebra, intro stats) |
| High school | Algebra 1, Geometry, Algebra 2, Precalculus |
| AP | Calculus AB, Calculus BC, AP Statistics |
| College | Calculus 1, Calculus 2, Calculus 3 (multivariable), Differential Equations |

---

## 2. Core design principle: solve it two ways and agree

One solver can't be trusted for accuracy. Each problem goes through **independent paths**, and the system only reports a confident verdict when they agree:

```
            ┌──────────────────────┐
problem ──▶ │ A. LLM reasoning     │──▶ answer A ─┐
            │    solve (run ×N)    │              │
            ├──────────────────────┤              ├─▶ consensus ─▶ compare with key ─▶ verdict
            │ B. CAS / numeric     │──▶ answer B ─┤
            │    solve (SymPy,     │              │
            │    SciPy, etc.)      │              │
            ├──────────────────────┤              │
            │ C. Back-substitution │──▶ check  ───┘
            │    verify key answer │
            └──────────────────────┘
```

- **A. LLM solver** (Claude via the Anthropic API): reads the problem as given, including diagrams, solves it step by step, and returns a structured final answer. It runs several times on its own (self-consistency); answers that don't agree across runs lower confidence.
- **B. Computer algebra / numeric solver:** the LLM translates the problem into executable SymPy/SciPy code, and the code is run in a sandbox. This gives an exact or high-precision answer that doesn't depend on the LLM's arithmetic.
- **C. Direct verification of the key:** whenever possible, check the *key's* answer directly. Plug roots back into the equation, differentiate an antiderivative, substitute a DE solution into the equation, check a probability sums to 1, and so on. This is often the strongest evidence of all.

**When the program flags a key answer as wrong:** at least two independent paths must agree with each other and disagree with the key, and path C (where it applies) must show the key fails. Anything less goes to "Needs review", not "Key is wrong".

---

## 3. Verdicts

Every problem gets exactly one verdict:

| Verdict | Meaning | Shown to user as |
|---|---|---|
| ✅ **Correct** | Key matches the verified answer, allowing for equivalent forms | Green |
| ❌ **Key is wrong** | High-confidence mismatch; paths agree and the key fails verification | Red, with a correction |
| ⚠️ **Key incomplete / mis-formatted** | Partly right, e.g. one of two roots missing, wrong rounding, missing units, missing `+ C` | Orange, with a correction |
| 🔍 **Needs human review** | Solvers disagree, the problem is ambiguous, or the answer type can't be checked automatically (proofs, sketches) | Yellow, with reasoning |
| ➖ **No key entry** | Problem has no answer in the key (e.g. the key covers odd problems only) | Gray. Still solved, but not compared |
| ⛔ **Could not parse** | Extraction failed (unreadable scan, figure not captured) | Gray, with the page image |

---

## 4. "What exactly is wrong": report format

Each ❌ or ⚠️ item includes:

- **Location:** page number (printed *and* PDF index), section, problem number, and the key's page and line.
- **Problem text**, rendered as LaTeX/MathJax, plus a cropped image of the original.
- **Key says:** the key's answer exactly as printed.
- **Correct answer:** in the same style and format as the book (e.g. if the book writes `x = 3/2`, don't answer `1.5`).
- **What's wrong:** a specific diagnosis, e.g.:
  - "Sign error: the key gives `x = −4`, but substituting gives `2(−4)+3 = −5 ≠ 11`. The solution is `x = 4`."
  - "Missing solution: `x² = 9` has two solutions, `x = ±3`. The key lists only `x = 3`."
  - "Rounding: the book's instructions say to round to the nearest tenth. `12.47 → 12.5`, not `12.4`."
  - "Answer belongs to a different problem: the key's #14 answer matches problem #15. Keys for #14–#20 may be shifted by one."
- **Change to:** the exact replacement text for the key entry.
- **Worked solution:** the steps that lead to the correct answer.
- **Evidence and confidence:** which paths agreed, the verification results, and a confidence score.

**Pattern detection across problems:** the program looks for systematic errors, such as a key shifted by one problem, a whole section keyed to the wrong edition, or rounding applied in the wrong place everywhere. It reports these once as a group instead of 20 separate errors.

Output formats: an interactive HTML report in the app, plus downloadable **PDF**, **DOCX**, and **CSV/JSON** versions.

---

## 5. System architecture

```
┌──────────────┐   ┌──────────────┐   ┌───────────────┐   ┌─────────────┐   ┌──────────────┐
│ 1. Ingest    │──▶│ 2. Structure │──▶│ 3. Align with │──▶│ 4. Solve &  │──▶│ 5. Compare & │
│ PDF / DOCX   │   │ problems &   │   │ answer key    │   │ verify      │   │ report       │
│ → pages+math │   │ key entries  │   │               │   │             │   │              │
└──────────────┘   └──────────────┘   └───────────────┘   └─────────────┘   └──────┬───────┘
                                                                                    │ (optional)
                                                                            ┌───────▼────────┐
                                                                            │ 6. Apply fixes │
                                                                            │ DOCX → PDF     │
                                                                            └────────────────┘
```

### Tech stack (recommended)

| Layer | Choice | Why |
|---|---|---|
| Language | **Python 3.12** | Best ecosystem for math (SymPy, SciPy, statsmodels) and documents |
| Backend API | **FastAPI** | Async, easy file uploads, streams progress |
| Job queue | **Celery + Redis** (or RQ) | A 600-page book takes minutes; run jobs in the background with progress updates |
| Frontend | **React + TypeScript**, MathJax/KaTeX for math, PDF.js for page previews | Drag-and-drop, page picker, side-by-side review |
| PDF | **PyMuPDF** (text, layout, page rendering) | Fast, gives positions, renders crops |
| DOCX | **python-docx** + raw OOXML handling for equations (OMML) | Equations in Word are OMML and need conversion to LaTeX |
| Math OCR | **Claude vision**, with optional **Mathpix** as a second reader | Scanned pages and equations stored as images |
| LLM | **Claude (Opus-class for solving, cheaper model for extraction/triage)** via Anthropic API | Strong math reasoning plus vision |
| CAS | **SymPy**, **SciPy**, **NumPy**, **mpmath** (high precision), **statsmodels** for stats | Exact, checkable answers |
| Code sandbox | Isolated subprocess / container with time and memory limits, no network | Runs LLM-generated CAS code safely |
| DOCX → PDF | **LibreOffice headless** (`soffice --convert-to pdf`) | Free and dependable; preserves layout well |
| Storage | SQLite (single user) → Postgres (multi-user) | Jobs, problems, verdicts, user overrides |

Deployment: start as a **local web app** (run on the user's machine, open `localhost`) so textbooks never leave the machine except for API calls. A Docker image bundles LibreOffice and the Python stack.

---

## 6. Pipeline details

### 6.1 Ingestion

**PDF**
- Extract text with positions using PyMuPDF.
- Check each page: is there a real text layer? If the page is scanned or text is garbled, render it to an image (300 DPI) and run math OCR.
- Equations are often broken in PDF text layers (fractions split across lines, missing symbols). **Policy:** any problem with math gets a vision pass over a cropped image of that problem, and the vision transcript is checked against the text layer. Disagreements are flagged.
- Extract figures (diagrams, graphs, tables) as images tied to their problems. Geometry and calculus problems often depend on them.

**DOCX**
- Walk the document body in order: paragraphs, tables, numbered lists, images.
- Convert OMML equations to LaTeX (via the standard OMML→MathML XSLT, then MathML→LaTeX).
- Rebuild automatic list numbering (Word stores "1., 2., 3." as list formatting, not text). Problem numbers depend on this.
- Record a **location anchor** for each problem and key entry (paragraph index and run range). The fix-applying feature needs these.
- Page numbers: `.docx` has no fixed pages. Render to PDF with LibreOffice to map content to page numbers for the page picker.

### 6.2 Page selection

- UI shows page thumbnails. The user picks **All pages**, ranges (`12–30, 45, 51–60`), or chapters/sections from a detected table of contents.
- Accept **both** printed page numbers ("p. 47" in the book) and PDF page indices. Detect the offset between them automatically by reading the printed page numbers, and show both.
- Detect the answer key section automatically (headings like "Answers", "Selected Answers", "Answer Key", "Solutions"; dense numbered short answers; usually the last 10–20% of the book). The user can confirm it or set its page range by hand.
- Only selected problem pages get solved. The answer key pages are always parsed (only the relevant entries are used).

### 6.3 Structuring problems

The LLM (with layout info and page images) turns each page into structured records:

```json
{
  "id": "ch3.sec2.ex17b",
  "chapter": "3", "section": "3.2", "exercise_set": "Practice",
  "number": "17", "part": "b",
  "page_printed": 147, "page_index": 163,
  "instructions": "Solve. Round to the nearest tenth if necessary.",
  "text_latex": "3x^2 - 5x - 7 = 0",
  "figures": ["fig_163_2.png"],
  "shared_context": "Use the table for Exercises 15–20.",
  "answer_type": "set_of_reals",
  "course_hint": "algebra1"
}
```

Points to get right:
- **Instructions are inherited.** "Solve each equation. Round to the nearest hundredth." applies to every problem below it, and it changes what counts as correct.
- **Shared context:** "Use the graph for Exercises 5–9" has to be attached to each of those problems.
- **Multi-part problems** (a, b, c) get separate entries.
- **Problem types:** compute / solve / simplify / prove / graph / explain / multiple choice / true-false. Proofs, "explain", and graphing problems go to a special track (§6.6).

### 6.4 Answer key parsing and alignment

- Parse key entries into `(chapter, section, exercise set, number, part) → answer`.
- Handle common layouts: multiple columns, "odd answers only", section headers like "Lesson 3-2", answers that run across columns or pages, answers that are graphs (images).
- **Alignment check:** after matching, look for signs the matching is off: a run of mismatches that would all become matches if shifted by one, or a key section whose answers don't fit the problem types. If found, re-align or flag it.
- Record the key entry's location (page and position) for reporting and editing.

### 6.5 Solving and verification by course

The solver picks strategies using a course/topic classifier. Each answer type has an **equivalence checker** (§6.7).

| Course | Typical problems | CAS / numeric path | Direct key verification |
|---|---|---|---|
| **K–8** | Arithmetic, fractions, decimals, percents, ratios, unit conversion, area/perimeter, mean/median/mode, word problems | Exact rationals (`fractions.Fraction`, SymPy `Rational`), `pint` for units | Recompute exactly. Word problems: LLM sets up the equation, CAS solves it, and the setup is checked by a second independent LLM run |
| **Algebra 1** | Linear equations/inequalities, systems, slope, functions, exponents, polynomials, factoring, quadratics, radicals | `solve`, `solveset`, `factor`, `expand`, `linsolve`, `reduce_inequalities` | Substitute roots; expand factored forms and compare; test points for inequalities |
| **Geometry** | Angles, triangles, similarity, Pythagorean theorem, trig ratios, circles, area/volume, coordinate geometry, transformations, proofs | SymPy geometry module, trig solve; numeric solve with constraints from the figure | Check the figure's constraints are satisfied (angle sums, side lengths). Proofs → review track |
| **Algebra 2** | Polynomials, rational functions, exponentials/logs, sequences/series, complex numbers, matrices, conics, probability | `solveset` over ℂ, `apart`, log rules, `Matrix`, summation | Substitute, including complex roots; check domain restrictions (extraneous roots) |
| **Precalculus** | Trig identities and equations, inverse trig, polar/parametric, vectors, limits (intro), conics | `trigsimp`, general solutions with periodicity, `nsolve` | Trig equations: check the key's solution set *and* the requested interval (e.g. `[0, 2π)`). Identities: symbolic plus numeric random-point test |
| **Calc AB / Calc 1** | Limits, derivatives, implicit differentiation, related rates, optimization, integrals, FTC, area/volume | `limit`, `diff`, `integrate`, `idiff`, numeric quadrature (mpmath) | Differentiate the key's antiderivative; numeric checks of limits and definite integrals; check critical points |
| **Calc BC / Calc 2** | Integration techniques, improper integrals, series convergence, Taylor/Maclaurin, polar/parametric calculus | `integrate`, `series`, `summation`, convergence tests, numeric partial sums | Compare Taylor coefficients; numeric checks of improper integrals; convergence by more than one test |
| **AP Stats** | Descriptive stats, regression, probability, distributions, sampling, confidence intervals, hypothesis tests | SciPy/statsmodels; exact binomial/normal/t/χ² computations | Recompute from the data. **Match the book's convention** (table vs calculator values, z vs t, pooled vs unpooled, rounding of intermediate steps); a tolerance band accounts for table-based answers |
| **Calc 3** | Vectors, partial derivatives, gradients, multiple integrals, line/surface integrals, Green/Stokes/divergence | SymPy vector module, iterated `integrate`, numeric cubature | Compute double/triple integrals in two orders or coordinate systems; check the theorem both ways (e.g. a line integral vs Green's double integral) |
| **Diff Eqs** | Separable, linear, exact, 2nd-order linear, undetermined coefficients, variation of parameters, Laplace, systems, series solutions | `dsolve`, `laplace_transform`, `Matrix.exp`, numeric ODE (`solve_ivp`) | **Substitute the key's solution into the ODE** (`checkodesol`) and check initial conditions; compare with a numeric solution |

### 6.6 Problems that can't be checked by computation

- **Proofs / "show that" / "explain":** an LLM grader checks the key's argument against a rubric, and these always come out as 🔍 *Needs review* with notes. The "show that" *claim itself* can still be checked by CAS.
- **Graphs / sketches in the key:** extract key features from the image (intercepts, asymptotes, shading, open/closed points) with vision and compare with computed features. Report as ⚠️ or 🔍, never ❌, unless a specific feature is clearly wrong (e.g. the key shades the wrong side of an inequality).
- **Free-response stats interpretation** ("interpret the slope in context"): rubric check, 🔍 only.

### 6.7 Answer equivalence engine (key to accuracy)

Most false alarms come from treating two correct forms as different. The comparison layer must recognize equivalent answers:

| Answer type | Equivalence rule |
|---|---|
| Number | Exact equality for exact answers; for decimals, compare at the book's stated rounding (from the instructions). Accept `0.5 = 1/2 = 50%` *only* if the instructions allow either format; otherwise report a format issue (⚠️) |
| Expression | `simplify(a − b) == 0`, **plus** numeric checks at 20+ random points (including complex points), to catch both SymPy false negatives and false positives |
| Equation | Same solution set, or one is a nonzero multiple of the other (for lines, conics) |
| Solution set | Set equality (order doesn't matter); count multiplicity only if asked |
| Interval / inequality | Normalize to interval notation; compare endpoints and open/closed |
| Ordered pair / tuple / vector | Element-wise equivalence (order matters) |
| Matrix | Element-wise; for eigenvectors, equality up to scaling |
| Indefinite integral | Derivative of the key equals the integrand, and the key includes `+ C`. Differing by a constant counts as equivalent |
| General solution of a DE | Satisfies the ODE and spans the same solution family (arbitrary constants may be relabeled or combined) |
| Trig equation solutions | Same set over the stated interval, or the same general solution modulo the period |
| Units | Convert with `pint`; wrong or missing units → ⚠️ |
| Multiple choice | Letter, **and** check the letter's option content (catches keys pointing to the wrong letter) |
| Stats values | Tolerance tied to the method (table vs software); report the book's convention |

Every equivalence decision is logged with the method used, so a human can check the reasoning.

### 6.8 Confidence scoring

Inputs: agreement among LLM runs, agreement between the LLM and CAS, the key-verification result, extraction quality (OCR vs text-layer agreement), and problem-type risk (word problems and figure-dependent problems are higher risk).

- High confidence plus mismatch → ❌
- Medium confidence, or any path disagrees → 🔍
- On 🔍, escalate automatically first: more LLM runs, a stronger model, different CAS formulations. Only items still unresolved stay 🔍.

Thresholds get tuned on the test set (§9) so that **precision on ❌ is at least 99%**. A false "your key is wrong" is the worst failure.

---

## 7. User interface

1. **Upload screen:** drag-and-drop `.pdf` / `.docx`, with optional settings:
   - Course / grade level (auto-detected; the user can override)
   - Pages to check: **All** or a custom range / chapter picker with thumbnails
   - Answer key location: auto-detect or a manual page range
   - Strictness: whether equivalent forms count as correct, or whether the format must match the book
2. **Progress view:** live status for each page and problem (extracting → solving → verifying).
3. **Results dashboard:** summary counts by verdict; filter by verdict, chapter, or course topic.
4. **Problem detail (side by side):** original page crop | extracted problem | key answer | computed answer | diagnosis | worked solution | evidence.
5. **Human review controls:** for each item, *Accept correction*, *Reject (key is right)*, or *Edit correction*. These decisions feed into the export and into the test set.
6. **Export:** PDF/DOCX/CSV report, and (nice-to-have) a corrected document.

---

## 8. Nice-to-have: apply fixes to DOCX and convert to PDF

### 8.1 Editing the DOCX
- Use the location anchors from ingestion (§6.1) to find each key entry's paragraph and run range.
- Two modes:
  - **Tracked changes (default):** insert `<w:del>` / `<w:ins>` revision marks with an author like "Answer Key Verifier" and a Word comment holding the explanation. The author can accept or reject each change in Word.
  - **Clean replace:** overwrite directly, keeping run formatting (font, size, bold, etc.).
- **Equations:** if the key answer is an OMML equation, generate replacement OMML (LaTeX → MathML → OMML) so it still displays as an equation.
- Only apply changes the user accepted (or all ❌ items with "auto-apply high confidence" turned on).
- After editing, re-open and re-parse the document to confirm every change landed and nothing else changed (compare the before/after text outside the edited ranges).

### 8.2 PDF inputs
Editing a PDF directly isn't reliable. Options:
- Make an **annotated PDF**: red strike-through on the wrong key answer plus a sticky note or callout with the correction (PyMuPDF annotations). Simple and reliable.
- Or convert the PDF to DOCX (e.g. `pdf2docx`), apply the fixes, then convert back. This is lossy for complex layouts, so it's opt-in with a warning.

### 8.3 DOCX → PDF
- `soffice --headless --convert-to pdf corrected.docx`, bundled in the Docker image.
- Optionally, Microsoft Word automation on Windows for perfect fidelity, when available.

---

## 9. Proving accuracy: testing and evaluation

Accuracy is the main requirement, so testing is part of the build, not an add-on.

1. **Benchmark set:** 50+ real books and worksheets spread across all 12 courses (public/OER texts such as OpenStax for Algebra–Calculus and Statistics, plus user-supplied ones).
2. **Ground truth:** humans check a sample of problems per book.
3. **Seeded-error tests:** take correct keys and inject realistic errors (sign flips, missing roots, wrong rounding, swapped answers, missing `+C`, off-by-one alignment, wrong letter in multiple choice, units). Measure detection rate.
4. **Equivalence tests:** thousands of pairs of equivalent forms that must *not* be flagged (e.g. `(x+1)²` vs `x²+2x+1`, `ln(x²)` vs `2ln|x|` with domain care, `sin²x` vs `1−cos²x`, alternate antiderivatives, DE general-solution forms).
5. **Metrics, tracked for each course:**
   - **❌ precision** (target ≥ 99%): of the items flagged wrong, how many truly are
   - **❌ recall** (target ≥ 95%): of the truly wrong keys, how many are caught
   - **Extraction accuracy**: problems and key entries correctly captured
   - **Review rate**: share of items sent to 🔍 (keep it low without losing precision)
6. **Regression suite** in CI: every change reruns the benchmark; precision may not drop.
7. Human review decisions from the UI (§7.5) go back into the benchmark.

---

## 10. Project structure

```
math-solver/
├── backend/
│   ├── app/                 # FastAPI routes, job orchestration
│   ├── ingest/              # pdf.py, docx.py, ocr.py, omml_to_latex.py, page_map.py
│   ├── structure/           # problem_extractor.py, key_parser.py, aligner.py
│   ├── solve/
│   │   ├── llm_solver.py    # multi-run reasoning solver
│   │   ├── cas_solver.py    # LLM→SymPy code generation + sandboxed execution
│   │   ├── verifiers/       # per-topic direct verification (algebra, calc, de, stats, …)
│   │   └── router.py        # course/topic classification → strategy
│   ├── compare/             # equivalence engine, confidence scoring, pattern detection
│   ├── report/              # HTML/PDF/DOCX/CSV report generation
│   ├── fix/                 # docx_editor.py (tracked changes), pdf_annotate.py, convert.py
│   └── sandbox/             # isolated code runner
├── frontend/                # React app: upload, page picker, dashboard, review
├── eval/                    # benchmark datasets, seeded-error generator, metrics
├── tests/
├── docker/                  # Dockerfile with LibreOffice + Python stack
└── PLAN.md
```

---

## 11. Milestones

| Phase | Scope | Exit criteria |
|---|---|---|
| **0. Foundations** (1–2 wks) | Repo, Docker, FastAPI skeleton, sandbox, eval harness, first benchmark (Algebra 1 + K–8) | Harness runs end to end on a toy dataset |
| **1. MVP: text PDFs, Algebra 1 + K–8** (3–4 wks) | PDF ingestion, page selection, problem/key extraction, alignment, LLM + CAS solve, equivalence engine, basic HTML report with "what's wrong / change to" | ❌ precision ≥ 99% on the benchmark for these courses |
| **2. DOCX + scanned PDFs** (2–3 wks) | DOCX/OMML ingestion, OCR/vision path, figure extraction | Extraction accuracy ≥ 98% on the benchmark |
| **3. Geometry, Algebra 2, Precalc** (3 wks) | Figure-aware solving, trig/complex/log verifiers, interval-aware comparison | Targets met for each course |
| **4. Calculus (AB/BC/1/2/3)** (3–4 wks) | Limits/derivatives/integrals/series/multivariable verifiers | Targets met for each course |
| **5. AP Stats + Diff Eqs** (2–3 wks) | Stats convention handling, ODE substitution verification, Laplace/systems | Targets met for each course |
| **6. UI polish + review workflow** (2 wks) | Dashboard, side-by-side review, pattern detection, exports | Usability pass with real users |
| **7. Nice-to-have: fix and convert** (2 wks) | DOCX tracked-change editing, PDF annotation, LibreOffice export | Round-trip tests show only the intended text changed |

---

## 12. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Garbled math from PDF text layers | Vision transcript of every math-bearing crop, checked against the text layer; disagreements → 🔍 |
| Wrong problem↔key alignment | Shift detection, section header anchoring, user confirmation of the key's page range |
| LLM arithmetic or reasoning errors | Never rely on the LLM alone: CAS cross-check plus direct key verification plus multiple runs |
| SymPy can't simplify or solve certain forms | Numeric random-point testing; alternate formulations; fall back to 🔍 rather than guess |
| Book conventions (rounding, table values, exact vs decimal) | Parse instructions; per-book settings; stats tolerance bands; report as ⚠️ format issue, not ❌ |
| Figure-dependent problems (geometry, graphs) | Figure extraction plus vision; when the figure is ambiguous → 🔍 |
| Cost and time on large books | Cheaper model for extraction and triage, strong model only for solving and escalation; caching; parallel jobs; only selected pages |
| Copyright / privacy of textbooks | Runs locally; only problem text and crops go to the API; no storage beyond the job unless the user opts in |
| Running LLM-generated code | Sandbox with no network, CPU/memory/time limits, allow-listed imports |

---

## 13. Open questions for the user

1. **Where will it run?** Local desktop app/web app on your machine, or a hosted website for multiple users?
2. **API budget:** is using a paid LLM API (Claude) and optionally Mathpix OK? Accuracy depends a lot on a strong model.
3. **Typical inputs:** mostly digital PDFs from publishers, or scanned/photographed pages? Mostly DOCX worksheets you wrote yourself?
4. **Strictness default:** if the key says `0.5` and the problem asks for a fraction, should that be ❌, ⚠️, or ✅?
5. **Corrections in DOCX:** tracked changes (reviewable in Word) or clean replacement?
