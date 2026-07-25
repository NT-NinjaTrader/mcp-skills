#!/usr/bin/env python3
"""readme-reflow-lint.py — check that a README keeps reflowed paragraphs.

`README.md` is exempt from `scripts/ste-lint.py`, because it is human-facing
prose rather than model-facing instructions. See AGENTS.md § Writing style
for README.md. This tool takes over the gate, so the file is never ungated.

It finds one thing: a prose paragraph written one sentence per line. That
style reads as a list, and every comparable public project reflows instead.

The rule. Inside a prose paragraph, a line must not end at a sentence
boundary while another prose line follows in the same paragraph. Write the
paragraph as one source line, and let the renderer wrap it.

The tool ignores a construct where a line break carries meaning:

  - a fenced code block,
  - a heading,
  - a table row,
  - a list item, including a continuation line indented under one,
  - a blockquote, which covers a GitHub alert callout and a quoted example,
  - a link-reference definition,
  - an HTML block.

Usage:
    readme-reflow-lint.py README.md
    readme-reflow-lint.py --max-line-words 60 README.md

Exit codes:
    0 — no finding.
    1 — at least one finding, or an input path that does not exist.
    2 — a usage error, such as an unknown flag.
"""

import argparse
import re
import sys
from pathlib import Path

PROG = "readme-reflow-lint.py"

# A sentence-final line: ends in . ! or ? and is not an abbreviation or a
# version number. A colon does not count, because a colon legitimately
# introduces a following block.
SENTENCE_END_RE = re.compile(r"[.!?][)\"'”]?$")

# A line whose break is structural, so the rule does not apply.
STRUCTURAL_RE = re.compile(
    r"""^\s*(
          \#{1,6}\s          # heading
        | [-*+]\s             # bullet item
        | \d+[.)]\s           # ordered item
        | \|                  # table row
        | >                   # blockquote or alert callout
        | <                   # HTML block
        | \[[^\]]+\]:         # link-reference definition
        | ---+\s*$            # thematic break or front-matter fence
        | :{3,}               # directive fence
    )""",
    re.VERBOSE,
)

# An abbreviation that ends in a period but not a sentence.
ABBREV_RE = re.compile(r"\b(?:e\.g|i\.e|etc|vs|cf|Inc|Ltd|Dr|Mr|Ms|No)\.$", re.IGNORECASE)


def iter_paragraphs(lines):
    """Yield a list of (line_no, text) for each prose paragraph.

    Skip a fenced code block, and treat a structural line as a paragraph
    break so a list never merges with the prose around it.
    """
    para = []
    in_fence = False
    fence_marker = ""
    for line_no, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        fence = re.match(r"^\s*(`{3,}|~{3,})", raw)
        if fence:
            marker = fence.group(1)[0]
            if not in_fence:
                in_fence, fence_marker = True, marker
            elif marker == fence_marker:
                in_fence, fence_marker = False, ""
            if para:
                yield para
                para = []
            continue
        if in_fence:
            continue
        if not stripped or STRUCTURAL_RE.match(raw):
            if para:
                yield para
                para = []
            continue
        # A continuation line indented under a list item keeps the item's
        # line breaks, so treat any indented line as structural.
        if raw[:1].isspace():
            if para:
                yield para
                para = []
            continue
        para.append((line_no, stripped))
    if para:
        yield para


def check_file(path: Path, max_line_words: int, findings: list) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    for para in iter_paragraphs(lines):
        # A finding needs at least two prose lines in one paragraph, so the
        # last line of a paragraph never counts.
        for line_no, text in para[:-1]:
            if ABBREV_RE.search(text):
                continue
            if SENTENCE_END_RE.search(text):
                findings.append(
                    (
                        str(path),
                        line_no,
                        "reflow",
                        "error",
                        "line ends a sentence while the paragraph continues — "
                        "join the paragraph into one source line",
                    )
                )
        for line_no, text in para:
            words = len(text.split())
            if words > max_line_words:
                findings.append(
                    (
                        str(path),
                        line_no,
                        "line-length",
                        "warning",
                        f"paragraph line holds {words} words (soft max {max_line_words}) — "
                        "consider splitting the paragraph",
                    )
                )


def main() -> int:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=(
            "Check that a README keeps reflowed paragraphs instead of one sentence per line."
        ),
        epilog=(
            "Examples:\n"
            "  readme-reflow-lint.py README.md\n"
            "  readme-reflow-lint.py --max-line-words 60 README.md\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "paths",
        nargs="+",
        metavar="PATH",
        help="One or more markdown files to check. Default: none, so pass at least one.",
    )
    parser.add_argument(
        "--max-line-words",
        type=int,
        default=80,
        metavar="N",
        help=(
            "Warn when one paragraph line holds more than N words. "
            "A very long line is hard to review in a diff. Default: 80."
        ),
    )
    parser.add_argument(
        "--warnings-as-errors",
        action="store_true",
        help="Exit 1 on a warning as well as on an error. Default: off.",
    )
    args = parser.parse_args()

    findings: list = []
    bad_path = False
    for raw_path in args.paths:
        path = Path(raw_path)
        if not path.is_file():
            print(f"{PROG}: error: path not found: {raw_path}", file=sys.stderr)
            bad_path = True
            continue
        try:
            check_file(path, args.max_line_words, findings)
        except UnicodeDecodeError:
            print(f"{PROG}: skipping unreadable file: {path}", file=sys.stderr)

    for file_label, line_no, rule, severity, message in findings:
        print(f"{file_label}:{line_no}: [{rule}] {severity}: {message}")

    errors = [f for f in findings if f[3] == "error"]
    warnings = [f for f in findings if f[3] == "warning"]
    if findings:
        print(
            f"{PROG}: {len(errors)} error(s), {len(warnings)} warning(s)",
            file=sys.stderr,
        )
    if bad_path or errors or (args.warnings_as_errors and warnings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
