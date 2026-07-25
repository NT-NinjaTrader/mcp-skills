# Survivorship caveat

**Single-trade counterfactuals are not rule validations.**

This skill answers "what would THIS trade have returned under exit rule X?"
It does not answer "what would exit rule X return over all my trades?"
The two questions look similar, but they have opposite failure modes.

## The trap

A user runs a few what-ifs on a winning trade:
- "What if 2R target?" → +$3,200 (beat the actual +$2,800)
- "What if 1×ATR trail?" → +$2,900 (beat the actual)
- "What if BE@1R?" → $0 (underperformed)

Conclusion the user WANTS to draw: "I should switch to 2R targets."

Conclusion the data actually supports: "On this one trade, a 2R rule
outperformed the discretionary exit by $400."

This difference changes everything. A rule that converts one winner
into a bigger winner might be the SAME rule that turns a wobbly
winner into a -1R loser, when the market does not follow through. A
rule evaluation needs ALL the trades, and the ones where the rule
hurts you.

## How to narrate what-ifs

**Okay:**
> "With a 2R target, this ES trade would have closed at 7166 for
> +$3,200 — $400 better than your actual $2,800 exit."

**Not okay:**
> "You should use 2R targets — they're $400 better."

The first is a fact about this trade. The second is a rule claim
unsupported by a sample of 1.

## When the user asks for a rule recommendation

The user might ask: "Is 2R better than my current approach?"

Route them away from per-trade replay. Point them toward:

1. **`trade-journal`** → summary stats (win rate, profit factor across
   many trades). This gives good descriptive ground truth, but it is
   not a simulation.
2. **`trade-debrief`** → LLM-driven rule-mining, with the bundled
   prompt library (`06_correction_rules.md` specifically). The
   prompts explicitly require multi-trade evidence, before they
   recommend a rule.
3. **External backtest** — the MCP does not ship a rule-replay tool
   today. Tell the user plainly: "Validating a rule across your book
   is out of scope here. This skill shows what the rule did on this
   one trade. `trade-journal` summarizes your stats, and
   `trade-debrief` mines coaching-grade rules."

## Mandatory phrasing in the output

Every trade-replay output that surfaces a superior-looking counter-
factual should include a survivorship note. Suggested templates:

- "...that's what this specific trade would have done. Can't tell if
  a 2R rule across your book would be an improvement from one sample."
- "One-trade counterfactual. Route to `trade-debrief` for rule-level
  evaluation if you want to formalize."
- "This is a retrospective on ONE trade. N=1 is not a rule."

This phrasing is load-bearing. It separates a math fact for the user
from a lesson in cherry-picking.

## When to skip the caveat

Short, specific what-ifs that do not imply a rule change. "How far
did it go?" → MFE report. "Where did it touch?" → path. These are
descriptive, not prescriptive. They do not need the framing.

The caveat is for RULE-SHAPED what-ifs (2R target, ATR trail, BE pin)
that the user could apply from now on.
