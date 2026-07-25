# Contributing

Thank you for your interest in these skills.

This file is the public contributor guide. `scripts/internal/publish.sh` renames it to `CONTRIBUTING.md` in the public copy. Keep it free of an internal reference, because every reader sees it.

## Read the contract first

[`AGENTS.md`](AGENTS.md) holds the contributor contract. Read Part 2 before you change a file. It states the repository layout, the `SKILL.md` section spine, the bundled-script contract, the writing rules, and the safety posture.

## Report a problem

Open an issue from a [template](https://github.com/NT-NinjaTrader/mcp-skills/issues/new/choose). Two templates exist: a bug report, and a skill request.

A trigger phrase that reached the wrong skill is the most useful report. Give the exact wording that you used.

Do not open a GitHub issue for a question about an account. We cannot look up an account from a GitHub issue. For help with an account, a login, funding, the platform, or an order, go to <https://ninjatrader.com/support/>.

**Never post an account number, an order ID, or fill detail in a public issue.**

For a security problem, follow [`SECURITY.md`](SECURITY.md). Do not open a public issue for a security report.

## Propose a change

1. Open an issue first for anything larger than a typo. It saves you work if we
   disagree about the approach.
2. Fork the repository, and make a branch.
3. Run the gates in the next section. A red gate blocks the review.
4. Open a pull request. Explain what changes, and explain why.

Write the commit subject to the Conventional Commits convention:

```text
<type>(<scope>): <description>
```

The type is one of `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, or `chore`. Keep the subject to 72 characters.

## Run the gates

Four gates run in CI. Run them before you open a pull request:

```bash
./scripts/validate-all.sh                                  # skills, scripts, and links
git ls-files -z '*.md' | xargs -0 -r python3 scripts/ste-lint.py   # the writing rules
python3 scripts/readme-reflow-lint.py README.md            # the README paragraph style
./scripts/manifest-lint.sh                                 # the four client manifests agree
```

Run all Python tooling through `uv`. Use `uvx`, `uv run`, or `uv pip`. Do not call `pip` directly.

## How your change reaches a release

We review every pull request here. When we accept a change, it reaches the next published release, and you keep the credit as the author. The maintainers apply an accepted change through their own release process. A release may not carry your commit as you wrote it. We say so in the pull request when that happens.

## What we do not accept

- A change that lets a skill place, modify, or cancel an order without your
  approval. The safety posture is not negotiable. `AGENTS.md` states it.
- A skill that names a server hostname or a bare URL. A skill must run against
  any environment.
- A new dependency in a bundled script, unless the script declares it inline.

## Keep the writing style

The repository uses ASD-STE100 Simplified Technical English for a model-facing file. Keep one instruction per sentence. Keep a sentence short. Use the active voice. Use the imperative for an instruction.

`README.md` follows a different register, so `ste-lint.py` skips it.
