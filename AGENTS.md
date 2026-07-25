# AGENTS.md

This repository holds 13 trading skills for the NinjaTrader MCP server.
A skill turns a trading task into a guided workflow over the server's tools.
A skill proposes an action. It never executes a trade on its own.

This file orients two readers. Part 1 serves a user or an agent that runs the skills.
Part 2 serves a contributor who changes them.
Read [`README.md`](README.md) first for installation and the skill roster.
The full product documentation lives at <https://docs.ninjatrader.com/mcp>.

---

## Part 1 — Run the skills

### Tool names are bare. Your client adds the prefix.

A skill file names a tool bare, such as `place_order`, `my_portfolio`, or
`market_snapshot`. Each client applies its own prefix at run time:

| Client | Qualified form |
|---|---|
| Claude Code, server registered directly as `ninjatrader-demo` | `mcp__ninjatrader-demo__<tool>` |
| Claude Code, server bundled by this plugin (`ninjatrader`) | `mcp__plugin_ninjatrader_ninjatrader-demo__<tool>` |
| Codex, server registered as `ninjatrader-demo` (Codex replaces the hyphen with an underscore) | `mcp__ninjatrader_demo__<tool>` |
| Cursor, server registered from `mcp.json` as `ninjatrader-demo` | matches tools loosely by name |

Never write a prefix into a skill file. See [Part 2](#part-2--change-the-skills).

### One environment per workflow

This beta bundles the Demo (simulation) server only.
The endpoint is in [`mcp.json`](mcp.json) and in the three plugin manifests.
Demo (simulation) and live are separate servers with separate accounts.
Resolve an account once. Then stay on that same server for every later call.
A workflow that crosses servers returns an account that does not exist there.
See [Connect Your AI Agent](https://docs.ninjatrader.com/mcp/connect).

### Safety

A skill proposes an order payload. The user approves it. The server enforces the limits.

- `estimate_order` is the authoritative pre-trade gate. Call it before you present a payload.
- The server enforces the hard limits, such as daily loss and maximum contracts.
- Every mutating tool call sits after an explicit approval gate in its skill body.
  `skills/scale-manager/SKILL.md` § 5 and `skills/alerts-composer/SKILL.md` § 6 show the pattern.

See [Safety & Disclosures](https://docs.ninjatrader.com/mcp/safety) and
[Pre-Trade Risk](https://docs.ninjatrader.com/mcp/pre-trade-risk).

### Find the right skill

Each skill declares its trigger phrases in the `description` field of its `SKILL.md`.
Read [`README.md`](README.md) § Skills for the roster, with a link to each skill file.
Read [Trading Skills](https://docs.ninjatrader.com/mcp/skills) and
[Workflows](https://docs.ninjatrader.com/mcp/skills-workflows) for the phrasings that route to each job.
Call `describe(topic='index')` to enumerate the current tool set and every documented topic.

### Get help

- A defect in a skill or a tool: open a GitHub issue from a template in
  [`.github/ISSUE_TEMPLATE`](.github/ISSUE_TEMPLATE).
- An account, login, funding, platform, or order question: contact NinjaTrader
  support. A GitHub issue cannot reach your account.
- A security vulnerability: follow [`SECURITY.md`](SECURITY.md). Never open a public issue.
- Never post an account number, an order ID, or fill detail in a public issue.

---

## Part 2 — Change the skills

### Repository layout

```
skills/<name>/SKILL.md          the workflow, plus frontmatter that routes the skill
skills/<name>/scripts/*.py      deterministic math the model must not do in its head
skills/<name>/scripts/fixtures/ sample input for each script
skills/<name>/references/*.md   detail the model loads on demand, not up front
scripts/                        the repository gates
.claude/agents/ste-writer.md    an agent that rewrites prose to pass the style gate
```

### Every SKILL.md keeps the same spine

All 13 files carry these six sections, in this order. Keep the order when you edit a skill:

1. `## Purpose` — what the skill does, and what it does not do.
2. `## Environment routing` — how the skill picks demo (simulation) or live.
3. `## MCP tools used` — the bare tool names, each with a `fields=[...]` projection
   that keeps the payload small.
4. `## Workflow` — the numbered steps.
5. `## Disambiguation` — when to use a sibling skill instead.
6. `## Resource layout` — one line per bundled script and reference file, and when to load it.

A skill may add a section, such as `## Known gotchas` or `## Explicit non-goals`.
Keep the six above, and keep them in this order.

Put a correction, such as a fix to a wrong assumption, under a Gotchas heading.
Do not scatter a correction through the prose.

### The bundled-script contract

A script under `skills/<name>/scripts/` must meet every rule below:

- Support `--help`, and show at least one runnable example in the help output.
- Write its result as JSON to stdout.
- Write a diagnostic or a progress message to stderr, never to stdout.
- Give every flag `help=` text that states the meaning, the unit, and the default.
- Enumerate the valid choices in the error message for a bad argument value.
- Set `allow_abbrev=False`, so a mistyped flag fails instead of binding to another flag.
- Use only the Python standard library, unless a PEP 723 `# /// script` block declares
  the dependencies. The three chart scripts declare `matplotlib` this way.
- Ship a fixture under `scripts/fixtures/`, so a gate can exercise the script.

### Two publish rules that a gate enforces

- A skill must never name a server hostname or a bare URL. A skill runs against any
  environment, so the endpoint belongs in `mcp.json` and the manifests, never in a skill.
- A tool name in skill prose stays bare. Never add a client prefix. See
  [Part 1](#tool-names-are-bare-your-client-adds-the-prefix).

### Two writing styles, and which files take which

This repository runs two registers. Match the register to the reader.

| Files | Register | Gate |
|---|---|---|
| `skills/**/SKILL.md`, `skills/**/references/*.md`, `AGENTS.md`, `SECURITY.md`, `.github/**/*.md` | ASD-STE100 | `scripts/ste-lint.py` |
| `README.md` | Ordinary technical prose | `scripts/readme-reflow-lint.py` |
| `skills/trade-debrief/references/prompts/*.md` | Verbatim. Do not edit the prose. | none |

A model-facing file earns the tighter register. A skill body re-enters the model's context
on every turn it stays active, so each line costs tokens again. Terse, one-instruction
sentences also route better. A README pays no token cost and a person reads it once.

### Writing style: ASD-STE100 (model-facing files)

- Use one instruction per sentence.
- Keep an instruction sentence to 20 words or fewer.
- Keep a descriptive sentence to 25 words or fewer.
- Use the active voice, and the imperative mood for an instruction.
- Use simple present, past, or future tense. Do not use an `-ing` verb form.
- Keep the articles (`the`, `a`, `an`). Do not drop a word to save space.
- State a condition before the instruction it governs.
- Use one word for one meaning.

Never reword a code identifier, a tool name, a command, quoted tool output, or a
verbatim user phrase inside quotes. A `description` field cites the exact words a user
says, so a reworded trigger phrase breaks routing. Write a `description` in the third
person, because the client injects it into a system prompt.

The [`ste-writer`](.claude/agents/ste-writer.md) agent rewrites prose to these rules.
Never run it on `README.md`.

### Writing style: README.md (human-facing)

`README.md` is the landing page, so write it the way a reader expects a landing page to
read. These rules replace the STE rules above for that one file.

- Write each paragraph as one source line. Reflow it. Do not wrap at a column, and do not
  break the line at a sentence boundary.
- Open a section with a declarative sentence, not an instruction.
- Use the second person for anything the reader does. Keep "we" for a statement of project
  policy, of support scope, or of declined responsibility.
- Contractions are welcome.
- There is no sentence-length cap. Aim under about 30 words, and vary the length.
- An `-ing` form is fine. So is a subordinating conjunction, such as "so", "but", or
  "which". Use one to subordinate a detail instead of writing a flat run of short sentences.
- Keep the bare imperative inside a numbered procedure, an install step, and a safety
  callout. A procedure still reads as a procedure.
- Put a risk or a limitation in a GitHub alert callout, such as `> [!WARNING]`. Give a
  load-bearing safety sentence its own weight.
- Use no emoji.
- "One word for one meaning" still holds for a tool name, a product name, and a domain
  term. Ordinary prose may use a pronoun or a synonym.

### Run the gates before you open a pull request

```bash
./scripts/validate-all.sh                          # skill structure, script behavior, markdown links
python3 scripts/ste-lint.py <changed markdown>     # the ASD-STE100 rules
python3 scripts/readme-reflow-lint.py README.md    # the README paragraph style
./scripts/manifest-lint.sh                         # the four client manifests agree
shellcheck scripts/*.sh                            # the shell gates
```

| Gate | What it proves |
|---|---|
| `scripts/validate-all.sh` | Each skill's structure is valid. Each script runs against its fixture and prints valid JSON. Every markdown link and image target exists. |
| `scripts/ste-lint.py` | A model-facing file follows the ASD-STE100 rules. It skips `README.md` and the verbatim prompt library. |
| `scripts/readme-reflow-lint.py` | `README.md` keeps reflowed paragraphs. It ignores a list, a table, a callout, and a code block. |
| `scripts/check-references.py` | Every path a markdown file names exists on disk. `validate-all.sh` calls it. |
| `scripts/manifest-lint.sh` | The manifests agree on the endpoint, the version, the description, and the skills list. A mismatch makes a client refuse the plugin. |

CI runs these gates on every pull request. See
[`.github/workflows/validate.yml`](.github/workflows/validate.yml).
Then work through [`.github/pull_request_template.md`](.github/pull_request_template.md).

### The safety posture is not negotiable

A skill proposes an action. It never executes a trade or another account-changing action
on its own. Do not submit a change that adds autonomous execution. We decline such a
change, whatever its other merits.
