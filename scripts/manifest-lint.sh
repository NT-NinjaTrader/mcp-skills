#!/usr/bin/env bash
# manifest-lint.sh — check every client manifest for canonical jq
# formatting and an alphabetically sorted skills array.
# Usage: scripts/manifest-lint.sh [file ...]   (default: the 5 manifests)
#
# A separate pass guards the brand display name. Claude Code, Cursor,
# and Codex show the plugin `name` field when a manifest declares no
# display name. Claude Code then shows the lowercase `ninjatrader` in
# the `/plugin` picker. Cursor title-cases the kebab-case value, so
# `ninjatrader` renders as "Ninjatrader". The brand is "NinjaTrader"
# with a capital T, so each client manifest must declare the display
# name itself. The pass keys on the file path, so it also runs against
# a fixture copy.
#
# "Canonical" means `jq --indent 2 .` round-trips the file byte for
# byte: one key/value per line, 2-space indent. The sorted-skills
# check adapts per file shape — it reads `.plugins[0].skills` first
# (the marketplace.json shape), falls back to top-level `.skills`
# (the plugin.json shape), and skips the check entirely when that
# value is a string (codex/cursor point at a bare "./skills/" path)
# or absent (mcp.json has no skills field at all).
#
# A third check guards the Claude marketplace shape. `strict: true` is
# the default. It makes plugin.json authoritative and lets the
# marketplace entry supplement it. `strict: false` makes the marketplace
# entry the whole plugin definition. A plugin.json that also declares
# components is then a conflict, and Claude Code refuses to load the
# plugin. The check runs on a marketplace.json file only. It reads the
# sibling plugin.json next to that file.
#
# A final section checks for drift between the five manifests. The five
# files repeat the same metadata, and no build step generates them from
# one source. A disagreement between two of them breaks an install, so
# the section fails on any disagreement. It compares the whole set, so
# it runs only when the script gets no file argument. See DRIFT_PY for
# the field list and for the Cursor exemption.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1
ARGC=$#
FILES=("$@")
[ ${#FILES[@]} -eq 0 ] && FILES=(
  .claude-plugin/marketplace.json
  .claude-plugin/plugin.json
  .codex-plugin/plugin.json
  .cursor-plugin/plugin.json
  mcp.json
)

# The component keys that a plugin definition can declare. A conflict
# needs at least one of these keys on both sides.
COMPONENT_KEYS='["mcpServers","skills","commands","agents","hooks","outputStyles"]'

fail=0
for f in "${FILES[@]}"; do
  if [ ! -f "$f" ]; then
    echo "MISSING manifest: $f"
    fail=1
    continue
  fi

  if ! jq -e . "$f" >/dev/null 2>&1; then
    echo "INVALID JSON: $f"
    fail=1
    continue
  fi

  if ! diff -q <(jq --indent 2 . "$f") "$f" >/dev/null 2>&1; then
    echo "NOT CANONICALLY FORMATTED: $f (run: jq --indent 2 . $f > tmp && mv tmp $f)"
    fail=1
  fi

  skills_type=$(jq -r '(.plugins[0].skills // .skills) | type' "$f" 2>/dev/null)
  if [ "$skills_type" = "array" ]; then
    if ! jq -e '(.plugins[0].skills // .skills) as $s | $s == ($s | sort)' "$f" >/dev/null 2>&1; then
      echo "SKILLS NOT SORTED: $f"
      fail=1
    fi
  fi

  [ "$(basename "$f")" = "marketplace.json" ] || continue
  sibling="$(dirname "$f")/plugin.json"
  [ -f "$sibling" ] || continue
  jq -e . "$sibling" >/dev/null 2>&1 || continue

  # List the component keys that the sibling plugin.json declares.
  # An empty list means the plugin.json holds metadata only, so a
  # `strict: false` marketplace entry stays legal.
  plugin_components=$(jq -r --argjson keys "$COMPONENT_KEYS" \
    '[keys_unsorted[] | select(. as $k | $keys | index($k))] | join(", ")' \
    "$sibling")
  [ -n "$plugin_components" ] || continue

  # Report every marketplace entry that turns off strict mode and still
  # declares components of its own.
  conflicts=$(jq -r --argjson keys "$COMPONENT_KEYS" '
    (.plugins // [])[]
    | . as $p
    | [$p | keys_unsorted[] | select(. as $k | $keys | index($k))] as $declared
    | select($p.strict == false and ($declared | length) > 0)
    | "\($p.name // "(unnamed)")\t\($declared | join(", "))"
  ' "$f" 2>/dev/null)
  [ -n "$conflicts" ] || continue

  while IFS=$'\t' read -r entry declared; do
    echo "CONFLICTING MANIFESTS: $f entry \"$entry\" sets \"strict\": false and declares [$declared]; $sibling also declares [$plugin_components]"
    echo "  fix: set \"strict\": true in the $f entry, or remove the component specs from one location"
    fail=1
  done <<< "$conflicts"
done

# Brand display-name pass. Each client manifest holds the brand under a
# different key, so select the key from the file path.
BRAND_NAME='NinjaTrader'
for f in "${FILES[@]}"; do
  [ -f "$f" ] || continue
  jq -e . "$f" >/dev/null 2>&1 || continue
  case "$f" in
    *.cursor-plugin/plugin.json) brand_key='.displayName' ;;
    *.codex-plugin/plugin.json) brand_key='.interface.displayName' ;;
    *.claude-plugin/plugin.json) brand_key='.displayName' ;;
    *.claude-plugin/marketplace.json) brand_key='.plugins[0].displayName' ;;
    *) continue ;;
  esac

  found=$(jq -r "$brand_key // \"(absent)\"" "$f" 2>/dev/null)
  [ -n "$found" ] || found='(absent)'
  if [ "$found" != "$BRAND_NAME" ]; then
    echo "WRONG DISPLAY NAME: $f ($brand_key must be \"$BRAND_NAME\", found \"$found\")"
    fail=1
  fi
done

# Brand asset pass. A manifest points at a logo file with a relative path.
# A path that resolves to no file ships a broken image, so fail on it.
# The check reads only the asset keys that a client manifest supports.
ASSET_KEYS='.logo, .interface.logo, .interface.composerIcon'
for f in "${FILES[@]}"; do
  [ -f "$f" ] || continue
  jq -e . "$f" >/dev/null 2>&1 || continue
  while IFS= read -r asset; do
    [ -n "$asset" ] || continue
    # Strip a leading ./ so both "./assets/x.svg" and "assets/x.svg" resolve.
    if [ ! -f "${asset#./}" ]; then
      echo "MISSING BRAND ASSET: $f references \"$asset\", which resolves to no file"
      fail=1
    fi
  done <<EOF
$(jq -r "[$ASSET_KEYS] | map(select(type == \"string\")) | .[]" "$f" 2>/dev/null)
EOF
done

# Cross-manifest drift pass. The program below compares one logical
# field across every file that holds it and prints a line per
# disagreement. Each line names both files, both key paths, and both
# values. The program holds no single quote, so the shell keeps it
# verbatim inside the single-quoted assignment.
#
# The program reads JSON with python3. The repo already depends on
# python3 for scripts/ste-lint.py, so this adds no new dependency.
DRIFT_PY='
import json
import os
import sys

CLAUDE = ".claude-plugin/plugin.json"
MARKET = ".claude-plugin/marketplace.json"
CODEX = ".codex-plugin/plugin.json"
CURSOR = ".cursor-plugin/plugin.json"
MCPCFG = "mcp.json"
ALL = [CLAUDE, MARKET, CODEX, CURSOR, MCPCFG]

# The manifests that declare an mcpServers block. The Cursor manifest is
# absent from this list by design, so the two server passes below skip
# it. Cursor does not read a bundled server from its plugin manifest in
# this repo. A Cursor user adds the server from mcp.json instead, and
# README.md documents that step. The Cursor plugin schema does accept an
# mcpServers key, so a later change may bundle the server there. Add
# CURSOR to this list at that point.
SERVER_MANIFESTS = [CLAUDE, MARKET, CODEX, MCPCFG]

MISSING = object()
doc = {}
for path in ALL:
    with open(path) as handle:
        doc[path] = json.load(handle)


def get(obj, keys):
    """Return the value at a key path, or MISSING when absent."""
    cur = obj
    for key in keys:
        if isinstance(key, int):
            if not isinstance(cur, list) or len(cur) <= key:
                return MISSING
            cur = cur[key]
        else:
            if not isinstance(cur, dict) or key not in cur:
                return MISSING
            cur = cur[key]
    return cur


def at(path, *keys):
    """Return a labelled entry for one key path in one file."""
    label = path + " ." + ".".join(str(k) for k in keys)
    return (label, get(doc[path], keys))


def show(value):
    if value is MISSING:
        return "(absent)"
    return json.dumps(value, sort_keys=True)


failures = []


def compare(field, entries, skip_absent=False):
    """Report every entry that differs from the first present entry."""
    items = list(entries)
    if skip_absent:
        items = [(l, v) for l, v in items if v is not MISSING]
    if len(items) < 2:
        return
    base_label, base_value = items[0]
    for label, value in items[1:]:
        if value != base_value:
            failures.append(
                "MANIFEST DRIFT [{}]: {} = {} but {} = {}".format(
                    field, base_label, show(base_value), label, show(value)))


# The product version. It appears twice inside marketplace.json.
compare("version", [
    at(CLAUDE, "version"),
    at(MARKET, "metadata", "version"),
    at(MARKET, "plugins", 0, "version"),
    at(CODEX, "version"),
    at(CURSOR, "version"),
    at(MCPCFG, "version"),
])

# The long description. Codex repeats it under interface.longDescription.
compare("description", [
    at(CLAUDE, "description"),
    at(MARKET, "plugins", 0, "description"),
    at(CODEX, "description"),
    at(CODEX, "interface", "longDescription"),
    at(CURSOR, "description"),
])

compare("keywords", [
    at(CLAUDE, "keywords"),
    at(MARKET, "plugins", 0, "keywords"),
    at(CODEX, "keywords"),
    at(CURSOR, "keywords"),
])

# The author block. marketplace.json holds it twice, once as the
# marketplace owner and once on the plugin entry.
compare("author", [
    at(CLAUDE, "author"),
    at(MARKET, "owner"),
    at(MARKET, "plugins", 0, "author"),
    at(CODEX, "author"),
    at(CURSOR, "author"),
])

for field in ("homepage", "repository"):
    compare(field, [
        at(CLAUDE, field),
        at(MARKET, "plugins", 0, field),
        at(CODEX, field),
        at(CURSOR, field),
    ])

# The three policy URLs. Only the Codex schema names a key for each one
# today, so compare across every manifest that carries them and skip a
# manifest that does not. A second manifest that adds one of the three
# with a different value then fails this pass.
for field in ("websiteURL", "privacyPolicyURL", "termsOfServiceURL"):
    compare(field, [
        at(CLAUDE, field),
        at(MARKET, "plugins", 0, field),
        at(CODEX, "interface", field),
        at(CURSOR, field),
    ], skip_absent=True)


def servers(path):
    """Return a labelled mcpServers block for one manifest."""
    if path == MARKET:
        return at(path, "plugins", 0, "mcpServers")
    return at(path, "mcpServers")


key_entries = []
url_entries = []
for path in SERVER_MANIFESTS:
    label, block = servers(path)
    if not isinstance(block, dict):
        key_entries.append((label, MISSING))
        continue
    key_entries.append((label + " keys", sorted(block.keys())))
    for name in sorted(block.keys()):
        value = block[name]
        url = value.get("url", MISSING) if isinstance(value, dict) else MISSING
        url_entries.append((label + "[" + name + "].url", url))

# The server-registration name. A client builds the qualified tool name
# from this key, so a drift breaks every tool reference in the skills.
compare("mcpServers key", key_entries)
# The endpoint. All four files must name the same server.
compare("mcpServers url", url_entries)

# The skills array. The two Claude manifests must agree with each other
# and with the directories on disk. Claude Code refuses to load the
# plugin when a listed skill directory does not exist.
disk = []
if os.path.isdir("skills"):
    disk = sorted(
        "./skills/" + name for name in os.listdir("skills")
        if os.path.isdir(os.path.join("skills", name)))
compare("skills", [
    at(CLAUDE, "skills"),
    at(MARKET, "plugins", 0, "skills"),
    ("skills/ on disk", disk),
])

for line in failures:
    print(line)
sys.exit(0)
'

# Run the drift pass only for a full check. A run with file arguments
# stays a per-file check, so a fixture run keeps its current behavior.
if [ "$ARGC" -eq 0 ]; then
  drift_ready=1
  for f in "${FILES[@]}"; do
    if [ ! -f "$f" ]; then
      drift_ready=0
    elif ! jq -e . "$f" >/dev/null 2>&1; then
      drift_ready=0
    fi
  done
  if [ "$drift_ready" -eq 1 ]; then
    if ! drift=$(python3 -c "$DRIFT_PY" 2>&1); then
      echo "DRIFT CHECK ERROR: $drift"
      fail=1
    elif [ -n "$drift" ]; then
      printf '%s\n' "$drift"
      fail=1
    fi
  fi
fi
exit $fail
