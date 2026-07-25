#!/usr/bin/env python3
"""
validate.py — offline lint for the Tradovate alert DSL.

Mirrors the alert DSL grammar. The NinjaTrader/Tradovate trading
platform enforces that grammar. Offline means no server round-trip.
It reports structural problems before `create_alert` accepts an
expression and silently drops it.

Grammar (summary; see references/dsl-grammar.md for the full write-up):

    expr         = logicalExpr (AND|OR|XOR logicalExpr)*
    logicalExpr  = compareExpr
    compareExpr  = arithmeticExpr compareOp arithmeticExpr
    arithmeticExpr = term (("+"|"-") term)*
    term         = factor (("*"|"/") factor)*
    factor       = number | funcCall | "(" arithmeticExpr ")"
    funcCall     = funcName "(" subject ")"
    compareOp    = ">"|">="|"=>"|"<"|"<="|"=<"|"="|"=="|"!="|"<>"
    subject      = [$@]?[\\w\\s\\-\\+/|]+      (NO quotes; slash is allowed)

Checks performed:

  1. Balanced parentheses.
  2. At least one comparison operator present at top level.
  3. Each `name(...)` has a valid function name (whitelist from the DSL
     catalog) — unless --allow-unknown-functions.
  4. Subject inside each `(...)` matches the subject regex.
  5. AND/OR/XOR chaining only at top level (not nested in parens).
  6. No double-quoted subjects. The tool rejects "ESU6" with a hint.

Input: expression on stdin OR --expression flag.

Output: JSON with:
  {
    "expression": "...",
    "valid": true|false,
    "errors":   [...],
    "warnings": [...],
    "functions_used": [...],
    "subjects_used":  [...]
  }

Exit code: 0 on valid, 1 on errors, 2 on bad input.

Usage:
    echo 'lastPrice(ESU6) > 7200 AND posOpenPLUsd(ESU6) < -300' | python3 validate.py
    python3 validate.py --expression 'netLiq(DEMO-ACCOUNT-1) < 5000'
    python3 validate.py --allow-unknown-functions  ...   # skip catalog check
"""

import argparse
import json
import re
import sys

# Canonical DSL function catalog.
# To check this catalog against the live server, call the MCP tool
# `describe(topic='index')` and compare the alert-function list it returns.
# Account entity — subject is the account name (e.g., "DEMO-ACCOUNT-1").
ACCOUNT_FUNCTIONS: set[str] = {
    "cashAmount",
    "dollarOpenPL",
    "dollarTotalPL",
    "netLiq",
    "initialMargin",
    "maintenanceMargin",
    "dayMargin",
    "totalUsedMargin",
    "positionMargin",
    "dailyLossLimit",
    "weekLoss",
    "weeklyLossLimit",
    "futuresOnlyNetLiq",
    "openCollateralReq",
}

# Contract entity — subject is the contract name (e.g., "ESU6", "BTC/USD").
CONTRACT_FUNCTIONS: set[str] = {
    "lastPrice",
    "change",
    "percentChange",
    "bidPrice",
    "offerPrice",
    "openPrice",
    "highPrice",
    "lowPrice",
    "settlementPrice",
}

# Position entity — subject is a contract name. The caller's account
# keys the position, by convention.
POSITION_FUNCTIONS: set[str] = {
    "netPos",
    "bought",
    "sold",
    "longPos",
    "shortPos",
    "posInitMargin",
    "posMaintMargin",
    "posInitMarginUsd",
    "posMaintMarginUsd",
    "posOpenPL",
    "posOpenPLUsd",
    "posRealizedPL",
    "posTotalPL",
}

# Currency entity — subject is a currency code (e.g., "USD", "EUR").
CURRENCY_FUNCTIONS: set[str] = {"currentRate"}

KNOWN_FUNCTIONS: set[str] = (
    ACCOUNT_FUNCTIONS | CONTRACT_FUNCTIONS | POSITION_FUNCTIONS | CURRENCY_FUNCTIONS
)

# Subject regex — mirrors the server's subject-parsing rule exactly.
SUBJECT_RE = re.compile(r"^[\$@]?[\w\s\-\+/|]+$")

# Comparison + logic operators we recognize.
COMPARE_OPS = ["==", ">=", "<=", "=<", "=>", "!=", "<>", ">", "<", "="]
LOGIC_OPS = ["AND", "OR", "XOR"]

# Regex that matches any logic-op as a whole word. The code uses it
# to split the expression into compare-expr segments.
LOGIC_OPS_RE = re.compile(r"\b(?:AND|OR|XOR)\b")

# Function-call shape. The negative lookahead keeps AND/OR/XOR out of
# the function-name match. Those are logic operators that happen to
# share the `keyword(…)` surface shape. Without that exclusion,
# `AND (lastPrice(NQU6)` would match as "function AND with subject
# lastPrice(NQU6" and poison downstream checks.
FUNC_CALL_RE = re.compile(r"\b(?!(?:AND|OR|XOR)\b)([A-Za-z][A-Za-z0-9_]*)\s*\(([^)]*)\)")


def _check_balanced_parens(expr: str) -> list[str]:
    errs: list[str] = []
    depth = 0
    for i, ch in enumerate(expr):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                errs.append(f"unmatched `)` at offset {i}")
                return errs
    if depth > 0:
        errs.append(f"unclosed `(` — {depth} open paren(s) at end of expression")
    return errs


def _check_no_quoted_subjects(expr: str) -> list[str]:
    if '"' in expr:
        return ['subject must not be quoted — write `lastPrice(ESU6)`, not `lastPrice("ESU6")`']
    if "'" in expr:
        return ["subject must not be single-quoted — use bare subject: `lastPrice(ESU6)`"]
    return []


def _extract_calls(expr: str) -> list[tuple[str, str]]:
    return [(m.group(1), m.group(2).strip()) for m in FUNC_CALL_RE.finditer(expr)]


def _check_has_comparison(expr: str) -> list[str]:
    for op in COMPARE_OPS:
        if op in expr:
            return []
    return [
        f"no comparison operator ({', '.join(COMPARE_OPS)}) — "
        "an alert expression must compare two numerics"
    ]


def _check_segments_have_compare(expr: str) -> list[str]:
    """Split on AND/OR/XOR as whole words. Each segment must be a
    complete comparison — contains a compare op AND has non-empty
    operands on both sides of it (catches `lastPrice(ESU6) >` with
    trailing op; `AND` / `... AND` / `... AND AND ...` dangling)."""
    segments = LOGIC_OPS_RE.split(expr)
    errs: list[str] = []
    # Longest-first so `>=` matches before `>`.
    compare_ops_sorted = sorted(COMPARE_OPS, key=len, reverse=True)
    for i, seg in enumerate(segments):
        seg = seg.strip()
        if not seg:
            errs.append(
                f"empty segment around AND/OR/XOR (position {i + 1} of {len(segments)}) — dangling or adjacent logic op"
            )
            continue
        # Find first compare-op occurrence in the segment.
        op_found: str | None = None
        op_pos = -1
        for op in compare_ops_sorted:
            idx = seg.find(op)
            if idx >= 0:
                op_found = op
                op_pos = idx
                break
        if op_found is None:
            errs.append(
                f"segment `{seg}` has no comparison op — each AND/OR/XOR operand must be a comparison"
            )
            continue
        lhs = seg[:op_pos].strip()
        rhs = seg[op_pos + len(op_found) :].strip()
        if not lhs:
            errs.append(f"segment `{seg}` has no left-hand side before `{op_found}`")
        if not rhs:
            errs.append(f"segment `{seg}` has no right-hand side after `{op_found}`")
    return errs


def _check_no_stray_words(expr: str) -> list[str]:
    """After stripping function calls and numbers, the remaining tokens
    should only be compare ops, logic ops, arithmetic ops, parens, and
    whitespace. A stray word like `BUT` means the parser will reject."""
    stripped = _strip_function_calls(expr)
    # Remove number literals
    stripped = re.sub(r"-?\d+(\.\d*)?", "", stripped)
    # Remove FUNC placeholders from strip-function-calls
    stripped = stripped.replace("FUNC", "")
    # Remove all legal non-word tokens
    for op in COMPARE_OPS + ["+", "-", "*", "/", "(", ")"]:
        stripped = stripped.replace(op, " ")
    # What's left should only be AND/OR/XOR or whitespace
    leftover_words = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", stripped)
    bad = [w for w in leftover_words if w not in LOGIC_OPS]
    if bad:
        return [f"stray word(s) outside grammar: {bad}. Legal between compares: AND, OR, XOR."]
    return []


def _strip_function_calls(expr: str) -> str:
    """Replace every funcName(subject) with a placeholder. This lets the
    check test whether any remaining parens are arithmetic grouping.
    FUNC_CALL_RE already excludes logic-op names via negative lookahead,
    so `AND (...)` stays intact for the flat-logic check to flag."""
    return FUNC_CALL_RE.sub("FUNC", expr)


def _check_logic_flat(expr: str) -> list[str]:
    """Alert DSL rejects parenthesized logical sub-expressions — each AND/OR/XOR
    must join two comparison expressions at top level."""
    stripped = _strip_function_calls(expr)
    # After stripping function calls, any remaining `(` `)` must wrap a pure
    # arithmetic expression — never an AND/OR/XOR.
    depth = 0
    inside_paren_buf: list[str] = []
    buffers: list[str] = []
    for ch in stripped:
        if ch == "(":
            if depth == 0:
                inside_paren_buf = []
            depth += 1
            inside_paren_buf.append(ch)
        elif ch == ")":
            depth -= 1
            inside_paren_buf.append(ch)
            if depth == 0:
                buffers.append("".join(inside_paren_buf))
                inside_paren_buf = []
        elif depth > 0:
            inside_paren_buf.append(ch)
    errs: list[str] = []
    for buf in buffers:
        for op in LOGIC_OPS:
            if re.search(rf"\b{op}\b", buf):
                errs.append(
                    f"AND/OR/XOR cannot appear inside `( ... )` — "
                    f"parens are arithmetic-only. Offending group: `{buf}`"
                )
                break
    return errs


def validate(expr: str, allow_unknown_functions: bool = False) -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    errors.extend(_check_balanced_parens(expr))
    errors.extend(_check_no_quoted_subjects(expr))
    errors.extend(_check_has_comparison(expr))
    errors.extend(_check_segments_have_compare(expr))
    errors.extend(_check_logic_flat(expr))
    errors.extend(_check_no_stray_words(expr))

    calls = _extract_calls(expr)
    functions_used: list[str] = []
    subjects_used: list[str] = []
    for fname, subject in calls:
        functions_used.append(fname)
        subjects_used.append(subject)
        if not SUBJECT_RE.match(subject):
            errors.append(
                f"subject `{subject}` contains disallowed characters. "
                f"Allowed: letters, digits, space, `_ - + / |`, optional leading `$` or `@`."
            )
        if not allow_unknown_functions and fname not in KNOWN_FUNCTIONS:
            near = [k for k in KNOWN_FUNCTIONS if k.lower().startswith(fname[:3].lower())]
            if near:
                hint = f" (did you mean: {', '.join(sorted(near)[:5])}?)"
            else:
                hint = f" (accepted functions: {', '.join(sorted(KNOWN_FUNCTIONS))})"
            errors.append(f"unknown function `{fname}`{hint}")

    if not calls:
        warnings.append("expression has no function calls — it will be constant-valued")

    return {
        "expression": expr,
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "functions_used": sorted(set(functions_used)),
        "subjects_used": sorted(set(subjects_used)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Offline validate an alert-DSL expression.",
        allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python3 validate.py --expression 'lastPrice(ESU6) > 7200'\n"
            "  python3 validate.py --expression "
            "'lastPrice(ESU6) > 7200 AND posOpenPLUsd(ESU6) < -300'\n"
            "  echo 'netLiq(DEMO-ACCOUNT-1) < 5000' | python3 validate.py\n"
            "  python3 validate.py --allow-unknown-functions "
            "--expression 'brandNewFunc(ESU6) > 1'\n"
            "\n"
            "Exit codes: 0 = valid, 1 = DSL errors, 2 = bad input."
        ),
    )
    parser.add_argument(
        "--expression",
        metavar="TEXT",
        help=(
            "One alert-DSL expression to validate, as a single string. "
            "Default: read the expression from stdin."
        ),
    )
    parser.add_argument(
        "--allow-unknown-functions",
        action="store_true",
        help=(
            "Accept a function name outside the 37-name catalog. "
            "Use it when the server adds a function this script does not know yet. "
            "Default: off, so an unknown name is an error."
        ),
    )
    args = parser.parse_args()

    if args.expression is not None:
        expr = args.expression
    else:
        expr = sys.stdin.read().strip()

    if not expr:
        print(json.dumps({"error": "no expression on stdin or --expression"}), file=sys.stderr)
        return 2

    result = validate(expr, allow_unknown_functions=args.allow_unknown_functions)
    print(json.dumps(result, indent=2))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    sys.exit(main())
