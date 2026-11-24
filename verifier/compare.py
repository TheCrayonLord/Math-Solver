"""Compare a computed solution with the answer key and explain any difference.

Rule for accuracy: a key is only reported wrong when
  * the key's answer is NOT equivalent to the computed answer, and
  * where a direct check exists (plugging the key's answer back in), the key's answer fails it.
If the key passes a direct check but disagrees with the solver, the problem goes to review.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Any, Optional

import sympy as sp

from .mathparse import (
    ParseError, decimal_places, parse_expr_answer, parse_interval_answer, parse_math,
    parse_number_answer, parse_solution_set, parse_tuple_answer, pretty, pretty_set,
)
from .models import (
    Solution, VERDICT_CORRECT, VERDICT_INCOMPLETE, VERDICT_REVIEW, VERDICT_WRONG,
)
from .solver import round_half_up


@dataclass
class Comparison:
    verdict: str
    error_type: str = ""
    message: str = ""
    checks: list[str] = field(default_factory=list)
    key_value: Any = None


TOL = 1e-9


def _num(v) -> Optional[complex]:
    try:
        z = complex(sp.N(v, 30))
    except (TypeError, ValueError):
        return None
    if z != z or abs(z) == float("inf"):
        return None
    return z


def numbers_equal(c, k, raw: str = "", places: Optional[int] = None) -> bool:
    zc, zk = _num(c), _num(k)
    if zc is None or zk is None:
        return False
    if abs(zc - zk) <= TOL * max(1.0, abs(zc)):
        return True
    if abs(zc.imag) > TOL or abs(zk.imag) > TOL:
        return False
    # The key may show a rounded value: accept it if it equals the correctly rounded answer,
    # at the precision the key shows or the precision the problem asked for.
    kd = decimal_places(raw) if raw else None
    for d in (kd, places):
        if d is None:
            continue
        try:
            if round_half_up(c, d) == sp.Rational(str(sp.N(k, 30))).limit_denominator(10 ** 12):
                return True
        except Exception:  # noqa: BLE001
            pass
    return False


def exprs_equal(a, b) -> Optional[bool]:
    """True / False / None (can't tell)."""
    try:
        d = sp.simplify(a - b)
        sym = d == 0
    except Exception:  # noqa: BLE001
        sym = None
    syms = sorted((a.free_symbols | b.free_symbols), key=str)
    rnd = random.Random(12345)
    agree = disagree = 0
    for _ in range(30):
        pt = {s: sp.Rational(rnd.randint(-370, 430), 97) for s in syms}
        za, zb = _num(a.subs(pt)), _num(b.subs(pt))
        if za is None or zb is None:
            continue
        if abs(za - zb) <= 1e-8 * max(1.0, abs(za)):
            agree += 1
        else:
            disagree += 1
    if sym is True:
        return True if disagree == 0 else None
    if disagree == 0 and agree >= 10:
        return True
    if disagree > 0 and agree + disagree >= 5:
        return False
    return None


def _sub_str(var_vals: dict) -> str:
    return ", ".join(f"{k} = {pretty(v)}" for k, v in var_vals.items())


def plug_in(equations, var_vals: dict) -> tuple[str, list[str]]:
    """Returns ('ok'|'fail'|'undefined', check lines)."""
    lines, status = [], "ok"
    for eq in equations:
        lhs, rhs = eq.lhs, eq.rhs
        try:
            lv = sp.simplify(lhs.subs(var_vals))
            rv = sp.simplify(rhs.subs(var_vals))
        except Exception:  # noqa: BLE001
            return "undefined", [f"Couldn't evaluate with {_sub_str(var_vals)}"]
        if lv.has(sp.zoo, sp.nan) or rv.has(sp.zoo, sp.nan) or _num(lv) is None or _num(rv) is None:
            lines.append(f"With {_sub_str(var_vals)}, {pretty(eq.lhs)} = {pretty(eq.rhs)} is undefined "
                         f"(division by zero) — this value is not allowed.")
            return "undefined", lines
        if isinstance(eq, sp.Eq):
            ok = abs(_num(lv) - _num(rv)) <= TOL * max(1.0, abs(_num(rv)))
            sym = "=" if ok else "≠"
        else:
            try:
                ok = bool(type(eq)(lv, rv))
            except TypeError:
                ok = False
            sym = {"StrictLessThan": "<", "StrictGreaterThan": ">", "LessThan": "≤",
                   "GreaterThan": "≥", "Unequality": "≠"}.get(type(eq).__name__, "?")
            sym = sym if ok else f"is not {sym}"
        lines.append(f"Check {_sub_str(var_vals)} in {pretty(eq.lhs)} {_rel_symbol(eq)} {pretty(eq.rhs)}: "
                     f"left side = {pretty(lv)}, right side = {pretty(rv)} "
                     f"{'✓' if ok else '✗'}")
        if not ok:
            status = "fail"
    return status, lines


def _rel_symbol(eq) -> str:
    return {"Equality": "=", "StrictLessThan": "<", "StrictGreaterThan": ">", "LessThan": "≤",
            "GreaterThan": "≥", "Unequality": "≠"}.get(type(eq).__name__, "=")


def fmt_decimal(v, places: Optional[int] = None) -> str:
    if places is not None and places >= 0:
        return f"{float(v):.{places}f}"
    x = float(sp.N(v, 15))
    s = f"{x:.6f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def diagnose_number(c, k, raw: str, places: Optional[int]) -> tuple[str, str]:
    zc, zk = _num(c), _num(k)
    if zc is None or zk is None:
        return "Wrong value", ""
    if abs(zc) > TOL and abs(zc + zk) <= TOL * max(1, abs(zc)):
        return "Sign error", "The key has the opposite sign."
    if abs(zc) > TOL and abs(zk) > TOL and abs(zc * zk - 1) <= TOL:
        return "Reciprocal", "The key gives the reciprocal (the fraction is flipped)."
    if abs(zc) > TOL and abs(zk) > TOL and abs(zc.imag) < TOL:
        ratio = zk.real / zc.real
        for p in (10, 100, 1000, 0.1, 0.01, 0.001):
            if abs(ratio - p) <= 1e-9 * p:
                return "Decimal point error", f"The key's decimal point is in the wrong place (off by a factor of {p:g})."
    d = places if places is not None else decimal_places(raw)
    if d is not None and abs(zc.real - zk.real) <= 1.5 * 10 ** (-d) and abs(zc.imag) < TOL:
        r = round_half_up(c, d)
        return "Rounding error", (f"{fmt_decimal(c)} rounded to {d} decimal place{'s' if d != 1 else ''} "
                                  f"is {fmt_decimal(r, d)}, not {raw.strip()}.")
    return "Wrong value", ""


# ----------------------------------------------------------------- per-kind comparison

def compare(sol: Solution, key_raw: str) -> Comparison:
    try:
        fn = {
            "number": _cmp_number, "percent": _cmp_number, "text": _cmp_text,
            "expr": _cmp_expr, "literal": _cmp_expr, "factor": _cmp_factor,
            "solutions": _cmp_solutions, "interval": _cmp_interval, "tuple": _cmp_tuple,
            "stdev": _cmp_stdev,
        }[sol.kind]
    except KeyError:
        return Comparison(VERDICT_REVIEW, message=f"No comparison rule for answer type '{sol.kind}'.")
    try:
        return fn(sol, key_raw)
    except ParseError as exc:
        return Comparison(VERDICT_REVIEW, error_type="Key not understood",
                          message=f"Couldn't read the key's answer \"{key_raw}\" ({exc}). "
                                  f"Computed answer: {sol.display}.")


def _cmp_text(sol: Solution, key_raw: str) -> Comparison:
    k = key_raw.strip().lower().rstrip(".")
    if sol.value == "undefined":
        if re.search(r"undefined|no slope|vertical", k):
            return Comparison(VERDICT_CORRECT)
    elif sol.value == "no mode":
        if re.search(r"no mode|none", k):
            return Comparison(VERDICT_CORRECT)
    return Comparison(VERDICT_WRONG, "Wrong value",
                      f"The key says \"{key_raw}\" but the correct answer is {sol.display}.")


def _cmp_number(sol: Solution, key_raw: str) -> Comparison:
    ans = parse_number_answer(key_raw)
    if ans.kind == "text":
        return Comparison(VERDICT_WRONG, "Wrong value",
                          f"The key says \"{key_raw}\" but the answer is {sol.display}.")
    c, k = sol.value, ans.value
    if sol.kind == "percent":
        cands = [k * 100] if ans.percent else [k, k * 100]
    else:
        cands = [k]
    for kv in cands:
        if numbers_equal(c, kv, key_raw, sol.places):
            if sol.simplest_form and _unreduced_fraction(key_raw):
                return Comparison(VERDICT_INCOMPLETE, "Not in simplest form",
                                  f"The key's value is right but {_unreduced_fraction(key_raw)} "
                                  f"is not in simplest form. Write it as {sol.display}.", key_value=kv)
            return Comparison(VERDICT_CORRECT, key_value=kv)
    kv = cands[0]
    etype, detail = diagnose_number(c, kv, key_raw, sol.places)
    if sol.method == "rounding":
        etype = "Rounding error"
        detail = f"{sol.steps[0].split(':')[0]} gives {sol.display}, not {key_raw.strip()}."
    msg = f"The key says {key_raw.strip()}, but the correct answer is {sol.display}."
    if detail:
        msg += " " + detail
    return Comparison(VERDICT_WRONG, etype, msg, key_value=kv)


def _cmp_stdev(sol: Solution, key_raw: str) -> Comparison:
    """Books differ on population (÷n) vs sample (÷(n−1)) standard deviation: accept either."""
    ans = parse_number_answer(key_raw)
    pop, sample = sol.value
    places = sol.places
    raw = key_raw
    if decimal_places(raw) is None and places is None:
        # a whole-number key like "4" is a rounded value
        places = 0
    for v in (pop, sample):
        if numbers_equal(v, ans.value, raw, places):
            return Comparison(VERDICT_CORRECT, key_value=ans.value)
    return Comparison(VERDICT_WRONG, "Wrong value",
                      f"The key says {key_raw.strip()}, but the standard deviation is {sol.display}.",
                      key_value=ans.value)


def _unreduced_fraction(raw: str) -> Optional[str]:
    import math
    for a, b in re.findall(r"(?<![\d.])(\d+)\s*/\s*(\d+)(?![\d.])", raw):
        if int(b) != 0 and math.gcd(int(a), int(b)) > 1:
            return f"{a}/{b}"
    return None


def _cmp_expr(sol: Solution, key_raw: str) -> Comparison:
    ans = parse_expr_answer(key_raw)
    eq = exprs_equal(sol.value, ans.value)
    if eq is True:
        return Comparison(VERDICT_CORRECT, key_value=ans.value)
    if eq is None:
        return Comparison(VERDICT_REVIEW, "Can't confirm",
                          f"Couldn't confirm whether the key's \"{key_raw}\" equals {sol.display}.",
                          key_value=ans.value)
    checks = []
    syms = sorted(sol.value.free_symbols | ans.value.free_symbols, key=str)
    if syms:
        pt = {s: sp.Integer(i + 2) for i, s in enumerate(syms)}
        checks.append(f"Test with {_sub_str(pt)}: correct answer gives {pretty(sp.simplify(sol.value.subs(pt)))}, "
                      f"key gives {pretty(sp.simplify(ans.value.subs(pt)))}")
    etype = "Wrong expression"
    if exprs_equal(sol.value, -ans.value) is True:
        etype = "Sign error"
    return Comparison(VERDICT_WRONG, etype,
                      f"The key says {key_raw.strip()}, but the correct answer is {sol.display}."
                      + (" The key has the opposite sign." if etype == "Sign error" else ""),
                      checks, key_value=ans.value)


def _cmp_factor(sol: Solution, key_raw: str) -> Comparison:
    original = sol.value
    content, factors = sp.factor_list(original)
    prime = abs(content) == 1 and len(factors) == 1 and factors[0][1] == 1
    if re.search(r"prime|not factorable|cannot be factored|can't be factored|does not factor", key_raw, re.I):
        if prime:
            return Comparison(VERDICT_CORRECT)
        return Comparison(VERDICT_WRONG, "Wrong factoring",
                          f"The key says the expression can't be factored, but it factors as {sol.display}.")
    ans = parse_expr_answer(key_raw)
    eq = exprs_equal(original, ans.value)
    if eq is None:
        return Comparison(VERDICT_REVIEW, "Can't confirm",
                          f"Couldn't confirm whether the key's \"{key_raw}\" equals {sol.display}.")
    if eq is False:
        checks = []
        syms = sorted(original.free_symbols, key=str)
        pt = {s: sp.Integer(i + 2) for i, s in enumerate(syms)}
        checks.append(f"Multiply out the key's answer: {pretty(sp.expand(ans.value))} "
                      f"(should be {pretty(sp.expand(original))})")
        if syms:
            checks.append(f"Test with {_sub_str(pt)}: original = {pretty(original.subs(pt))}, "
                          f"key = {pretty(ans.value.subs(pt))}")
        return Comparison(VERDICT_WRONG, "Wrong factoring",
                          f"The key's factoring {key_raw.strip()} does not multiply back to the "
                          f"original expression. Correct factoring: {sol.display}.", checks)
    # equivalent: is it completely factored?
    try:
        tree = parse_math(re.sub(r"^\s*[a-zA-Z]\s*=\s*", "", key_raw), evaluate=False)
    except ParseError:
        return Comparison(VERDICT_CORRECT)
    for f in (tree.args if isinstance(tree, sp.Mul) else (tree,)):
        base = f.base if isinstance(f, sp.Pow) else f
        if not base.free_symbols:
            continue
        try:
            b = sp.sympify(base)
            c2, fs = sp.factor_list(b)
        except Exception:  # noqa: BLE001
            continue
        nontrivial = sum(m for _, m in fs)
        if nontrivial > 1 or (abs(c2) != 1 and len(fs) >= 1):
            return Comparison(VERDICT_INCOMPLETE, "Not completely factored",
                              f"The key's answer {key_raw.strip()} is equal to the expression but not "
                              f"completely factored: {pretty(b)} = {pretty(sp.factor(b))}. "
                              f"Complete factoring: {sol.display}.")
    return Comparison(VERDICT_CORRECT)


def _match_values(computed: list, keyvals: list, raw: str, places) -> tuple[list, list]:
    """Return (unmatched key values, computed values missing from key)."""
    unmatched_key = []
    used = set()
    for k in keyvals:
        hit = None
        for i, c in enumerate(computed):
            if i not in used and numbers_equal(c, k, raw, places):
                hit = i
                break
        if hit is None:
            unmatched_key.append(k)
        else:
            used.add(hit)
    missing = [c for i, c in enumerate(computed) if i not in used]
    return unmatched_key, missing


def _cmp_solutions(sol: Solution, key_raw: str) -> Comparison:
    x = sol.variables[0] if sol.variables else sp.Symbol("x")
    C = sol.value
    ans = parse_solution_set(key_raw)
    name = str(x)
    eqs = sol.equations

    def check(vals):
        lines, bad = [], []
        for v in vals:
            st, ls = plug_in(eqs, {x: v}) if eqs else ("ok", [])
            lines += ls
            if st != "ok":
                bad.append((v, st))
        return bad, lines

    if ans.kind == "empty":
        if C == sp.S.EmptySet:
            return Comparison(VERDICT_CORRECT)
        vals = list(C)[:3] if isinstance(C, sp.FiniteSet) else [sp.Integer(0), sp.Integer(7)]
        _, lines = check(vals)
        return Comparison(VERDICT_WRONG, "Wrong: there is a solution",
                          f"The key says no solution, but {sol.display} works.", lines)
    if ans.kind == "all_reals":
        if C == sp.S.Reals:
            return Comparison(VERDICT_CORRECT)
        test = next(t for t in (sp.Rational(37, 10), sp.Rational(-23, 7), sp.Integer(11))
                    if not (isinstance(C, sp.FiniteSet) and t in C))
        _, lines = check([test])
        return Comparison(VERDICT_WRONG, "Wrong: not all real numbers",
                          f"The key says all real numbers, but the answer is {sol.display}.", lines)
    keyvals = ans.value
    if any(getattr(v, "free_symbols", None) for v in keyvals):
        raise ParseError("expected numbers but the key's answer contains a variable")
    if C == sp.S.Reals or (isinstance(C, sp.Complement) and C.args[0] == sp.S.Reals):
        bad, lines = check(keyvals)
        return Comparison(VERDICT_WRONG, "Wrong: every number works",
                          f"The key lists {key_raw.strip()}, but the equation is true for "
                          f"{'all real numbers' if C == sp.S.Reals else pretty_set(C, name)}.", lines)
    computed = list(C) if isinstance(C, sp.FiniteSet) else []
    dupes = False
    uniq = []
    for v in keyvals:  # "x = 6 or x = 6": the same value listed twice
        if any(numbers_equal(v, u) for u in uniq):
            dupes = True
        else:
            uniq.append(v)
    keyvals = uniq
    unmatched, missing = _match_values(computed, keyvals, key_raw, sol.places)
    if not unmatched and not missing:
        return Comparison(VERDICT_CORRECT, key_value=keyvals)
    bad, lines = check(unmatched)
    good_unmatched = [v for v in unmatched if v not in [b for b, _ in bad]]
    if good_unmatched:
        return Comparison(VERDICT_REVIEW, "Solver disagreement",
                          f"The key's value(s) {', '.join(f'{name} = {pretty(v)}' for v in good_unmatched)} "
                          f"check out when plugged in, but the solver found {sol.display}. Please review.",
                          lines, key_value=keyvals)
    if not unmatched and missing:
        _, mlines = check(missing)
        miss = ", ".join(f"{name} = {pretty(v)}" for v in missing)
        note = " (The key lists the same value twice — probably a sign was dropped.)" if dupes else ""
        return Comparison(VERDICT_INCOMPLETE, "Missing solution",
                          f"The key's answer is incomplete: it is missing {miss}. "
                          f"All solutions: {sol.display}.{note}", mlines, key_value=keyvals)
    # some key values fail the plug-in check
    parts = []
    undefined = [v for v, st in bad if st == "undefined"]
    failing = [v for v, st in bad if st == "fail"]
    etype = "Wrong value"
    if undefined:
        etype = "Extraneous solution"
        parts.append(f"{', '.join(f'{name} = {pretty(v)}' for v in undefined)} is not allowed "
                     f"(it makes a denominator zero or is outside the domain), so it is an extraneous solution")
    if failing:
        parts.append(f"{', '.join(f'{name} = {pretty(v)}' for v in failing)} "
                     f"{'does' if len(failing) == 1 else 'do'} not satisfy the equation")
    extra = ""
    if len(failing) == 1 and len(missing) == 1 and not undefined:
        e2, d2 = diagnose_number(missing[0], failing[0], key_raw, sol.places)
        if e2 != "Wrong value":
            etype = e2
            extra = " " + d2
    msg = (f"The key says {key_raw.strip()}, but {' and '.join(parts)}. "
           f"The correct answer is {sol.display}.{extra}")
    if missing and len(keyvals) > len(unmatched):
        msg += f" (The key is also missing {', '.join(f'{name} = {pretty(v)}' for v in missing)}.)"
    return Comparison(VERDICT_WRONG, etype, msg, lines, key_value=keyvals)


def _sets_equal(a: sp.Set, b: sp.Set) -> bool:
    try:
        d1 = sp.Complement(a, b).simplify() if hasattr(sp.Complement(a, b), "simplify") else sp.Complement(a, b)
        d2 = sp.Complement(b, a)
        return d1 == sp.S.EmptySet and d2 == sp.S.EmptySet
    except Exception:  # noqa: BLE001
        return False


def _point_in(st: sp.Set):
    if isinstance(st, sp.FiniteSet):
        return next(iter(st))
    if isinstance(st, sp.Union):
        return _point_in(st.args[0])
    if isinstance(st, sp.Interval):
        a, b = st.start, st.end
        if a == -sp.oo and b == sp.oo:
            return sp.Integer(0)
        if a == -sp.oo:
            return sp.floor(b) - 1
        if b == sp.oo:
            return sp.ceiling(a) + 1
        return (a + b) / 2
    return None


def _cmp_interval(sol: Solution, key_raw: str) -> Comparison:
    x = sol.variables[0]
    ans = parse_interval_answer(key_raw)
    C, K = sol.value, ans.value
    if _sets_equal(C, K):
        return Comparison(VERDICT_CORRECT, key_value=K)
    only_key = sp.Complement(K, C)
    only_sol = sp.Complement(C, K)
    lines = []
    status_key_pts = []
    for st, label in ((only_key, "key"), (only_sol, "solution")):
        if st == sp.S.EmptySet:
            continue
        p = _point_in(st)
        if p is None:
            continue
        status, ls = plug_in(sol.equations, {x: p})
        lines += ls
        if label == "key":
            status_key_pts.append(status)
    if status_key_pts and all(s == "ok" for s in status_key_pts):
        return Comparison(VERDICT_REVIEW, "Solver disagreement",
                          f"The key's answer {key_raw.strip()} differs from the computed {sol.display}, "
                          f"but a test point from the key's answer still works. Please review.", lines)
    etype = "Wrong inequality solution"
    detail = ""
    boundary_only = isinstance(only_key, sp.FiniteSet) or isinstance(only_sol, sp.FiniteSet)
    if boundary_only and (only_key == sp.S.EmptySet or isinstance(only_key, sp.FiniteSet)) \
            and (only_sol == sp.S.EmptySet or isinstance(only_sol, sp.FiniteSet)):
        etype = "Endpoint error"
        detail = (" The endpoint is wrong: check whether it should be included (≤, ≥, closed bracket) "
                  "or excluded (<, >, open parenthesis).")
    else:
        rev = sp.Complement(sp.S.Reals, C)
        d1, d2 = sp.Complement(rev, K), sp.Complement(K, rev)
        if all(d == sp.S.EmptySet or isinstance(d, sp.FiniteSet) for d in (d1, d2)):
            etype = "Inequality sign reversed"
            detail = (" The inequality points the wrong way. (Remember to flip the sign when "
                      "multiplying or dividing both sides by a negative number.)")
    return Comparison(VERDICT_WRONG, etype,
                      f"The key says {key_raw.strip()}, but the correct answer is {sol.display}.{detail}",
                      lines, key_value=K)


def _cmp_tuple(sol: Solution, key_raw: str) -> Comparison:
    ans = parse_tuple_answer(key_raw, sol.variables)
    if sol.value in ("empty", "infinite"):
        if ans.kind == sol.value:
            return Comparison(VERDICT_CORRECT)
        return Comparison(VERDICT_WRONG, "Wrong system solution",
                          f"The key says {key_raw.strip()}, but the system has {sol.display}.")
    if ans.kind != "tuple":
        lines = plug_in(sol.equations, dict(zip(sol.variables, sol.value)))[1]
        return Comparison(VERDICT_WRONG, "Wrong system solution",
                          f"The key says {key_raw.strip()}, but the system has exactly one solution: "
                          f"{sol.display}.", lines)
    if len(ans.value) != len(sol.value):
        return Comparison(VERDICT_REVIEW, "Key not understood",
                          f"The key's answer {key_raw.strip()} has a different number of values than expected.")
    if all(numbers_equal(c, k, key_raw, sol.places) for c, k in zip(sol.value, ans.value)):
        return Comparison(VERDICT_CORRECT, key_value=ans.value)
    if not sol.equations:
        # computed directly (e.g. a midpoint): there is nothing else the key could satisfy
        return Comparison(VERDICT_WRONG, "Wrong point",
                          f"The key says {key_raw.strip()}, but the correct answer is {sol.display}.",
                          key_value=ans.value)
    status, lines = plug_in(sol.equations, dict(zip(sol.variables, ans.value)))
    if status == "ok":
        return Comparison(VERDICT_REVIEW, "Solver disagreement",
                          f"The key's {key_raw.strip()} satisfies the equations, but the solver found "
                          f"{sol.display}. Please review.", lines)
    etype = "Wrong system solution"
    if tuple(reversed(ans.value)) == tuple(sol.value):
        etype = "Coordinates swapped"
    msg = f"The key says {key_raw.strip()}, but the solution is {sol.display}."
    if etype == "Coordinates swapped":
        msg += " The x- and y-values are swapped."
    return Comparison(VERDICT_WRONG, etype, msg, lines, key_value=ans.value)
