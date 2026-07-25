# Prompt selection — routing table

Map user intent to the right prompt template. Prompts live in `references/prompts/`. This skill bundles them and uses them verbatim. Do not modify them.

## Intent → prompt map

| User phrasing | Prompt file | Mode |
|---------------|-------------|------|
| "debrief me", "quick summary", "review today's session" | `07_daily_debrief.md` | Single session, ≤250 words |
| "what mistakes did I make", "find my errors", "what went wrong" | `01_mistake_identification.md` | Single session, fact-only observations |
| "find patterns", "what's my worst habit", "recurring behavior" | `02_pattern_extraction.md` | Single session, cluster by behavior |
| "score my trades", "grade each trade", "which was my best/worst" | `03_trade_scoring.md` | Single session, per-trade 0–100 |
| "how do I improve", "give me rules", "what should I change" | `06_correction_rules.md` | Single session, mechanical rule list |
| "this week", "last 5 days", "cluster across days" | `08_pattern_clustering.md` | Multi-day, behavioral clusters |
| "what's my edge so far", "expectancy", "win-rate × payoff ratio" | `09_expectancy_analysis.md` | Multi-day, statistical, descriptive of past sessions only |

## Combinations

- **Single-day analysis**: `01 → 03 → 07` (mistakes → scores → summary)
- **Weekly review**: `08 → 09 → 06` (clusters → expectancy → rules on worst cluster)
- **Event-aware review** — this skill does not call the
  news-enrichment prompt. It uses `event-watch` instead. Run
  `event-watch` first, to narrate volatility context. Then run
  `01`/`07` with that context in the conversation.

## Prompts this skill skips

- **`04_news_enrichment.md`** — requires an external news API.
  `event-watch` fills the same contextual role, with the
  `economic_calendar` MCP tool.
- **`05_regime_classification.md`** — redundant with `market-context`'s
  regime narrative. Prefer that skill's output. Populate the
  report's `market_context` block from it.

## How to run a prompt inside Claude Code

These prompts assume an external LLM call pipeline. Inside Claude Code, Claude itself IS the LLM. This needs no API plumbing:

1. Assemble the report YAML via `scripts/assemble_report.py`.
2. Load the chosen prompt file (e.g., `references/prompts/07_daily_debrief.md`)
   into context via the Read tool.
3. Append the report YAML below the prompt's "## Trade Timeline
   Report" header (each prompt ends with that sentinel).
4. Follow the prompt's constraints. The same fact-only,
   citation-required rules apply. Output in the structure the
   prompt specifies.

Do not relay this through an external API call. Claude Code is the LLM. Read the prompt and follow it.

## Length guidance

Each prompt's STRICT RULES govern the output length. For example, 07 allows a maximum of 250 words. Respect those rules.

## Schema compatibility notes

The bundled prompts carry a `compatible_report_versions: [1, 2]` tag. The assembled YAML declares `schema_version: 1`, within that range. When prompts advance to v3, validate that `assemble_report.py` still produces a schema-1-or-2 output before the upgrade.

## When a prompt fails (fact-only violation)

If the output cites a field that is `null` in the report, treat it as a prompt bug. Such a citation is common with `timeline`-dependent claims. Then do this:

1. Re-run with an explicit note: "timeline[] is null in this report —
   do not cite minute-by-minute volume or POC fields."
2. If the prompt cites a null field again, report the problem through
   GitHub Issues.

`report-schema.md` lists which fields are null today.
