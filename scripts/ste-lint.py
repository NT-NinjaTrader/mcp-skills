#!/usr/bin/env python3
"""ste-lint.py — check markdown prose for ASD-STE100 style hits.

This tool checks a mechanical subset of ASD-STE100 Simplified
Technical English. It finds four patterns: long sentences,
continuous tense, perfect tense, and passive voice. It does not
check the full rule set. A human reviewer must still check article
use, one-instruction-per-sentence structure, and word choice.

The tool skips code identifiers and other non-prose spans before it
checks a line. It skips a fenced code block, an inline code span, a
table row, a blockquote line, a URL, and any text inside double
quotes. Inside YAML frontmatter, it skips every key except
`description`, and it still skips double-quoted text inside that
value.

The sentence-length check never splits a sentence at "e.g.",
"i.e.", "etc.", "vs.", or "cf." mid-line. A real sentence boundary
right after one of these still merges into the next sentence. This
is a known gap in the mechanical subset, not a new rule.

The tool skips two kinds of path, and prints one stderr note per
skipped file. See `EXEMPT_PATHS` below.

First, every file under `skills/trade-debrief/references/prompts/`.
Each file there is a verbatim prompt for another model, because a
reworded prompt changes the output of that model.

Second, any `README.md`. A README is human-facing prose, so it
follows the ordinary technical-writing rules in `AGENTS.md`
§ Writing style for README.md. `scripts/readme-reflow-lint.py`
gates a README instead, so the file is never ungated.

A directory argument makes the tool recurse into every `*.md` file
under it. A file argument only runs when the file has an `.md`
suffix; the tool skips any other file and prints a note to stderr.

Findings print to stdout, one per line, in this form:

    file:line: [rule] severity: message

Exit code 0 means no error-level finding, and no warning-level
finding when `--warnings-as-errors` is set. Exit code 1 means at
least one such finding, or an input path that does not exist. Exit
code 2 means a usage error, such as an unknown flag.

Examples:
    ste-lint.py AGENTS.md
    ste-lint.py AGENTS.md SECURITY.md skills/
    ste-lint.py --warnings-as-errors skills/market-context/SKILL.md
"""

import argparse
import re
import sys
from pathlib import Path

PROG = "ste-lint.py"

VALID_FLAGS = ("--help", "--warnings-as-errors")

# Lines that open or close a construct we skip entirely.
FENCE_RE = re.compile(r"^\s*(```+|~~~+)")
TABLE_ROW_RE = re.compile(r"^\s*\|")
BLOCKQUOTE_RE = re.compile(r"^\s*>")

# Spans we strip from a prose line before we check it. Order matters:
# a markdown link keeps its link text and drops the URL target first,
# so a later bare-URL pass does not need to handle that case too.
MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
BARE_URL_RE = re.compile(r"<?https?://\S+>?")
INLINE_CODE_RE = re.compile(r"`[^`]*`")
DOUBLE_QUOTED_RE = re.compile(r'"[^"]*"')

# The four mechanical checks.
CONTINUOUS_RE = re.compile(r"\b(?:is|are|was|were|be|been|being)\s+\w+ing\b", re.IGNORECASE)
PERFECT_RE = re.compile(r"\b(?:has|have|had)\s+(?:been\s+)?\w+(?:ed|en)\b", re.IGNORECASE)
PASSIVE_RE = re.compile(r"\b(?:is|are|was|were|been)\s+\w+ed\b(\s+by\b)?", re.IGNORECASE)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

# SENTENCE_SPLIT_RE treats an abbreviation period plus whitespace as
# a sentence boundary. Swap the period for a placeholder first. A
# mid-sentence "e.g." must not split one long sentence into two
# short sentences. A split like that hides a real sentence-length
# finding.
ABBREVIATION_RE = re.compile(r"\b(?:e\.g|i\.e|etc|vs|cf)\.(?=\s)", re.IGNORECASE)
ABBREVIATION_PLACEHOLDER = "\x00"

SENTENCE_MAX_WORDS = 25
SENTENCE_WARN_WORDS = 21

# Paths that this tool never checks. AGENTS.md § Writing style states the
# scope of the ASD-STE100 rules, and these paths sit outside it.
#
#   trade-debrief/references/prompts/ — a verbatim prompt library. Each file
#     there is a prompt for another model, so the contract says to send the
#     text as-is.
#   README.md — the landing page. It is human-facing prose, so it follows
#     the ordinary technical-writing rules in AGENTS.md § Writing style for
#     README.md, not the STE rules. `scripts/readme-reflow-lint.py` gates
#     it instead.
EXEMPT_PATHS = (
    "trade-debrief/references/prompts/",
    "README.md",
)


class STEArgumentParser(argparse.ArgumentParser):
    """An ArgumentParser whose error message names the valid flags."""

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"{PROG}: error: {message}", file=sys.stderr)
        print(f"valid flags: {', '.join(VALID_FLAGS)}", file=sys.stderr)
        sys.exit(2)


def build_parser() -> STEArgumentParser:
    parser = STEArgumentParser(
        prog=PROG,
        description=(
            "Check a mechanical subset of ASD-STE100 rules on markdown "
            "prose: sentence length, continuous tense, perfect tense, "
            "and passive voice."
        ),
        epilog=(
            "Examples:\n"
            "  ste-lint.py AGENTS.md\n"
            "  ste-lint.py AGENTS.md SECURITY.md skills/\n"
            "  ste-lint.py --warnings-as-errors skills/market-context/SKILL.md\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        # A typo such as --warnings must not bind to --warnings-as-errors.
        allow_abbrev=False,
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="markdown file(s) or directory(ies) to check",
    )
    parser.add_argument(
        "--warnings-as-errors",
        action="store_true",
        help="exit 1 when a warning-level finding exists, not only an error-level one",
    )
    return parser


def clean_prose(text: str) -> str:
    """Strip non-prose spans from one line, in the exemption order."""
    text = MD_LINK_RE.sub(r"\1", text)
    text = BARE_URL_RE.sub("", text)
    text = INLINE_CODE_RE.sub("", text)
    text = DOUBLE_QUOTED_RE.sub("", text)
    return text


def iter_prose_lines(path: Path):
    """Yield (line_no, cleaned_text) for each line eligible for a check."""
    lines = path.read_text(encoding="utf-8").splitlines()
    in_frontmatter = False
    in_fence = False

    for i, raw in enumerate(lines, start=1):
        stripped = raw.strip()

        if i == 1 and stripped == "---":
            in_frontmatter = True
            continue

        if in_frontmatter:
            if stripped == "---":
                in_frontmatter = False
                continue
            if stripped.startswith("description:"):
                value = raw.split(":", 1)[1].strip()
                yield i, clean_prose(value)
            continue

        if FENCE_RE.match(raw):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if TABLE_ROW_RE.match(raw) or BLOCKQUOTE_RE.match(raw):
            continue
        if not stripped:
            continue

        yield i, clean_prose(raw)


def protect_abbreviations(text: str) -> str:
    """Swap an abbreviation's period for a placeholder before a split."""
    return ABBREVIATION_RE.sub(lambda m: m.group(0)[:-1] + ABBREVIATION_PLACEHOLDER, text)


def check_line(file_label: str, line_no: int, text: str, findings: list) -> None:
    text = text.strip()
    if not text:
        return

    if CONTINUOUS_RE.search(text):
        findings.append(
            (
                file_label,
                line_no,
                "continuous-tense",
                "error",
                "line uses a continuous tense (an -ing form)",
            )
        )

    passive_match = PASSIVE_RE.search(text)
    if passive_match:
        if passive_match.group(1):
            findings.append(
                (
                    file_label,
                    line_no,
                    "passive-voice",
                    "error",
                    'passive voice with an explicit "by" agent',
                )
            )
        else:
            findings.append(
                (file_label, line_no, "passive-voice", "warning", "passive voice construction")
            )

    if PERFECT_RE.search(text):
        findings.append(
            (file_label, line_no, "perfect-tense", "warning", "line uses a perfect tense")
        )

    for sentence in SENTENCE_SPLIT_RE.split(protect_abbreviations(text)):
        sentence = sentence.strip()
        if not sentence:
            continue
        word_count = len(sentence.split())
        if word_count > SENTENCE_MAX_WORDS:
            findings.append(
                (
                    file_label,
                    line_no,
                    "sentence-length",
                    "error",
                    f"sentence has {word_count} words (max {SENTENCE_MAX_WORDS})",
                )
            )
        elif word_count >= SENTENCE_WARN_WORDS:
            findings.append(
                (
                    file_label,
                    line_no,
                    "sentence-length",
                    "warning",
                    f"sentence has {word_count} words (recommended max {SENTENCE_WARN_WORDS - 1})",
                )
            )


def is_exempt_prompt_file(path: Path) -> bool:
    """Return True for a path that the STE rules do not cover.

    `README.md` matches on the final path segment only. A file named
    `README.md` inside a skill still counts as the landing-page style, and
    a path such as `docs/READMEs/notes.md` must not match by accident.
    """
    posix = path.as_posix()
    for marker in EXEMPT_PATHS:
        if marker.endswith("/"):
            if marker in posix:
                return True
        elif path.name == marker:
            return True
    return False


def collect_md_files(path: Path) -> list:
    if path.is_dir():
        return sorted(path.rglob("*.md"))
    if path.suffix == ".md":
        return [path]
    print(f"{PROG}: skipping non-markdown file: {path}", file=sys.stderr)
    return []


def main(argv: list) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    all_findings: list = []
    had_bad_path = False

    for raw_path in args.paths:
        candidate = Path(raw_path)
        if not candidate.exists():
            print(f"{PROG}: error: path not found: {raw_path}", file=sys.stderr)
            had_bad_path = True
            continue

        for md_file in collect_md_files(candidate):
            if is_exempt_prompt_file(md_file):
                print(f"{PROG}: skipping exempt file: {md_file}", file=sys.stderr)
                continue
            try:
                for line_no, cleaned in iter_prose_lines(md_file):
                    check_line(str(md_file), line_no, cleaned, all_findings)
            except UnicodeDecodeError:
                print(f"{PROG}: skipping unreadable file: {md_file}", file=sys.stderr)

    for file_label, line_no, rule, severity, message in all_findings:
        print(f"{file_label}:{line_no}: [{rule}] {severity}: {message}")

    has_error = any(f[3] == "error" for f in all_findings)
    has_warning = any(f[3] == "warning" for f in all_findings)

    if had_bad_path or has_error:
        return 1
    if args.warnings_as_errors and has_warning:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
