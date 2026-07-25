#!/usr/bin/env python3
"""
check-references.py — verify the paths the markdown in a checkout names.

The tool runs three checks and reports every failure before it exits.

Check 1 covers each skill's `SKILL.md` body. A skill body names a
bundled script or a reference file in one of these forms:

  - `../trade-journal/scripts/streaks.py` (relative-up form)
  - `trade-journal/scripts/streaks.py`    (bare form, same meaning)
  - `scripts/streaks.py`                  (this skill only)
  - `references/risk-rules.md`            (this skill only)

The first two forms are legitimate: the named script lives in a sibling
skill. The tool resolves those against the sibling directory.

Check 2 covers every markdown file in the checkout, not only a
`SKILL.md`. It resolves each relative markdown link target and each
image target against the file that names it. It skips an absolute URL,
a `mailto:` target, and a bare intra-document anchor.

Check 3 covers every markdown file in the checkout. It fails on a
stray `</content>` line, which is an artifact of file generation.

Checks 2 and 3 ask git for the markdown file list, so a newly staged
file enters the scan without an edit here. Outside a git work tree the
tool walks the directory tree instead.

Exit code: 0 when every check passes. 1 when any reference, link
target, or stray tag fails a check. 2 on a usage error, such as a path
that is not a directory.

Examples:
    check-references.py skills
    check-references.py --repo-root . skills
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

PROG = "check-references.py"

VALID_FLAGS = ("--help", "--repo-root")

GREEN = "\033[32m"
RED = "\033[31m"
RESET = "\033[0m"

# Check 1: a bundled-script or reference path inside a SKILL.md body.
REF_RE = re.compile(
    r"((?:\.\./)?[a-z][a-z0-9-]*/)?(scripts|references)/[a-zA-Z0-9_/-]+\.(?:py|md|json|yml|yaml)"
)

# Check 2: one markdown inline link or image. Group 1 holds the target.
# The pattern accepts an angle-bracket wrapper and drops a link title.
MD_TARGET_RE = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)>\s]*)>?[^)]*\)")

# A target that carries a URI scheme, a protocol-relative host, or a
# bare anchor never resolves to a file in this checkout.
EXTERNAL_TARGET_RE = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//|#)", re.IGNORECASE)

# Check 3: the generation artifact a markdown file must never hold.
STRAY_TAG = "</content>"

# Directories the walk fallback never descends into. Git already omits
# each one, so this list only matters outside a git work tree.
WALK_SKIP_DIRS = frozenset({".git", "node_modules", ".venv", "__pycache__"})


class RefArgumentParser(argparse.ArgumentParser):
    """An ArgumentParser whose error message names the valid flags."""

    def error(self, message):
        self.print_usage(sys.stderr)
        print(f"{PROG}: error: {message}", file=sys.stderr)
        print(f"valid flags: {', '.join(VALID_FLAGS)}", file=sys.stderr)
        sys.exit(2)


def build_parser() -> RefArgumentParser:
    parser = RefArgumentParser(
        prog=PROG,
        description=(
            "Verify the paths the markdown in a checkout names: the script "
            "and reference paths in each SKILL.md body, every relative "
            "markdown link and image target, and the absence of a stray "
            "</content> generation tag."
        ),
        epilog=(
            "Examples:\n"
            "  check-references.py skills\n"
            "  check-references.py --repo-root . skills\n"
            "  check-references.py --repo-root . /path/to/checkout/skills\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
    )
    parser.add_argument(
        "skills_dir",
        metavar="SKILLS_DIR",
        help="Directory that holds one subdirectory per skill.",
    )
    parser.add_argument(
        "--repo-root",
        metavar="PATH",
        default=None,
        help=(
            "Checkout root for the markdown link and stray-tag checks. "
            "Default: the parent of SKILLS_DIR."
        ),
    )
    return parser


# -----------------------------------------------------------------------------
# Markdown file enumeration
# -----------------------------------------------------------------------------


def _git_output(root: Path, args: list[str]) -> str | None:
    """Run one git command in `root`. Return stdout, or None on failure."""
    try:
        result = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def git_tracked_markdown(root: Path) -> list[Path] | None:
    """Return the markdown files git tracks under `root`.

    Return None when `root` is not the top of a git work tree, because
    git then reports paths relative to another directory.
    """
    top = _git_output(root, ["rev-parse", "--show-toplevel"])
    if top is None or not top.strip():
        return None
    if Path(top.strip()).resolve() != root.resolve():
        return None
    listing = _git_output(root, ["ls-files", "-z", "--", "*.md"])
    if listing is None:
        return None
    names = [name for name in listing.split("\0") if name]
    return sorted(root / name for name in names)


def walk_markdown(root: Path) -> list[Path]:
    """Return every markdown file under `root`, minus a vendored tree."""
    found = [path for path in root.rglob("*.md") if not WALK_SKIP_DIRS.intersection(path.parts)]
    return sorted(found)


def list_markdown_files(root: Path) -> list[Path]:
    """Return the markdown files to scan, from git or from a tree walk."""
    tracked = git_tracked_markdown(root)
    if tracked is not None:
        return tracked
    return walk_markdown(root)


def relative_label(path: Path, root: Path) -> str:
    """Return the path of `path` relative to `root`, for a report line."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def read_markdown(path: Path) -> str | None:
    """Return the text of one markdown file, or None when it is unreadable."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        print(f"{PROG}: skipping unreadable file: {path}", file=sys.stderr)
        return None


# -----------------------------------------------------------------------------
# Check 1: script and reference paths inside a SKILL.md body
# -----------------------------------------------------------------------------


def check_skill_references(skills_dir: Path) -> int:
    """Report each SKILL.md reference that no file satisfies.

    Return the number of skills that hold at least one bad reference.
    """
    all_skills = {p.name: p for p in skills_dir.iterdir() if p.is_dir()}
    fail_count = 0

    for skill_name in sorted(all_skills):
        skill_dir = all_skills[skill_name]
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue

        body = skill_md.read_text(encoding="utf-8")
        missing: list[str] = []

        for match in REF_RE.finditer(body):
            ref = match.group(0).strip()

            # Normalize: strip a leading ../ and check whether the first
            # segment names a known skill. If it does, resolve against
            # that skill.
            target: Path
            normalized = ref.removeprefix("../")
            first_segment = normalized.split("/", 1)[0]
            if first_segment in all_skills and first_segment != skill_name:
                # Cross-skill reference
                tail = "/".join(normalized.split("/")[1:])
                target = all_skills[first_segment] / tail
            elif normalized.startswith(("scripts/", "references/")):
                target = skill_dir / normalized
            else:
                # Unknown prefix — skip it. The regex matches some prose
                # by accident, and that prose names no real path.
                continue

            if not target.is_file():
                missing.append(ref)

        if missing:
            fail_count += 1
            missing_joined = " ".join(sorted(set(missing)))
            print(f"   {RED}✗{RESET} {skill_name} — missing: {missing_joined}")
        else:
            print(f"   {GREEN}✓{RESET} {skill_name}")

    return fail_count


# -----------------------------------------------------------------------------
# Check 2: markdown link and image targets
# -----------------------------------------------------------------------------


def iter_link_targets(text: str):
    """Yield (line_no, target) for each markdown link or image target."""
    for line_no, line in enumerate(text.splitlines(), start=1):
        for match in MD_TARGET_RE.finditer(line):
            yield line_no, match.group(1)


def is_external_target(target: str) -> bool:
    """Return True for a target this tool never resolves on disk."""
    return not target or bool(EXTERNAL_TARGET_RE.match(target))


def resolve_target(md_file: Path, target: str) -> Path:
    """Return the on-disk path a relative markdown target names."""
    path_part = target.split("#", 1)[0].split("?", 1)[0]
    return md_file.parent / unquote(path_part)


def find_broken_links(md_files: list[Path], root: Path) -> list[tuple[str, int, str]]:
    """Return one (file_label, line_no, target) entry per absent target."""
    misses: list[tuple[str, int, str]] = []
    for md_file in md_files:
        text = read_markdown(md_file)
        if text is None:
            continue
        for line_no, target in iter_link_targets(text):
            if is_external_target(target):
                continue
            if resolve_target(md_file, target).exists():
                continue
            misses.append((relative_label(md_file, root), line_no, target))
    return misses


# -----------------------------------------------------------------------------
# Check 3: stray generation tag
# -----------------------------------------------------------------------------


def find_stray_tags(md_files: list[Path], root: Path) -> list[str]:
    """Return the label of each markdown file that holds the stray tag."""
    hits: list[str] = []
    for md_file in md_files:
        text = read_markdown(md_file)
        if text is None:
            continue
        if STRAY_TAG in text:
            hits.append(relative_label(md_file, root))
    return hits


# -----------------------------------------------------------------------------
# Entry point
# -----------------------------------------------------------------------------


def report_link_check(misses: list[tuple[str, int, str]], file_count: int) -> None:
    if not misses:
        print(f"   {GREEN}✓{RESET} markdown links resolve in {file_count} files")
        return
    for file_label, line_no, target in misses:
        print(f"   {RED}✗{RESET} markdown link target absent: {file_label}:{line_no} -> {target}")


def report_stray_tag_check(hits: list[str], file_count: int) -> None:
    if not hits:
        print(f"   {GREEN}✓{RESET} no stray {STRAY_TAG} tag in {file_count} markdown files")
        return
    print(f"   {RED}✗{RESET} stray {STRAY_TAG} tag in {len(hits)} markdown files:")
    for file_label in hits:
        print(f"       {file_label}")


def main(argv: list[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    skills_dir = Path(args.skills_dir)
    if not skills_dir.is_dir():
        print(f"{PROG}: error: not a directory: {skills_dir}", file=sys.stderr)
        return 2

    repo_root = Path(args.repo_root) if args.repo_root else skills_dir.parent
    if not repo_root.is_dir():
        print(f"{PROG}: error: not a directory: {repo_root}", file=sys.stderr)
        return 2

    fail_count = check_skill_references(skills_dir)

    md_files = list_markdown_files(repo_root)
    misses = find_broken_links(md_files, repo_root)
    report_link_check(misses, len(md_files))
    fail_count += len(misses)

    hits = find_stray_tags(md_files, repo_root)
    report_stray_tag_check(hits, len(md_files))
    fail_count += len(hits)

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
