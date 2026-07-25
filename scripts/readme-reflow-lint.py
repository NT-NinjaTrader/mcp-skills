#!/usr/bin/env python3
"""readme-reflow-lint.py — check that a markdown file keeps reflowed paragraphs.

The rule. A prose paragraph occupies one source line. Write the paragraph as
one line, and let the renderer wrap it for the reader.

The tool finds any hard line break inside a prose paragraph. That covers two
styles this repository does not use:

  - one sentence per line, which reads as a list,
  - a wrap at 80 characters, which breaks a sentence in the middle and hides
    an over-long sentence from `scripts/ste-lint.py`.

An earlier rule flagged only a break at a sentence boundary, so it caught the
first style and missed the second.

The tool gates every markdown file, whichever writing style the file follows.
A model-facing file also answers to `scripts/ste-lint.py`. `README.md` is
exempt from that tool, so this one is the only gate it has.

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

# A line whose break is structural, so the rule does not apply.
STRUCTURAL_RE = re.compile(
    r"""^\s*(
          \#{1,6}\s          # heading
        | [-*+]\s             # bullet item
        | \d+[.)]\s           # ordered item
        | \|                  # table row
        | >                   # blockquote or alert callout
        # An HTML block, but not an autolink. <https://example.com> is prose,
        # and a paragraph may end on one.
        | <(?![a-zA-Z][a-zA-Z0-9+.\-]*:)
        | \[[^\]]+\]:         # link-reference definition
        | ---+\s*$            # thematic break or front-matter fence
        | :{3,}               # directive fence
    )""",
    re.VERBOSE,
)


def iter_paragraphs(lines):
    """Yield a list of (line_no, text) for each prose paragraph.

    Skip a fenced code block, and treat a structural line as a paragraph
    break so a list never merges with the prose around it.
    """
    para = []
    in_fence = False
    fence_marker = ""
    in_frontmatter = False
    for line_no, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        # Front matter is YAML, so every line break in it is structural. A
        # SKILL.md opens with a `name` key and a long `description` key, and
        # YAML needs each key on its own line.
        if line_no == 1 and stripped == "---":
            in_frontmatter = True
            continue
        if in_frontmatter:
            if stripped == "---":
                in_frontmatter = False
            continue
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
        # A prose paragraph occupies one source line. Any break inside one is
        # a finding, whether it falls between two sentences or inside one.
        # Hard wrapping at 80 characters produces the second kind, and the
        # earlier sentence-boundary rule missed every one of those.
        #
        # A finding needs at least two prose lines in one paragraph, so the
        # last line of a paragraph never counts.
        for line_no, _text in para[:-1]:
            findings.append(
                (
                    str(path),
                    line_no,
                    "reflow",
                    "error",
                    "the paragraph continues on the next line. Join the "
                    "paragraph into one source line.",
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
        description=("Check that a markdown file keeps each prose paragraph on one source line."),
        epilog=(
            "Examples:\n"
            "  readme-reflow-lint.py README.md\n"
            "  readme-reflow-lint.py --max-line-words 60 README.md\n"
            "  git ls-files -z '*.md' | xargs -0 readme-reflow-lint.py\n"
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
