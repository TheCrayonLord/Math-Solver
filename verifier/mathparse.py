"""Parse book math text and answer-key text into SymPy objects."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

import sympy as sp
from sympy.parsing.sympy_parser import (
    convert_xor, implicit_multiplication_application, parse_expr, rationalize,
    standard_transformations,
)

TRANSFORMS = standard_transformations + (implicit_multiplication_application, convert_xor, rationalize)

ALLOWED_WORDS = {"cbrt", "root4", "sqrt", "sin", "cos", "tan", "sec", "csc", "cot", "log", "ln", "abs", "pi", "oo",
                 "exp", "and", "or"}

UNICODE_MAP = {
    "−": "-", "–": "-", "—": "-", "‒": "-", "×": "*", "·": "*", "⋅": "*", "∙": "*", "÷": "/",
    "≤": "<=", "≥": ">=", "≦": "<=", "≧": ">=", "≠": "!=", "π": " pi ", "∞": "oo",
    "²": "^2", "³": "^3", "¹": "^1", "⁴": "^4", "⁵": "^5",
    "½": "(1/2)", "⅓": "(1/3)", "⅔": "(2/3)", "¼": "(1/4)", "¾": "(3/4)", "⅛": "(1/8)",
    "⁄": "/", "∕": "/", "′": "'", "’": "'", "“": '"', "”": '"', " ": " ",
    "ℝ": " all real numbers ", "∅": " no solution ", "∪": " U ",
}

NUMBER_WORDS = {"tenth": 1, "tenths": 1, "hundredth": 2, "hundredths": 2, "thousandth": 3,
                "thousandths": 3, "ten-thousandth": 4, "whole number": 0, "one": 0, "ones": 0,
                "integer": 0, "unit": 0, "ten": -1, "tens": -1, "hundred": -2, "hundreds": -2,
                "thousand": -3, "thousands": -3, "cent": 2, "penny": 2}

ROUND_RE = re.compile(
    r"(?:round(?:ed)?|nearest|to the nearest)\s+(?:your answers?\s+)?(?:to\s+)?(?:the\s+)?(?:nearest\s+)?"
    r"(ten-thousandth|tenths?|hundredths?|thousandths?|whole number|integer|ones?|tens?|hundreds?|"
    r"thousands?|cent|penny)", re.I)
DECIMAL_PLACES_RE = re.compile(r"(\d+|one|two|three|four)\s+decimal\s+places?", re.I)


class ParseError(ValueError):
    pass


def rounding_places(text: str) -> Optional[int]:
    m = ROUND_RE.search(text)
    if m:
        return NUMBER_WORDS[m.group(1).lower()]
    m = DECIMAL_PLACES_RE.search(text)
    if m:
        w = m.group(1).lower()
        return {"one": 1, "two": 2, "three": 3, "four": 4}.get(w) or int(w)
    return None


SUPERSCRIPTS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺⁽⁾ⁿˣ", "0123456789-+()nx")
SUBSCRIPTS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")


def normalize(s: str) -> str:
    s = re.sub(r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺⁽⁾ⁿˣ]+",
               lambda m: "^(" + m.group(0).translate(SUPERSCRIPTS) + ")", s)
    s = re.sub(r"[₀₁₂₃₄₅₆₇₈₉]+", lambda m: "_" + m.group(0).translate(SUBSCRIPTS), s)
    for a, b in UNICODE_MAP.items():
        s = s.replace(a, b)
    s = s.replace("∛", " cbrt ").replace("∜", " root4 ")
    s = s.replace("√", " sqrt ")
    s = re.sub(r"(cbrt|root4)\s*(-?\d+(?:\.\d+)?|[a-zA-Z])(?![\w(])", r"\1(\2)", s)
    s = re.sub(r"(cbrt|root4)\s*\(", r"\1(", s)
    # sqrt followed by a number/symbol without parentheses
    s = re.sub(r"sqrt\s*(\d+(?:\.\d+)?|[a-zA-Z])(?![\w(])", r"sqrt(\1)", s)
    s = re.sub(r"sqrt\s*\(", "sqrt(", s)
    # absolute value bars
    for _ in range(3):
        s2 = re.sub(r"\|([^|]+)\|", r"Abs(\1)", s)
        if s2 == s:
            break
        s = s2
    # mixed numbers: 2 1/2 -> (2+1/2)
    s = re.sub(r"(?<![\d.^/)\w])(\d+)\s+(\d+)\s*/\s*(\d+)(?![\d.])", r"(\1+\2/\3)", s)
    # a simple fraction is one unit: 3/4 ÷ 7/8 means (3/4) ÷ (7/8)
    s = re.sub(r"(?<![\w.)^/+])(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)(?![\w.(/^])", r"(\1/\2)", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _symbols_in(s: str) -> dict:
    d = {"e": sp.E, "pi": sp.pi, "sqrt": sp.sqrt, "cbrt": lambda x: sp.real_root(x, 3),
         "root4": lambda x: sp.real_root(x, 4), "Abs": sp.Abs, "abs": sp.Abs,
         "ln": sp.log, "log": sp.log, "oo": sp.oo, "E": sp.E, "I": sp.Symbol("I"),
         "S": sp.Symbol("S"), "N": sp.Symbol("N"), "Q": sp.Symbol("Q"), "O": sp.Symbol("O"),
         "C": sp.Symbol("C")}
    for ch in set(re.findall(r"(?<![A-Za-z])([A-Za-z])(?![A-Za-z])", s)):
        if ch not in d and ch != "e":
            d[ch] = sp.Symbol(ch)
    return d


# Short English words that must not be read as products of variables (e.g. "is" = i·s)
STOP_WORDS = set("""a an and are as at be by can cost costs do does each for from had has have he her his
how if in is it its many more much not of on or per she sum than that the then them they this to total
was we were what when who why will with you your old new let use how all any one two six ten
find solve each than less more same make made take gets got buy buys sell sold""".split())


def check_words(s: str) -> None:
    """Raise if the text contains English words (it isn't pure math).

    Short letter runs like 'lw', 'Prt' or 'IR' are products of variables, as written in algebra.
    """
    for m in re.finditer(r"[A-Za-z]{2,}", s):
        w = m.group(0)
        lw = w.lower()
        if lw in ALLOWED_WORDS or w == "Abs":
            continue
        if len(w) >= 5:
            raise ParseError(f"contains words ('{w}')")
        if lw in STOP_WORDS:
            # a stop word next to another word is English ("x is 5"); inside math ("u + at") it's a product
            before = s[:m.start()].rstrip()
            after = s[m.end():].lstrip()
            if (before and before[-1].isalpha()) or (after and after[0].isalpha()):
                raise ParseError(f"contains words ('{w}')")


def parse_math(s: str, evaluate: bool = True) -> sp.Expr:
    s = normalize(s).strip().rstrip(".").strip()
    s = s.replace("$", "")
    if not s:
        raise ParseError("empty")
    check_words(s)
    if re.search(r"[<>=!]", s):
        raise ParseError("relation, not expression")
    s = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", s)  # 1,250 -> 1250
    s = re.sub(r"(\d)\s+(?=\d)", r"\1*", s) if re.search(r"\d\s+\d", s) else s
    s = re.sub(r"\[", "(", s)
    s = re.sub(r"\]", ")", s)
    s = s.replace("{", "(").replace("}", ")")
    try:
        with sp.evaluate(evaluate):
            expr = parse_expr(s, local_dict=_symbols_in(s), transformations=TRANSFORMS,
                              evaluate=evaluate)
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"cannot parse '{s}': {exc}") from exc
    if not isinstance(expr, sp.Basic) or isinstance(expr, (sp.Tuple,)):
        raise ParseError(f"not an expression: '{s}'")
    return expr


REL_SPLIT = re.compile(r"(<=|>=|!=|=|<|>)")
REL_OPS = {"<": sp.Lt, ">": sp.Gt, "<=": sp.Le, ">=": sp.Ge, "=": sp.Eq, "!=": sp.Ne}


def parse_relation_chain(s: str) -> list[tuple[sp.Expr, str, sp.Expr]]:
    """'-1 < x <= 4' -> [(-1,'<',x), (x,'<=',4)]"""
    s = normalize(s).strip().rstrip(".")
    s = s.replace("==", "=")
    parts = REL_SPLIT.split(s)
    if len(parts) < 3:
        raise ParseError("no relation")
    exprs = [parse_math(p) for p in parts[0::2]]
    ops = parts[1::2]
    return [(exprs[i], ops[i], exprs[i + 1]) for i in range(len(ops))]


# ----------------------------------------------------------------- answers

@dataclass
class Answer:
    kind: str  # number | expr | set | interval | tuple | empty | all_reals | infinite | text
    value: Any
    raw: str
    percent: bool = False
    var: Optional[str] = None


NO_SOLUTION_RE = re.compile(r"^(?:no\s+(?:real\s+)?solutions?|none|no\s+real\s+solutions?|no\s+real\s+(?:roots|numbers)|"
                            r"\{\s*\}|empty\s+set|∅|inconsistent)\.?$", re.I)
ALL_REALS_RE = re.compile(r"^(?:all\s+real\s+numbers|infinitely\s+many(?:\s+solutions)?|"
                          r"identity|every\s+real\s+number|\(\s*-oo\s*,\s*oo\s*\)|"
                          r"all\s+reals|true\s+for\s+all\s+x|R)\.?$", re.I)
UNDEFINED_RE = re.compile(r"^(?:undefined|no\s+slope|not\s+defined)\.?$", re.I)
UNIT_TAIL_RE = re.compile(
    r"\s*(?:sq(?:uare)?\.?\s+|cu(?:bic)?\.?\s+)?(?:units?|cm|mm|km|m|in\.?|inch(?:es)?|ft\.?|feet|foot|"
    r"yd\.?|yards?|mi\.?|miles?|meters?|centimeters?|kilometers?|g|kg|lb\.?|lbs\.?|pounds?|oz|ounces?|"
    r"grams?|kilograms?|L|mL|liters?|gal(?:lons?)?|qt|quarts?|pints?|cups?|s|sec|seconds?|min|minutes?|"
    r"h|hr|hours?|days?|weeks?|years?|degrees?|°|dollars?|cents?|mph|people|students|"
    r"items|books|tickets)(?:\^?[23²³])?\.?\s*$", re.I)


def strip_units(s: str) -> tuple[str, str]:
    m = UNIT_TAIL_RE.search(s)
    if m and m.start() > 0 and re.search(r"[\d)]\s*$", s[:m.start()]):
        return s[:m.start()].strip(), s[m.start():].strip()
    return s, ""


def _strip_var_prefix(s: str) -> tuple[str, Optional[str]]:
    m = re.match(r"^\s*([a-zA-Z])\s*=\s*(?!=)(.*)$", s)
    if m and not re.search(r"[<>]", m.group(2)):
        return m.group(2), m.group(1)
    return s, None


def split_top_level(s: str, seps=(",", ";")) -> list[str]:
    parts, depth, cur = [], 0, ""
    for ch in s:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if depth == 0 and ch in seps:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p.strip() for p in parts if p.strip()]


def _clean(raw: str) -> str:
    s = normalize(raw).strip()
    s = re.sub(r"^(?:answer|ans)\s*[:.]\s*", "", s, flags=re.I)
    # remarks in parentheses: "all real numbers (infinitely many solutions)", "none (discriminant -12)"
    s = re.sub(r"\s*\((?=[^()]*[A-Za-z]{4,})[^()]*\)\s*$", "", s)
    s = s.strip().rstrip(".").strip()
    s = s.replace("$", "")
    return s


def parse_number_answer(raw: str) -> Answer:
    s = _clean(raw)
    s, _ = strip_units(s)
    s, var = _strip_var_prefix(s)
    s, _ = strip_units(s)
    if UNDEFINED_RE.match(s):
        return Answer("text", "undefined", raw)
    pct = s.endswith("%")
    if pct:
        s = s[:-1].strip()
    s = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", s)
    v = parse_math(s)
    if pct:
        return Answer("number", v / 100, raw, percent=True, var=var)
    return Answer("number", v, raw, var=var)


def parse_expr_answer(raw: str) -> Answer:
    s = _clean(raw)
    s = re.sub(r"^\s*(?:[a-zA-Z]\(\s*[a-zA-Z]\s*\)|[a-zA-Z])\s*=\s*(?!=)", "", s)
    return Answer("expr", parse_math(s), raw)


def _expand_pm(piece: str) -> list[str]:
    """'(−3 ± √65)/4' -> ['(−3 + √65)/4', '(−3 - √65)/4']"""
    p = piece.replace("+/-", "±").replace("+-", "±")
    if "±" in p:
        return _expand_pm(p.replace("±", "+", 1)) + _expand_pm(p.replace("±", "-", 1))
    return [p]


def parse_solution_set(raw: str) -> Answer:
    s = _clean(raw)
    if NO_SOLUTION_RE.match(s.strip()):
        return Answer("empty", sp.S.EmptySet, raw)
    if ALL_REALS_RE.match(s.strip()):
        return Answer("all_reals", sp.S.Reals, raw)
    s = s.replace("{", "").replace("}", "")
    pieces = []
    for chunk in re.split(r"\s+or\s+|\s+and\s+", s):
        pieces.extend(split_top_level(chunk))
    values = []
    var = None
    for p in pieces:
        p2, v = _strip_var_prefix(p)
        var = var or v
        for q in _expand_pm(p2):
            values.append(parse_math(q))
    if not values:
        raise ParseError("no values")
    return Answer("set", values, raw, var=var)


def _interval_from_notation(s: str) -> Optional[sp.Set]:
    pieces = re.split(r"\s+U\s+|\s*∪\s*", s)
    sets = []
    for p in pieces:
        m = re.fullmatch(r"\s*([\[(])\s*([^,]+?)\s*,\s*([^,]+?)\s*([\])])\s*", p)
        if not m:
            return None
        a, b = parse_math(m.group(2)), parse_math(m.group(3))
        sets.append(sp.Interval(a, b, left_open=m.group(1) == "(", right_open=m.group(4) == ")"))
    return sp.Union(*sets)


def parse_interval_answer(raw: str, var: Optional[sp.Symbol] = None) -> Answer:
    s = _clean(raw)
    if NO_SOLUTION_RE.match(s):
        return Answer("interval", sp.S.EmptySet, raw)
    if ALL_REALS_RE.match(s):
        return Answer("interval", sp.S.Reals, raw)
    if re.search(r"[<>]", s):
        sets = []
        for chunk in re.split(r"\s+or\s+", s):
            parts = [p for p in re.split(r"\s+and\s+|,", chunk) if p.strip()]
            cur = sp.S.Reals
            for part in parts:
                for lhs, op, rhs in parse_relation_chain(part):
                    rel = REL_OPS[op](lhs, rhs)
                    syms = list(rel.free_symbols)
                    if len(syms) != 1:
                        raise ParseError("inequality needs one variable")
                    cur = cur.intersect(rel.as_set() if op != "!=" else
                                        sp.solveset(rel, syms[0], sp.S.Reals))
            sets.append(cur)
        return Answer("interval", sp.Union(*sets), raw)
    st = _interval_from_notation(s)
    if st is not None:
        return Answer("interval", st, raw)
    raise ParseError("not an inequality or interval")


def parse_tuple_answer(raw: str, variables: list[sp.Symbol]) -> Answer:
    s = _clean(raw)
    if NO_SOLUTION_RE.match(s):
        return Answer("empty", None, raw)
    if re.match(r"^(?:infinitely\s+many|all\s+points|same\s+line|dependent)", s, re.I):
        return Answer("infinite", None, raw)
    m = re.fullmatch(r"\(\s*(.+)\s*\)", s)
    if m and "=" not in s:
        vals = split_top_level(m.group(1), (",",))
        return Answer("tuple", tuple(parse_math(v) for v in vals), raw)
    # x = 2, y = 3
    assigns = {}
    for p in re.split(r",|;|\s+and\s+", s):
        if not p.strip():
            continue
        mm = re.fullmatch(r"\s*([a-zA-Z])\s*=\s*(.+)", p)
        if not mm:
            raise ParseError("not an ordered pair")
        assigns[mm.group(1)] = parse_math(mm.group(2))
    names = [str(v) for v in variables]
    if set(assigns) != set(names):
        raise ParseError("variables don't match")
    return Answer("tuple", tuple(assigns[n] for n in names), raw)


# ----------------------------------------------------------------- display

def pretty(e: Any) -> str:
    if isinstance(e, (list, tuple)):
        inner = ", ".join(pretty(x) for x in e)
        return f"({inner})" if isinstance(e, tuple) else inner
    if isinstance(e, sp.Set):
        return pretty_set(e)
    s = sp.sstr(e)
    s = s.replace("**", "^")
    s = re.sub(r"sqrt\((\d+)\)", r"√{\1}", s)
    s = s.replace("sqrt(", "√(")
    s = re.sub(r"(\d)\*(?=[a-zA-Z(√])", r"\1", s)
    s = re.sub(r"\)\*\(", ")(", s)
    s = re.sub(r"(?<=[a-zA-Z])\*(?=[a-zA-Z(])", "", s)
    s = re.sub(r"√\{(\d+)\}\*", r"√\1·", s)
    s = re.sub(r"√\{(\d+)\}", r"√\1", s)
    s = s.replace("*", "·").replace("pi", "π").replace("oo", "∞")
    s = re.sub(r"Abs\(([^()]*)\)", r"|\1|", s)
    return s


def pretty_set(st: sp.Set, var: str = "x") -> str:
    if st == sp.S.EmptySet:
        return "no solution"
    if st == sp.S.Reals:
        return "all real numbers"
    if isinstance(st, sp.FiniteSet):
        return ", ".join(f"{var} = {pretty(v)}" for v in sorted(st, key=_sort_key))
    if isinstance(st, sp.Interval):
        a, b = st.start, st.end
        if a == -sp.oo:
            return f"{var} {'<' if st.right_open else '≤'} {pretty(b)}"
        if b == sp.oo:
            return f"{var} {'>' if st.left_open else '≥'} {pretty(a)}"
        return (f"{pretty(a)} {'<' if st.left_open else '≤'} {var} "
                f"{'<' if st.right_open else '≤'} {pretty(b)}")
    if isinstance(st, sp.Union):
        return " or ".join(pretty_set(a, var) for a in st.args)
    if isinstance(st, sp.Complement) and st.args[0] == sp.S.Reals:
        return f"all real numbers except {pretty_set(st.args[1], var)}"
    return sp.sstr(st)


def _sort_key(v):
    try:
        return float(sp.N(v))
    except Exception:  # noqa: BLE001
        return 0.0


def decimal_places(raw: str) -> Optional[int]:
    """Number of decimal places shown in a key answer like '12.40' -> 2. None if not a decimal."""
    m = re.search(r"\d*\.(\d+)(?!\d)", raw)
    if m and not re.search(r"\d\s*/\s*\d", raw):
        return len(m.group(1))
    return None
