#!/usr/bin/env bash
# Reference counts for every `pub` Rust item and every JS/TS export.
#
# Why this exists: rustc's `dead_code` lint does NOT fire on `pub` items in a
# library crate — it assumes an external consumer. In any workspace with
# library crates, the single largest class of dead code is therefore
# structurally invisible to the compiler, and a bundler's tree-shaking tells
# you as little about an exported TS symbol. This script is the substitute:
# one token-frequency pass over the whole tree, joined against every public
# definition.
#
# Counting model (a signal, not a proof — the verifier agent settles it):
#
#   total    every occurrence of the identifier anywhere, definition included
#   test     occurrences inside `#[cfg(test)]` blocks and under test paths
#   nontest  total - test
#   codegen  occurrences in non-source files (.js/.ts/.svelte/.toml/.json/
#            .html) — a hit here means the symbol may be reached through a
#            manifest scanner, a virtual module, injected JS, or a command
#            table, so a zero-reference claim against it needs proof, not a
#            grep
#
# A symbol with nontest <= 1 is referenced nowhere but its own definition.
# Two known blind spots, both of which cause FALSE NEGATIVES (a dead symbol
# looking alive), never false positives:
#   - common names (`new`, `init`, `state`) collide with unrelated tokens
#   - trait-method names are counted at every impl site
#
# Every path set comes from cfg.py. Lanes are handled by their `kind`, not
# their name, so a project may call its TypeScript lane whatever it likes.
#
# Usage: symbols.sh <out-dir>

set -euo pipefail

OUT="${1:?usage: symbols.sh <out-dir>}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CFG="python3 $HERE/cfg.py"
mkdir -p "$OUT"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

CFG_LINES=()
cfg_lines() {
  CFG_LINES=()
  local line
  while IFS= read -r line; do
    [ -n "$line" ] && CFG_LINES+=("$line")
  done < <($CFG "$@")
}

cfg_lines lanes
[ "${#CFG_LINES[@]}" -gt 0 ] || exit 0
LANES=("${CFG_LINES[@]}")
lane_of_kind() {
  local want="$1" lane
  for lane in "${LANES[@]}"; do
    [ "$($CFG get "lanes.$lane.kind")" = "$want" ] && { echo "$lane"; return 0; }
  done
  return 1
}
RUST_LANE="$(lane_of_kind rust || true)"
JS_LANE="$(lane_of_kind js || true)"

# `git grep` exits 1 when nothing matches, and nothing matching is an ordinary
# outcome here — a Rust-only repo has no file for the codegen pass to read.
# Under `set -o pipefail` that would kill the run, so each pass swallows it.
echo "  … token frequency (whole tree)"
cfg_lines refspecs
{ git grep -h -o -E '[A-Za-z_][A-Za-z0-9_]*' -- "${CFG_LINES[@]}" || true; } \
  | sort | uniq -c | awk '{print $2"\t"$1}' > "$TMP/all.freq"

echo "  … token frequency (codegen: manifests, generated and injected files)"
cfg_lines codegenspecs
{ git grep -h -o -E '[A-Za-z_][A-Za-z0-9_]*' -- "${CFG_LINES[@]}" || true; } \
  | sort | uniq -c | awk '{print $2"\t"$1}' > "$TMP/codegen.freq"

echo "  … token frequency (tests: test paths + inline cfg(test) blocks)"
cfg_lines testspecs
TEST_SPECS=("${CFG_LINES[@]}")
{
  git grep -h -o -E '[A-Za-z_][A-Za-z0-9_]*' -- "${TEST_SPECS[@]}" 2>/dev/null || true
  # Inline `#[cfg(test)] mod tests { … }` blocks, extracted by brace depth.
  if [ -n "$RUST_LANE" ] && [ -s "$OUT/files.$RUST_LANE" ]; then
    while read -r f; do
      awk '
        { line = $0
          t = line; opens = gsub(/{/, "{", t)
          t = line; closes = gsub(/}/, "}", t)
          if (!intest && line ~ /#\[cfg\(test\)\]/) armed = 1
          if (armed && opens > 0) { intest = 1; testdepth = depth; armed = 0 }
          if (intest) {
            rest = line
            while (match(rest, /[A-Za-z_][A-Za-z0-9_]*/)) {
              print substr(rest, RSTART, RLENGTH)
              rest = substr(rest, RSTART + RLENGTH)
            }
          }
          depth += opens - closes
          if (intest && depth <= testdepth) intest = 0
        }' "$f"
    done < "$OUT/files.$RUST_LANE"
  fi
} | { grep -E '^[A-Za-z_][A-Za-z0-9_]*$' || true; } | sort | uniq -c \
  | awk '{print $2"\t"$1}' > "$TMP/test.freq"

: > "$TMP/defs.rust.tsv"
: > "$TMP/defs.js.tsv"

# Definitions are scanned out of the lane's own file list rather than by
# pathspec, so the set of files a symbol can be DEFINED in is exactly the set
# the lane audits — one filter, in signals.sh, instead of two that can drift.
scan_defs() {  # scan_defs <lane> <grep-ere> <sed-script> <dest>
  local list="$OUT/files.$1"
  [ -s "$list" ] || return 0
  tr '\n' '\0' < "$list" \
    | xargs -0 grep -n -H -E "$2" 2>/dev/null \
    | sed -E "$3" > "$4" || true
}

if [ -n "$RUST_LANE" ]; then
  echo "  … public Rust definitions"
  # The `(const )?` before the kind group is load-bearing: without it
  # `pub const fn foo()` parses as kind=const, name=fn. With it, the optional
  # group eats `const ` only when a real kind keyword follows, so plain
  # `pub const FOO: u32` still parses as kind=const, name=FOO.
  scan_defs "$RUST_LANE" \
    '^[[:space:]]*pub(\([^)]*\))?[[:space:]]+(const[[:space:]]+)?(async[[:space:]]+)?(unsafe[[:space:]]+)?(fn|struct|enum|trait|const|static|type)[[:space:]]+[A-Za-z_]' \
    $'s/^([^:]+):([0-9]+):[[:space:]]*pub(\\([^)]*\\))?[[:space:]]+(const[[:space:]]+)?(async[[:space:]]+)?(unsafe[[:space:]]+)?(fn|struct|enum|trait|const|static|type)[[:space:]]+([A-Za-z_][A-Za-z0-9_]*).*/\\1\t\\2\t\\7\t\\8/' \
    "$TMP/defs.rust.tsv"
fi

if [ -n "$JS_LANE" ]; then
  echo "  … JS/TS exports"
  scan_defs "$JS_LANE" \
    '^[[:space:]]*export[[:space:]]+(async[[:space:]]+)?(function|const|let|class|type|interface)[[:space:]]+[A-Za-z_$]' \
    $'s/^([^:]+):([0-9]+):[[:space:]]*export[[:space:]]+(async[[:space:]]+)?(function|const|let|class|type|interface)[[:space:]]+([A-Za-z_$][A-Za-z0-9_$]*).*/\\1\t\\2\t\\4\t\\5/' \
    "$TMP/defs.js.tsv"
fi

join_counts() {
  awk -F'\t' -v OFS='\t' '
    FILENAME == a { all[$1] = $2; next }
    FILENAME == b { test[$1] = $2; next }
    FILENAME == c { cg[$1] = $2; next }
    {
      name = $4
      t = (name in all) ? all[name] : 0
      te = (name in test) ? test[name] : 0
      cgn = (name in cg) ? cg[name] : 0
      nt = t - te
      print $1, $2, $3, name, t, te, nt, cgn
    }' a="$1" b="$2" c="$3" "$1" "$2" "$3" "$4"
}

write_table() {  # write_table <out-name> <defs-file>
  local name="$1" defs="$2"
  [ -s "$defs" ] || return 0
  {
    printf 'file\tline\tkind\tname\ttotal\ttest\tnontest\tcodegen\n'
    join_counts "$TMP/all.freq" "$TMP/test.freq" "$TMP/codegen.freq" "$defs"
  } > "$OUT/$name.tsv"

  # Candidates: referenced nowhere outside their own definition (nontest <= 1),
  # or referenced only from tests. `codegen` is carried through so the agent
  # can see at a glance which claims need the manifest/JS/table proof.
  {
    printf 'file\tline\tkind\tname\ttotal\ttest\tnontest\tcodegen\tverdict\n'
    awk -F'\t' -v OFS='\t' 'NR > 1 && $7 <= 1 {
        print $0, ($6 > 0 ? "test-only" : "unreferenced")
      }' "$OUT/$name.tsv" | sort -t$'\t' -k1,1 -k2,2n
  } > "$OUT/${name}_candidates.tsv"

  echo "  $name.tsv: $(( $(wc -l < "$OUT/$name.tsv") - 1 )) definitions, $(( $(wc -l < "$OUT/${name}_candidates.tsv") - 1 )) unreferenced / test-only"
}

write_table symbols "$TMP/defs.rust.tsv"
write_table exports "$TMP/defs.js.tsv"
