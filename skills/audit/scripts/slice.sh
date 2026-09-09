#!/usr/bin/env bash
# Cut the signal pack down to one shard, so a shard agent reads 40 rows of
# lint instead of 9000.
#
#   slice.sh <signal-dir> <shard-name>
#
# The shard's globs come from .claude/audit/shards.md via shards.py — the
# caller never retypes them, so a brief and its slice can't disagree.
#
# Writes <signal-dir>/shards/<shard-name>/ with the same TSV names and headers
# as the full pack, holding only rows that touch the shard's files.
#
# Clone groups match if ANY of their spans is in the shard — a group whose
# other half lives elsewhere is exactly what the cross-area agent wants, but
# the local agent should see it too rather than have it disappear.

set -euo pipefail

SIG="${1:?usage: slice.sh <signal-dir> <shard-name>}"
SHARD="${2:?usage: slice.sh <signal-dir> <shard-name>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG="python3 $HERE/cfg.py"
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

DEST="$SIG/shards/$SHARD"
mkdir -p "$DEST"

# Empty arrays and `set -u` do not mix in bash 3.2 (macOS system bash), so
# every expansion of CFG_LINES goes through this guard rather than "${a[@]}".
CFG_LINES=()
cfg_lines() {
  CFG_LINES=()
  local line
  while IFS= read -r line; do
    [ -n "$line" ] && CFG_LINES+=("$line")
  done < <("$@")
}
cfg_count() { echo "${#CFG_LINES[@]}"; }

cfg_lines python3 "$HERE/shards.py" globs "$SHARD"
git ls-files -- "${CFG_LINES[@]}" > "$DEST/files.txt"
if [ ! -s "$DEST/files.txt" ]; then
  echo "slice: no files matched for shard '$SHARD'" >&2
  exit 1
fi

# Cargo reports diagnostic paths relative to whichever root it invoked rustc
# from, which is not always the workspace root — so lint rows are matched on
# basename as well. Over-matches when two crates share a file name
# (mod.rs, lib.rs); the agent has the crate in the row either way.
sed -E 's#.*/##' "$DEST/files.txt" | sort -u > "$DEST/basenames.txt"

slice_by_path() {
  local src="$SIG/$1" dst="$DEST/$1"
  [ -s "$src" ] || return 0
  { head -1 "$src"; grep -F -f "$DEST/files.txt" "$src" || true; } > "$dst"
}

slice_by_basename() {
  local src="$SIG/$1" dst="$DEST/$1"
  [ -s "$src" ] || return 0
  { head -1 "$src"; grep -F -f "$DEST/basenames.txt" "$src" || true; } > "$dst"
}

TABLES=(symbols_candidates.tsv exports_candidates.tsv complexity.tsv
        allow_census.tsv)
cfg_lines $CFG lanes
for lane in "${CFG_LINES[@]}"; do
  TABLES+=("clones_$lane.tsv")
done
cfg_lines $CFG extra-tables path
if [ "$(cfg_count)" -gt 0 ]; then TABLES+=("${CFG_LINES[@]}"); fi

for t in "${TABLES[@]}"; do slice_by_path "$t"; done
for t in lint.tsv lint_by_file.tsv; do slice_by_basename "$t"; done

# Small cross-cutting tables (a project's registry drift, say) are copied
# whole — filtering them by path would hide exactly the row that matters,
# which is the one with a blank on the shard's side.
cfg_lines $CFG extra-tables whole
if [ "$(cfg_count)" -gt 0 ]; then
  for t in "${CFG_LINES[@]}"; do
    [ -s "$SIG/$t" ] && cp "$SIG/$t" "$DEST/$t"
  done
fi

{
  echo "shard: $SHARD"
  echo "files: $(wc -l < "$DEST/files.txt" | tr -d ' ')"
  for f in "$DEST"/*.tsv; do
    [ -e "$f" ] || continue
    printf '%-28s %s rows\n' "$(basename "$f")" "$(( $(wc -l < "$f") - 1 ))"
  done
} | tee "$DEST/summary.txt"
