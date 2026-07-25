# Alert DSL — grammar

This file documents the alert DSL grammar enforced by the
NinjaTrader/Tradovate trading platforms.

## Full grammar

```
expr            = logicalExpr (logicOp logicalExpr)*
logicalExpr     = compareExpr
compareExpr     = arithmeticExpr compareOp arithmeticExpr
arithmeticExpr  = term (("+" | "-") term)*
term            = factor (("*" | "/") factor)*
factor          = number | funcCall | "(" arithmeticExpr ")"
funcCall        = funcName "(" subject ")"

number          = -?\d+(\.\d*)?
funcName        = [A-Za-z][A-Za-z0-9_]*   (must match catalog — see dsl-functions.md)
subject         = [\$@]?[\w\s\-\+/|]+       (NO QUOTES)

compareOp       = ">" | ">=" | "=>" | "<" | "<=" | "=<" | "=" | "==" | "!=" | "<>"
logicOp         = AND | OR | XOR
```

## What each construct means

- **`funcCall`** — invokes a NumericCall with the given subject. `dsl-functions.md` lists the full catalog. At runtime, the subject becomes an entity name lookup: account, contract, position, or currency.
- **`arithmeticExpr`** — normal `+ - * /` with standard precedence. Parens `()` group arithmetic only — they CANNOT wrap a comparison or a logic expression.
- **`compareExpr`** — exactly one comparison between two arithmetic expressions. You can write `lastPrice(ESU6) - lastPrice(NQU6) > 100` (arithmetic on both sides).
- **`logicOp`** — combines two `compareExpr` results. Left-associative. **No nesting**: `A AND (B OR C)` is NOT valid. Only `A AND B OR C` (flat chain, left-to-right eval: `(A AND B) OR C`).

## Subject rules

- No quotes. `lastPrice(ESU6)` — not `lastPrice("ESU6")`. Always validate an expression with `scripts/validate.py` before you submit it.
- The subject can include `/` — `highPrice(BTC/USD)` works.
- Leading `$` marks index-like subjects — `lastPrice($TICK)`.
- The parser reserves a leading `@`. It appears in production data and is syntax-valid.
- A subject can include spaces — `lastPrice(ES SEP 2026)` would parse if that contract name existed. In practice, use the exact `symbol` field from `market_snapshot` or `search_contracts`.

## JSON shorthand

The server also accepts a JSON form that serializes to the
same AST:

```json
{
  "conjuction": "AND",
  "conditions": [
    {"l": "lastPrice", "op": ">", "r": "7200", "subj": "ESU6"},
    {"l": "posOpenPLUsd", "op": "<", "r": "-300", "subj": "ESU6"}
  ]
}
```

- `l` = left function name
- `op` = compare op
- `r` = right value (string; numeric literal)
- `rf` = optional right-function (for function-vs-function compares)
- `subj` = subject for `l`

Note the typo `conjuction` (not `conjunction`) is the literal key used
in production data — do not "fix" it.

Equivalent text form:
```
lastPrice(ESU6) > 7200 AND posOpenPLUsd(ESU6) < -300
```

Prefer the text form unless you're constructing programmatically.

## Runtime evaluation statuses

The interpreter returns one of these on failure (via `AlertExpressionInterpretationStatus`):

- `NoData` — subject exists but the field is unset (e.g., `settlementPrice` before settlement, `dayMargin` not yet populated).
- `AccessDenied` — subject is an account or contract the user cannot see.
- `NotFound(s)` — the interpreter cannot find the boolean function's subject. The current catalog has no boolean functions, so this rarely appears.
- `UnsupportedOperation(op)` — a compare/logic/arithmetic operator not in the lists above. This means a parse-vs-interpret mismatch — rare.
- `WrongArithmeticExpression` / `WrongLogicalExpression` — a structural malformation. This should not happen after a successful parse, but the evaluator returns it if it sees an unexpected AST shape.

If the expression returns `Right(status)` at runtime, the alert does NOT trigger.
The interpreter silently skips it until the inputs become evaluable.
This is why offline validation matters.
A typo in a function name or subject still passes `create_alert`, but the alert never fires.

## Boolean functions — reserved, not active

The grammar includes a `BooleanCall` node, but the server registers no boolean function.
So today, no boolean function name is callable.
If `list_alerts` returns an expression that references a boolean name, treat it as legacy data.

## Known gotchas (via real test cases)

- `highPrice(BTC/USD) >= 33000` — a `/` in the subject is valid.
- `1 >= 2 OR 3 < 4` — numeric-literal-only comparisons parse and evaluate; the alert just never fires (static false/true). Use this for testing, never for production alerts.
- Compare-only-once rule: `a > b > c` is NOT valid (a chained compare does not exist). Write `a > b AND b > c`.
