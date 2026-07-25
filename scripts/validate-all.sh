#!/usr/bin/env bash
# validate-all.sh — run structural + functional validation across all
# 13 skills. Exit 0 if everything passes; 1 on any failure.
#
# Layers covered:
#   1. Structural — skill-creator's quick_validate.py on each skill
#      (frontmatter, description length, angle brackets, etc.)
#   2. Functional — run each smoke-testable Python script against its
#      fixture (when a fixture exists). Pass = exit 0 + valid JSON on
#      stdout. An unclassified script is a failure, not a skip.
#   3. Markdown checks — scripts/check-references.py verifies the
#      script and reference paths in each SKILL.md, every relative
#      markdown link and image target in the checkout, and the absence
#      of a stray </content> generation tag.
#
# The summary line reports how many layers actually ran. Layer 1 needs
# the skill-creator plugin cache, which a CI runner does not have.
#
# Activation layer (does the skill trigger on its documented phrases?)
# requires a running Claude Code session and is documented separately —
# see https://docs.ninjatrader.com/mcp/skills-reference.

set -u

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS_DIR="$ROOT/skills"
TOTAL_LAYERS=3
# The plugin cache path contains a content hash that rotates on plugin
# updates — resolve it instead of hardcoding one hash.
QUICK_VALIDATE="${QUICK_VALIDATE:-$(find "$HOME/.claude/plugins/cache" -path "*/skills/skill-creator/scripts/quick_validate.py" 2>/dev/null | head -1)}"

PASS="\033[32m✓\033[0m"
FAIL="\033[31m✗\033[0m"
INFO="\033[34m·\033[0m"

declare -i fail_count=0
declare -i skill_count=0

echo "==> validate-all.sh"
echo "    skills dir: $SKILLS_DIR"
echo

# CI runners do not have the skill-creator plugin cached, so
# quick_validate.py is normally absent there. Skip layer 1 with a
# visible notice in that case, rather than a hard failure, so layers
# 2 and 3 still run. A local checkout with the plugin installed keeps
# running layer 1 exactly as before.
#
# The ::warning:: prefix is a GitHub Actions workflow command. It is
# noise in a local terminal, so emit it only inside a CI run.
if [ ! -f "$QUICK_VALIDATE" ]; then
  notice="quick_validate.py not found — skipping layer 1 (structural validation)"
  if [ -n "${GITHUB_ACTIONS:-}" ]; then
    echo "::warning::$notice"
  else
    printf "   %b %s\n" "$INFO" "$notice"
  fi
  printf "   %b Install the example-skills plugin (see skill-creator) or\n" "$INFO"
  echo "      adjust the path in this script to run layer 1 locally."
  echo
  skip_layer1=1
else
  skip_layer1=0
fi
declare -i layers_run=$((TOTAL_LAYERS - skip_layer1))

# -----------------------------------------------------------------------------
# Layer 1: structural validation
# -----------------------------------------------------------------------------
if [ "$skip_layer1" -eq 0 ]; then
  echo "[1/3] Structural validation (quick_validate.py)"
  for skill_dir in "$SKILLS_DIR"/*/; do
    [ -d "$skill_dir" ] || continue
    skill="$(basename "$skill_dir")"
    skill_count+=1
    if out=$(python3 "$QUICK_VALIDATE" "$skill_dir" 2>&1); then
      printf "   %b %s\n" "$PASS" "$skill"
    else
      printf "   %b %s — %s\n" "$FAIL" "$skill" "$out"
      fail_count+=1
    fi
  done
  echo
else
  for skill_dir in "$SKILLS_DIR"/*/; do
    [ -d "$skill_dir" ] || continue
    skill_count+=1
  done
fi

# -----------------------------------------------------------------------------
# Layer 2: functional smoke tests per script
# -----------------------------------------------------------------------------

# Print one PASS or FAIL line for a finished run. $1 is the exit status
# and $2 is the captured output. The caller sets $skill and
# $script_name.
report_result() {
  local run_status="$1" out="$2"
  if [ "$run_status" -ne 0 ]; then
    printf "   %b %-20s %-25s (non-zero exit)\n" "$FAIL" "$skill" "$script_name"
    fail_count+=1
    return
  fi
  if printf '%s' "$out" | python3 -c "import sys,json; json.loads(sys.stdin.read())" >/dev/null 2>&1; then
    printf "   %b %-20s %-25s\n" "$PASS" "$skill" "$script_name"
  else
    printf "   %b %-20s %-25s (not valid JSON)\n" "$FAIL" "$skill" "$script_name"
    fail_count+=1
  fi
}

# Run a command, then report the result. Pass each argument separately.
# A separate argument keeps a path that holds a space intact. An earlier
# version built one command string and ran it through `eval`. That form
# split such a path into extra arguments and broke the run.
run_and_report() {
  local out run_status
  out=$("$@" 2>&1) && run_status=0 || run_status=$?
  report_result "$run_status" "$out"
}

# Same as run_and_report, with $1 redirected to the command's stdin.
run_and_report_with_stdin() {
  local fixture="$1"
  shift
  local out run_status
  out=$("$@" <"$fixture" 2>&1) && run_status=0 || run_status=$?
  report_result "$run_status" "$out"
}

echo "[2/3] Functional smoke tests"
for skill_dir in "$SKILLS_DIR"/*/; do
  [ -d "$skill_dir" ] || continue
  skill="$(basename "$skill_dir")"
  scripts_dir="$skill_dir/scripts"
  fixtures_dir="$scripts_dir/fixtures"
  [ -d "$scripts_dir" ] || continue

  # Each script is classified by how it takes input:
  #   stdin        — fixture JSON piped on stdin (+ optional CLI args)
  #   cli          — CLI args only, no fixture required
  #   file         — named fixtures passed as --flag path arguments
  #   manual       — skipped (composed/binary inputs that aren't worth
  #                  auto-testing). The list is explicit.
  #   unclassified — a script absent from every branch below. This is a
  #                  failure, not a skip. The author must classify a new
  #                  script, so no script reaches a release unverified.
  for script in "$scripts_dir"/*.py; do
    [ -f "$script" ] || continue
    script_name="$(basename "$script" .py)"

    invoke=""
    # Several scripts need no argument, so this array stays empty for
    # them. Under `set -u`, bash 3.2 (the stock macOS bash) rejects
    # "${cmd_args[@]}" on an empty array. Every expansion below uses the
    # ${cmd_args[@]+...} form, which yields zero arguments instead and
    # still keeps an argument that holds a space intact.
    cmd_args=()
    case "$script_name" in
      # --- stdin-fixture scripts ---------------------------------------------
      # atr.py takes --n. An abbreviated --period binds to
      # --periods-per-year instead and changes the result silently.
      atr)                invoke="stdin"; cmd_args=(--n 14) ;;
      vwap|profile)       invoke="stdin"; cmd_args=(--tick-size 0.25) ;;
      delta)              invoke="stdin" ;;
      resolve|rollover)   invoke="stdin" ;;
      reaction_size)      invoke="stdin"; cmd_args=(--offset-minutes 5) ;;
      importance_filter)  invoke="stdin"; cmd_args=(--products ES MNQ CL --min-importance 3) ;;
      streaks)            invoke="stdin"; cmd_args=(--value-per-point-map ES:50 NQ:20) ;;
      slippage)           invoke="stdin"; cmd_args=(--tick-size 0.25 --vwap-window-seconds 60) ;;
      compute_derived)    invoke="stdin" ;;
      scale_math)         invoke="stdin"; cmd_args=(--action partial_exit --pct 0.5) ;;
      ladder)             invoke="stdin"; cmd_args=(--mode even --legs 3 --band-points 6) ;;
      detect)             invoke="stdin" ;;
      excursion)          invoke="stdin" ;;
      whatif)             invoke="stdin"; cmd_args=(--scenario r_target --r-target 2.0) ;;
      correlation)        invoke="stdin" ;;
      hedge_sizing)       invoke="stdin" ;;
      whatif_live)        invoke="stdin"; cmd_args=(--new-stop 7148) ;;
      # --- CLI-only scripts --------------------------------------------------
      size)               invoke="cli"; cmd_args=(--netliq 100000 --risk-pct 1.0 --atr 6.0 --value-per-point 50) ;;
      bracket)            invoke="cli"; cmd_args=(--entry 7150 --direction long --stop-distance-points 9 --r-multiple 2.0 --tick-size 0.25 --qty 4 --value-per-point 50) ;;
      validate)           invoke="cli"; cmd_args=(--expression 'lastPrice(ESU6) > 7200') ;;
      # --- file-arg scripts (named fixtures under scripts/fixtures/) ---------
      health)             invoke="file"
                          cmd_args=(--portfolio "$fixtures_dir/portfolio.json"
                                    --snapshot "$fixtures_dir/snapshot.json"
                                    --risk-settings "$fixtures_dir/risk_settings.json") ;;
      stop_drift)         invoke="file"
                          cmd_args=(--orders "$fixtures_dir/order_history.json"
                                    --symbol ESU6 --entry-price 7150 --direction long
                                    --tick-size 0.25 --value-per-point 50 --net-pos 4) ;;
      cross_symbol)       invoke="file"
                          cmd_args=(--symbol "ES=$fixtures_dir/es_cross_symbol.json"
                                    --symbol "NQ=$fixtures_dir/nq_cross_symbol.json"
                                    --symbol "RTY=$fixtures_dir/rty_cross_symbol.json") ;;
      # --- manual-only (composed/binary inputs) ------------------------------
      # A chart script writes a PNG, so it needs a writable output path
      # rather than a JSON stdout check. assemble_report composes several
      # tool payloads that no single fixture represents.
      assemble_report|candles|profile_chart|equity_curve)
                          invoke="manual" ;;
      *)                  invoke="unclassified" ;;
    esac

    case "$invoke" in
      stdin)
        fixture=""
        [ -f "$fixtures_dir/$script_name.json" ] && fixture="$fixtures_dir/$script_name.json"
        if [ -z "$fixture" ] && [ -d "$fixtures_dir" ]; then
          prefix_match=$(find "$fixtures_dir" -maxdepth 1 -name "${script_name}*.json" 2>/dev/null | head -1)
          [ -n "$prefix_match" ] && fixture="$prefix_match"
        fi
        if [ -z "$fixture" ] && [ -d "$fixtures_dir" ]; then
          # Last resort: first JSON in the dir, but skip names reserved
          # for the "file" invoke branch (position-watchdog's health /
          # stop_drift read these by path, not from stdin).
          for candidate in "$fixtures_dir"/*.json; do
            [ -f "$candidate" ] || continue
            case "$(basename "$candidate")" in
              portfolio.json|snapshot.json|order_details.json|order_history.json|risk_settings.json) continue ;;
            esac
            fixture="$candidate"
            break
          done
        fi
        if [ -z "$fixture" ]; then
          printf "   %b %-20s %-25s (no fixture — skipped)\n" "$INFO" "$skill" "$script_name"
          continue
        fi
        run_and_report_with_stdin "$fixture" python3 "$script" ${cmd_args[@]+"${cmd_args[@]}"}
        # Also exercise the --file input path on one representative
        # script (vwap) so it stays covered alongside the stdin path.
        if [ "$script_name" = "vwap" ]; then
          run_and_report python3 "$script" ${cmd_args[@]+"${cmd_args[@]}"} --file "$fixture"
        fi
        ;;
      cli|file)
        run_and_report python3 "$script" ${cmd_args[@]+"${cmd_args[@]}"}
        ;;
      manual)
        printf "   %b %-20s %-25s (manual test — skipped)\n" "$INFO" "$skill" "$script_name"
        ;;
      *)
        printf "   %b %-20s %-25s (unclassified)\n" "$FAIL" "$skill" "$script_name"
        printf "       Classify %s in the case table in scripts/validate-all.sh.\n" "$script"
        printf "       Use stdin, cli, file, or the explicit manual list.\n"
        fail_count+=1
        ;;
    esac
  done
done
echo

# -----------------------------------------------------------------------------
# Layer 3: markdown checks — SKILL.md reference paths, markdown link and
# image targets across the checkout, and stray generation tags.
# -----------------------------------------------------------------------------
echo "[3/3] Markdown reference, link, and stray-tag checks"
if ! python3 "$ROOT/scripts/check-references.py" --repo-root "$ROOT" "$SKILLS_DIR"; then
  fail_count+=1
fi
echo

# -----------------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------------
if [ "$fail_count" -eq 0 ]; then
  printf "==> All %d skills passed. %d of %d layers ran.\n" \
    "$skill_count" "$layers_run" "$TOTAL_LAYERS"
else
  noun="failures"
  [ "$fail_count" -eq 1 ] && noun="failure"
  printf "==> %d %s across %d skills. %d of %d layers ran.\n" \
    "$fail_count" "$noun" "$skill_count" "$layers_run" "$TOTAL_LAYERS"
fi
if [ "$skip_layer1" -eq 1 ]; then
  echo "    Layer 1 did not run."
fi
[ "$fail_count" -eq 0 ] && exit 0
exit 1
