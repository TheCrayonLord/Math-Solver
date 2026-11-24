"""Tier 1 solver: rule-based problem understanding + exact computation with SymPy.

Every handler either returns a Solution or None (not my kind of problem).
If nothing handles a problem, Unsupported is raised and the problem goes to "Needs review".
"""
from __future__ import annotations

import math
import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

import sympy as sp

from .mathparse import (
    ParseError, normalize, parse_math, parse_relation_chain, pretty, pretty_set, rounding_places,
    REL_OPS,
)
from .models import Problem, Solution


class Unsupported(Exception):
    pass


NUM = r"-?\d+(?:,\d{3})*(?:\.\d+)?|-?\.\d+"
LEAD_VERB_RE = re.compile(
    r"^(?:solve(?:\s+(?:the|each)\s+(?:equation|inequality|system))?|simplify(?:\s+the\s+expression)?|"
    r"evaluate(?:\s+the\s+expression)?|factor(?:\s+completely)?|expand|multiply|add|subtract|divide|"
    r"compute|calculate|find\s+the\s+(?:sum|difference|product|quotient|value)(?:\s+of)?|find)\b"
    r"[\s:.,]*", re.I)
TRAILING_NOISE_RE = re.compile(r"\s*(?:check your (?:answer|solution)s?\.?|show your work\.?)\s*$", re.I)


def _strip_verb(text: str) -> str:
    t = text.strip()
    for _ in range(2):
        t2 = LEAD_VERB_RE.sub("", t).strip()
        if t2 == t:
            break
        t = t2
    return TRAILING_NOISE_RE.sub("", t).strip()


def _num(s: str) -> sp.Rational:
    return sp.Rational(s.replace(",", ""))


def round_half_up(value, places: int) -> sp.Rational:
    d = Decimal(str(sp.N(value, 40)))
    q = Decimal(1).scaleb(-places)
    return sp.Rational(str(d.quantize(q, rounding=ROUND_HALF_UP)))


def decimalize(s: str) -> str:
    """Show terminating fractions as decimals (for problems written with decimals)."""
    def rep(m):
        a, b = int(m.group(1)), int(m.group(2))
        q = b
        for f in (2, 5):
            while q % f == 0:
                q //= f
        if q != 1 or b == 0:
            return m.group(0)
        val = Decimal(a) / Decimal(b)
        return format(val.normalize(), "f")
    return re.sub(r"(?<![\w.^])(-?\d+)/(\d+)(?![\w.^(])", rep, s)


def _fmt_number(v) -> str:
    return pretty(v)


# ----------------------------------------------------------------- handlers

def h_round(text, instr, ctx) -> Optional[Solution]:
    m = re.search(rf"round\s+({NUM})\s+to\s+the\s+nearest\s+([\w-]+(?:\s+number)?)", ctx, re.I)
    if not m:
        m2 = re.fullmatch(rf"\s*({NUM})\s*", text)
        places = rounding_places(instr) if m2 and re.search(r"\bround", instr, re.I) else None
        if m2 is None or places is None:
            return None
        val = _num(m2.group(1))
    else:
        val = _num(m.group(1))
        places = rounding_places("nearest " + m.group(2))
        if places is None:
            return None
    r = round_half_up(val, places)
    shown = f"{float(r):.{places}f}" if places > 0 else f"{int(r):,}"
    target = {1: "tenth", 2: "hundredth", 3: "thousandth", 0: "whole number", -1: "ten",
              -2: "hundred", -3: "thousand"}.get(places, f"{places} decimal places")
    orig = m.group(1) if m else m2.group(1)
    return Solution("number", r, shown, steps=[f"Rounding {orig} to the nearest {target}: {shown}"],
                    method="rounding")


def h_percent(text, instr, ctx) -> Optional[Solution]:
    m = re.search(rf"({NUM})\s*%\s*of\s*\$?({NUM})", ctx, re.I)
    if m and not re.search(r"what\s+percent", ctx, re.I):
        p, n = _num(m.group(1)), _num(m.group(2))
        v = p / 100 * n
        return Solution("number", v, _fmt_number(v), steps=[f"{pretty(p)}% of {pretty(n)} = "
                        f"{pretty(p / 100)} × {pretty(n)} = {pretty(v)}"], method="percent")
    m = re.search(rf"what\s+percent\s+of\s+\$?({NUM})\s+is\s+\$?({NUM})", ctx, re.I)
    if m:
        whole, part = _num(m.group(1)), _num(m.group(2))
    else:
        m = re.search(rf"\$?({NUM})\s+is\s+what\s+percent\s+of\s+\$?({NUM})", ctx, re.I)
        if not m:
            return None
        part, whole = _num(m.group(1)), _num(m.group(2))
    if whole == 0:
        return None
    v = part / whole * 100
    return Solution("percent", v, _fmt_number(v) + "%",
                    steps=[f"{pretty(part)} ÷ {pretty(whole)} × 100 = {pretty(v)}%"], method="percent")


def _number_list(text: str) -> Optional[list]:
    t = re.sub(r"\band\b", ",", text)
    t = t.strip().rstrip(".")
    parts = [p.strip() for p in re.split(r"[,;]\s*|\s+", t) if p.strip()]
    if len(parts) < 2 or not all(re.fullmatch(NUM, p) for p in parts):
        return None
    return [_num(p) for p in parts]


def h_gcf_lcm(text, instr, ctx) -> Optional[Solution]:
    low = ctx.lower()
    is_gcf = bool(re.search(r"\b(gcf|gcd|greatest common (factor|divisor))\b", low))
    is_lcm = bool(re.search(r"\b(lcm|least common (multiple|denominator)|lcd)\b", low))
    if is_gcf == is_lcm:
        return None
    m = re.search(r"(?:of|for)\s+([\d,\s]+(?:and\s+\d+)?)\s*\.?$", text)
    nums = _number_list(m.group(1)) if m else _number_list(_strip_verb(text))
    if not nums or not all(n.q == 1 for n in nums):
        return None
    ints = [int(n) for n in nums]
    if is_gcf:
        v = sp.Integer(math.gcd(*ints))
        return Solution("number", v, str(v), steps=[f"GCF({', '.join(map(str, ints))}) = {v}"],
                        method="gcf")
    v = sp.Integer(math.lcm(*ints))
    return Solution("number", v, str(v), steps=[f"LCM({', '.join(map(str, ints))}) = {v}"],
                    method="lcm")


def h_stats(text, instr, ctx) -> Optional[Solution]:
    low = ctx.lower()
    kinds = [k for k in ("mean", "average", "median", "mode", "range") if re.search(rf"\b{k}\b", low)]
    if "average" in kinds and "mean" in kinds:
        kinds.remove("average")
    if len(kinds) != 1:
        return None
    m = re.search(r"(?:of|for)\s*:?\s*([-\d.,\s]+(?:and\s+-?[\d.]+)?)\s*\.?$", text)
    nums = _number_list(m.group(1)) if m else _number_list(_strip_verb(text))
    if not nums:
        return None
    k = kinds[0]
    data = sorted(nums)
    n = len(data)
    if k in ("mean", "average"):
        v = sum(data) / n
        step = f"Sum = {pretty(sum(data))}, count = {n}, mean = {pretty(v)}"
    elif k == "median":
        v = data[n // 2] if n % 2 else (data[n // 2 - 1] + data[n // 2]) / 2
        step = f"Ordered: {', '.join(pretty(x) for x in data)} → median = {pretty(v)}"
    elif k == "range":
        v = data[-1] - data[0]
        step = f"{pretty(data[-1])} − {pretty(data[0])} = {pretty(v)}"
    else:
        counts = {}
        for x in data:
            counts[x] = counts.get(x, 0) + 1
        top = max(counts.values())
        if top == 1:
            return Solution("text", "no mode", "no mode", steps=["Every value appears once."],
                            method="mode")
        modes = [x for x, c in counts.items() if c == top]
        return Solution("solutions", sp.FiniteSet(*modes), ", ".join(pretty(x) for x in modes),
                        steps=[f"Most frequent value(s) appear {top} times"], method="mode")
    return Solution("number", v, _fmt_number(v), steps=[step], method=k)


POINT_RE = re.compile(rf"\(\s*({NUM}(?:\s*/\s*\d+)?)\s*,\s*({NUM}(?:\s*/\s*\d+)?)\s*\)")


def h_slope(text, instr, ctx) -> Optional[Solution]:
    if not re.search(r"\bslope\b", ctx, re.I) or re.search(r"equation|intercept\s+form|y-intercept", ctx, re.I):
        return None
    pts = POINT_RE.findall(normalize(text))
    if len(pts) != 2:
        return None
    (x1, y1), (x2, y2) = [(parse_math(a), parse_math(b)) for a, b in pts]
    if x2 == x1:
        return Solution("text", "undefined", "undefined",
                        steps=[f"x-values are equal ({pretty(x1)}), so the line is vertical"],
                        method="slope")
    v = (y2 - y1) / (x2 - x1)
    return Solution("number", v, _fmt_number(v),
                    steps=[f"m = ({pretty(y2)} − ({pretty(y1)})) / ({pretty(x2)} − ({pretty(x1)})) = {pretty(v)}"],
                    method="slope")


FUNC_DEF_RE = re.compile(r"\b([fghkpq])\s*\(\s*([a-z])\s*\)\s*=\s*(.+?)(?:(?<!\d)[.;,](?!\d)|\s+(?:find|evaluate|what|and)\b|$)", re.I)


def h_function(text, instr, ctx) -> Optional[Solution]:
    nctx = normalize(ctx)
    m = FUNC_DEF_RE.search(nctx)
    if not m:
        return None
    fname, var, body = m.group(1), m.group(2), m.group(3).strip()
    rest = normalize(text)
    if m.group(0) in rest:
        rest = rest.replace(m.group(0), " ")
    rest = re.sub(r"^.*?\b(?:find|evaluate|what\s+is)\b", "", rest, flags=re.I).strip(" .?:")
    if not re.search(rf"\b{fname}\s*\(", rest):
        return None
    def repl(mm):
        arg = mm.group(1)
        return "(" + re.sub(rf"(?<![A-Za-z]){var}(?![A-Za-z])", f"({arg})", body) + ")"
    target = re.sub(rf"\b{fname}\s*\(([^()]*)\)", repl, rest)
    v = sp.simplify(parse_math(target))
    kind = "number" if not v.free_symbols else "expr"
    return Solution(kind, v, pretty(v), steps=[f"{fname}({var}) = {body}", f"{rest} = {pretty(v)}"],
                    method="function evaluation")


ASSIGN_CLAUSE_RE = re.compile(
    rf"\b(?:when|for|if|given|where|using|let)\s+((?:[a-zA-Z]\s*=\s*(?:{NUM})(?:\s*/\s*\d+)?\s*(?:,|and|;)?\s*)+)",
    re.I)


def h_evaluate(text, instr, ctx) -> Optional[Solution]:
    m = ASSIGN_CLAUSE_RE.search(normalize(text)) or ASSIGN_CLAUSE_RE.search(normalize(instr))
    if not m:
        return None
    assigns = dict(re.findall(rf"([a-zA-Z])\s*=\s*((?:{NUM})(?:\s*/\s*\d+)?)", m.group(1)))
    expr_text = normalize(text).replace(m.group(0), " ") if m.group(0) in normalize(text) else normalize(text)
    expr_text = _strip_verb(expr_text).strip(" .,:;")
    if "=" in expr_text or not expr_text:
        return None
    e = parse_math(expr_text)
    subs = {sp.Symbol(k): parse_math(v) for k, v in assigns.items()}
    if not e.free_symbols or not e.free_symbols <= set(subs):
        return None
    v = sp.simplify(e.subs(subs))
    shown = ", ".join(f"{k} = {v_}" for k, v_ in assigns.items())
    return Solution("number", v, pretty(v), steps=[f"Substitute {shown} into {pretty(e)}: {pretty(v)}"],
                    method="evaluate")


def _split_equations(t: str) -> list[str]:
    parts = re.split(r";|\s+and\s+|,\s*(?=[^,]*=)|\s{2,}", t)
    return [p.strip(" .") for p in parts if p.strip(" .")]


def h_system(text, instr, ctx) -> Optional[Solution]:
    t = _strip_verb(normalize(text))
    if t.count("=") < 2 or re.search(r"[<>]", t):
        return None
    eq_texts = _split_equations(t)
    if len(eq_texts) < 2 or any(e.count("=") != 1 for e in eq_texts):
        return None
    eqs = []
    for et in eq_texts:
        l, r = et.split("=")
        eqs.append(sp.Eq(parse_math(l), parse_math(r), evaluate=False))
    syms = sorted(set().union(*[e.free_symbols for e in eqs]), key=str)
    if len(syms) not in (2, 3) or len(eqs) != len(syms):
        return None
    sols = sp.solve(eqs, syms, dict=True)
    if not sols:
        return Solution("tuple", "empty", "no solution", equations=eqs, variables=syms,
                        steps=["The equations are inconsistent (parallel lines)."], method="system")
    if len(sols) > 1:
        raise Unsupported("system has more than one solution")
    s = sols[0]
    if any(v not in s for v in syms):
        return Solution("tuple", "infinite", "infinitely many solutions", equations=eqs,
                        variables=syms, steps=["The equations are dependent (same line)."],
                        method="system")
    tup = tuple(s[v] for v in syms)
    return Solution("tuple", tup, pretty(tup), equations=eqs, variables=syms,
                    steps=[f"Solving gives {', '.join(f'{v} = {pretty(s[v])}' for v in syms)}"],
                    method="system")


def _linear_steps(lhs, rhs, x) -> list[str]:
    try:
        pl, pr = sp.Poly(sp.expand(lhs), x), sp.Poly(sp.expand(rhs), x)
    except Exception:  # noqa: BLE001
        return []
    if pl.degree() > 1 or pr.degree() > 1:
        return []
    a1, b1 = pl.coeff_monomial(x), pl.coeff_monomial(1)
    a2, b2 = pr.coeff_monomial(x), pr.coeff_monomial(1)
    steps = []
    if sp.expand(lhs) != lhs or sp.expand(rhs) != rhs:
        steps.append(f"Simplify each side: {pretty(a1 * x + b1)} = {pretty(a2 * x + b2)}")
    a, b, c = a1 - a2, b1, b2
    if a2 != 0:
        steps.append(f"Move the x-terms to the left: {pretty(a * x + b)} = {pretty(c)}")
    if b != 0:
        steps.append(f"{'Subtract' if b > 0 else 'Add'} {pretty(abs(b))} on both sides: "
                     f"{pretty(a * x)} = {pretty(c - b)}")
    if a == 0:
        return steps
    if a != 1:
        steps.append(f"Divide both sides by {pretty(a)}: {x} = {pretty((c - b) / a)}")
    return steps


def h_equation(text, instr, ctx) -> Optional[Solution]:
    t = _strip_verb(normalize(text))
    m_for = re.search(r"solve\s+(?:\S+\s+){0,3}?for\s+([a-zA-Z])\b", ctx, re.I)
    t = re.sub(r"\s*,?\s*for\s+[a-zA-Z]\s*\.?$", "", t)
    if t.count("=") != 1 or re.search(r"[<>!]", t):
        return None
    l, r = t.split("=")
    lhs, rhs = parse_math(l), parse_math(r)
    eq = sp.Eq(lhs, rhs, evaluate=False)
    syms = sorted(lhs.free_symbols | rhs.free_symbols, key=str)
    if m_for and len(syms) > 1:
        var = sp.Symbol(m_for.group(1))
        if var not in syms:
            return None
        sols = sp.solve(eq, var)
        if len(sols) != 1:
            raise Unsupported("literal equation with several solutions")
        v = sp.simplify(sols[0])
        return Solution("literal", v, f"{var} = {pretty(v)}", equations=[eq],
                        variables=[var], steps=[f"Solve for {var}: {var} = {pretty(v)}"],
                        method="literal equation")
    if len(syms) != 1:
        return None
    x = syms[0]
    sol = sp.solveset(lhs - rhs, x, sp.S.Reals)
    if not (isinstance(sol, sp.FiniteSet) or sol in (sp.S.EmptySet, sp.S.Reals)):
        if isinstance(sol, sp.Complement) and sol.args[0] == sp.S.Reals:
            pass  # identity except excluded points
        else:
            raise Unsupported(f"solution set is not a simple list ({sol})")
    steps = _linear_steps(lhs, rhs, x)
    if not steps:
        steps = [f"Solve {pretty(lhs)} = {pretty(rhs)} for {x}"]
    steps.append(f"Solution: {pretty_set(sol, str(x))}")
    return Solution("solutions", sol, pretty_set(sol, str(x)), equations=[eq],
                    variables=[x], steps=steps, method="equation")


def h_inequality(text, instr, ctx) -> Optional[Solution]:
    t = _strip_verb(normalize(text))
    if not re.search(r"[<>]", t):
        return None
    total = sp.S.EmptySet
    rels = []
    syms = set()
    for chunk in re.split(r"\s+or\s+", t):
        cur = sp.S.Reals
        for part in [p for p in re.split(r"\s+and\s+", chunk) if p.strip()]:
            for lhs, op, rhs in parse_relation_chain(part):
                rel = REL_OPS[op](lhs, rhs)
                rels.append(rel)
                fs = (lhs - rhs).free_symbols
                syms |= fs
                if len(fs) != 1:
                    return None
                cur = cur.intersect(sp.solveset(rel, list(fs)[0], sp.S.Reals))
        total = total.union(cur)
    if len(syms) != 1:
        return None
    x = list(syms)[0]
    return Solution("interval", total, pretty_set(total, str(x)), equations=rels, variables=[x],
                    steps=[f"Solution: {pretty_set(total, str(x))}"], method="inequality")


def h_factor(text, instr, ctx) -> Optional[Solution]:
    if not re.search(r"\bfactor", ctx, re.I) or re.search(r"\b(gcf|greatest common factor of|factors of|prime factorization)\b", ctx, re.I):
        return None
    t = _strip_verb(normalize(text))
    if "=" in t:
        return None
    e = parse_math(t)
    if not e.free_symbols:
        return None
    f = sp.factor(e)
    content, factors = sp.factor_list(e)
    prime = abs(content) == 1 and len(factors) == 1 and factors[0][1] == 1
    return Solution("factor", f, "prime (cannot be factored)" if prime else pretty(f),
                    steps=[f"{pretty(e)} = {pretty(f)}"], method="factor")


def h_expression(text, instr, ctx) -> Optional[Solution]:
    t = _strip_verb(normalize(text))
    if re.search(r"[=<>]", t):
        return None
    e = parse_math(t)
    if e.free_symbols:
        v = sp.simplify(e)
        if re.search(r"\b(expand|multiply|product)\b", ctx, re.I):
            v = sp.expand(e)
        return Solution("expr", v, pretty(v), steps=[f"{pretty(e)} = {pretty(v)}"], method="simplify")
    v = sp.simplify(e)
    return Solution("number", v, pretty(v), steps=[f"= {pretty(v)}"], method="arithmetic")


HANDLERS = [h_round, h_percent, h_gcf_lcm, h_stats, h_slope, h_function, h_evaluate,
            h_system, h_factor, h_inequality, h_equation, h_expression]


def solve_problem(problem: Problem) -> Solution:
    text = problem.text.strip()
    instr = problem.instruction.strip()
    ctx = f"{instr} {text}".strip()
    if re.search(r"\b(prove|explain|describe|graph|sketch|draw|justify|why)\b", ctx, re.I):
        raise Unsupported("asks for a proof, explanation, or graph")
    reasons = []
    for h in HANDLERS:
        try:
            sol = h(text, instr, ctx)
        except ParseError as exc:
            reasons.append(str(exc))
            continue
        if sol is not None:
            if re.search(r"\d\.\d|\$|%", text) and sol.kind != "percent":
                sol.display = decimalize(sol.display)
                sol.steps = [decimalize(st) for st in sol.steps]
            sol.places = rounding_places(ctx)
            sol.simplest_form = bool(re.search(r"simplest\s+form|lowest\s+terms|simplify", ctx, re.I))
            return sol
    if any("contains words" in r for r in reasons) or re.search(r"[A-Za-z]{4,}", _strip_verb(text)):
        raise Unsupported("word problem (not yet supported by the automatic solver)")
    raise Unsupported("couldn't understand the problem" + (f": {reasons[-1]}" if reasons else ""))
