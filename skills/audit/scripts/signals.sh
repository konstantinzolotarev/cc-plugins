#!/usr/bin/env bash
# Phase 0 of /audit — build the signal pack that every agent reads.
#
# Nothing here uses an LLM and nothing here writes to the working tree. The
# whole point is that the repo gets triaged mechanically first, so the agents
# spend their tokens judging candidates instead of scanning.
#
#   ./signals.sh --out <dir>            full pack (lint build: minutes)
#   ./signals.sh --out <dir> --quick    skip the lint builds (~30 s)
#
# Every glob, exclude and toolchain command comes from cfg.py — skill
# defaults, plus repo detection, plus the project's .claude/audit/config.json.
# Nothing about any one repo is written down here.
#
# The Rust lint runs under its own CARGO_TARGET_DIR: pedantic/nursery flags
# change the fingerprint of every crate, so sharing `target/` would force the
# next ordinary build into a full rebuild. Costs disk, saves the dev loop.

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG="python3 $HERE/cfg.py"

OUT="$ROOT/.local/audit-signals"
QUICK=0
while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    --quick) QUICK=1; shift ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
done
mkdir -p "$OUT"

# bash 3.2 (macOS system bash) has no `mapfile` and no namerefs, so config
# lists come back through one global array.
CFG_LINES=()
cfg_lines() {
  CFG_LINES=()
  local line
  while IFS= read -r line; do
    [ -n "$line" ] && CFG_LINES+=("$line")
  done < <($CFG "$@")
}

SKIPPED=()
skip() { SKIPPED+=("$1"); echo "  ▸ skipped: $1"; }

echo "audit signals → $OUT"
echo "commit: $(git rev-parse --short HEAD)  branch: $(git rev-parse --abbrev-ref HEAD)"

cfg_lines lanes
if [ "${#CFG_LINES[@]}" -eq 0 ]; then
  echo "no lane detected (no Cargo.toml, no package.json) — nothing to audit" >&2
  exit 1
fi
LANES=("${CFG_LINES[@]}")
echo "lanes: ${LANES[*]}"

# ── file lists ───────────────────────────────────────────────────────────────
# Includes go to git as pathspecs (exact); pattern excludes go through grep,
# because git matches a wildcard `:(exclude)` by extension alone and would
# drop far more than asked. See assets/defaults.json.
for lane in "${LANES[@]}"; do
  cfg_lines pathspecs "$lane"
  ex="$($CFG exclude-re "$lane")"
  if [ -n "$ex" ]; then
    git ls-files -- "${CFG_LINES[@]}" | grep -v -E "$ex" > "$OUT/files.$lane" || true
  else
    git ls-files -- "${CFG_LINES[@]}" > "$OUT/files.$lane"
  fi
  echo "  files.$lane: $(wc -l < "$OUT/files.$lane" | tr -d ' ')"
done

# ── dead code: public symbol reference counts ────────────────────────────────
echo "▸ symbols"
bash "$HERE/symbols.sh" "$OUT"

# ── duplication: clone index ─────────────────────────────────────────────────
echo "▸ clones"
for lane in "${LANES[@]}"; do
  window="$($CFG get "lanes.$lane.clone_window")"
  top="$($CFG get "lanes.$lane.clone_top")"
  python3 "$HERE/clones.py" --window "${window:-8}" --top "${top:-100}" \
    < "$OUT/files.$lane" > "$OUT/clones_$lane.tsv"
  echo "  clones_$lane.tsv: $(( $(wc -l < "$OUT/clones_$lane.tsv") - 1 )) groups"
done

# ── overcomplication: metrics x churn ────────────────────────────────────────
echo "▸ complexity"
cat "$OUT"/files.* \
  | python3 "$HERE/complexity.py" --top-fns 150 --top-files 60 \
  > "$OUT/complexity.tsv"
echo "  complexity.tsv: $(( $(wc -l < "$OUT/complexity.tsv") - 1 )) rows"

# ── style: the #[allow] census (Rust only) ───────────────────────────────────
# An `#[allow]` with no comment above it is a lint someone silenced rather
# than answered. That is a style finding in its own right.
if [ -f "$OUT/files.rust" ]; then
  echo "▸ allow census"
  {
    printf 'file\tline\tlints\tjustified\n'
    while read -r f; do
      awk -v file="$f" -F'\n' '
        /#\[allow\(/ {
          lints = $0
          sub(/.*#\[allow\(/, "", lints); sub(/\).*/, "", lints)
          gsub(/[[:space:]]/, "", lints)
          just = (prev ~ /^[[:space:]]*\/\//) ? "yes" : "no"
          printf "%s\t%d\t%s\t%s\n", file, NR, lints, just
        }
        { prev = $0 }' "$f"
    done < "$OUT/files.rust"
  } > "$OUT/allow_census.tsv"
  echo "  allow_census.tsv: $(( $(wc -l < "$OUT/allow_census.tsv") - 1 )) allows, $(awk -F'\t' 'NR>1 && $4 == "no"' "$OUT/allow_census.tsv" | wc -l | tr -d ' ') unjustified"
fi

# ── dependencies ─────────────────────────────────────────────────────────────
if [ -f "$OUT/files.rust" ]; then
  if command -v cargo-machete >/dev/null 2>&1; then
    echo "▸ unused deps"
    cargo machete > "$OUT/deps.txt" 2>&1 || true
    echo "  deps.txt: $(grep -c '^\t' "$OUT/deps.txt" 2>/dev/null || echo 0) candidates"
  else
    skip "unused deps (cargo-machete not installed)"
  fi
fi

# ── project-owned extra signals ──────────────────────────────────────────────
# A repo's hand-maintained wiring — plugin tables, registries, generated lists
# — fails at runtime, not at compile time, and no generic script can know its
# shape. config.json names the scripts; each gets the out-dir and writes TSVs
# into it. shards.md tells the agent what those tables mean.
cfg_lines extra-signals
if [ ${#CFG_LINES[@]} -gt 0 ]; then
  echo "▸ extra signals"
  for script in "${CFG_LINES[@]}"; do
    if [ -f "$script" ]; then
      echo "  … $script"
      bash "$script" "$OUT" || echo "  $script failed — see above"
    else
      skip "extra signal $script (not found)"
    fi
  done
fi

# ── the slow half ────────────────────────────────────────────────────────────
if [ "$QUICK" = "1" ]; then
  echo "▸ lint SKIPPED (--quick)"
  # Leave no empty lint output behind: slice.sh and the agents treat a missing
  # file as "this signal wasn't collected", an empty one as "no findings".
  rm -f "$OUT/lint.tsv" "$OUT/lint_by_rule.tsv" "$OUT/lint_by_file.tsv"
  for lane in "${LANES[@]}"; do
    rm -f "$OUT/$($CFG get "lanes.$lane.lint.out")"
  done
  SKIPPED+=("lint (--quick)")
else
  for lane in "${LANES[@]}"; do
    cmd="$($CFG get "lanes.$lane.lint.cmd")"
    parser="$($CFG get "lanes.$lane.lint.parser")"
    dest="$($CFG get "lanes.$lane.lint.out")"
    if [ -z "$cmd" ]; then
      skip "lint for lane '$lane' (no command configured or detected)"
      continue
    fi
    echo "▸ lint [$lane]: $cmd"
    case "$parser" in
      cargo-json)
        target="$($CFG get "lanes.$lane.lint.target_dir")"
        CARGO_TARGET_DIR="${target:+$ROOT/$target}" \
          bash -c "$cmd" 2>/dev/null \
          | python3 "$HERE/lints.py" "$OUT" || echo "  lint failed — see above"
        ;;
      *)
        bash -c "$cmd" > "$OUT/$dest" 2>&1 || true
        echo "  $dest: $(grep -c -E '^(Error|Warn)' "$OUT/$dest" 2>/dev/null || echo 0) lines flagged"
        ;;
    esac
  done
fi

# ── shard coverage ───────────────────────────────────────────────────────────
# The drift check for the shard map itself: a new crate or top-level directory
# that no shard glob matches is a hole no agent will look into.
if [ -f "$ROOT/.claude/audit/shards.md" ]; then
  echo "▸ shard coverage"
  python3 "$HERE/shards.py" coverage "$OUT" || true
else
  skip "shard coverage (no .claude/audit/shards.md — run /audit --init)"
fi

# ── summary ──────────────────────────────────────────────────────────────────
{
  echo "audit signal pack"
  echo "generated: $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo "commit:    $(git rev-parse HEAD)"
  echo "branch:    $(git rev-parse --abbrev-ref HEAD)"
  echo "lanes:     ${LANES[*]}"
  echo "quick:     $QUICK"
  echo
  for f in "$OUT"/*.tsv; do
    [ -e "$f" ] || continue
    printf '%-28s %s rows\n' "$(basename "$f")" "$(( $(wc -l < "$f") - 1 ))"
  done
  if [ ${#SKIPPED[@]} -gt 0 ]; then
    echo
    echo "signals NOT collected — say so in the report rather than reading"
    echo "their absence as a clean result:"
    for s in "${SKIPPED[@]}"; do echo "  - $s"; done
  fi
} > "$OUT/summary.txt"

echo
cat "$OUT/summary.txt"
