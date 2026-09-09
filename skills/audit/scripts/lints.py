#!/usr/bin/env python3
"""Flatten `cargo clippy --message-format=json` into three TSVs.

Reads cargo's JSON stream on stdin, writes into <out-dir>:

  lint.tsv          one row per diagnostic: file, line, level, code, message
  lint_by_rule.tsv  rule, count, distinct files, top 3 files
  lint_by_file.tsv  file, count, distinct rules

The per-rule rollup is the one that matters for the audit. A pedantic run over
a large workspace emits thousands of rows, and anyone can read those by
running clippy. What an agent is for is reading the SHAPE: one rule firing 200
times in a single module is a convention nobody ever decided, and that is a
finding; the same rule firing twice across the workspace is noise.
"""

from __future__ import annotations

import collections
import json
import pathlib
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: lints.py <out-dir>", file=sys.stderr)
        return 2
    out = pathlib.Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    for line in sys.stdin:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("reason") != "compiler-message":
            continue
        msg = rec.get("message") or {}
        level = msg.get("level", "")
        if level not in ("warning", "error"):
            continue
        code = ((msg.get("code") or {}).get("code")) or "rustc"
        text = (msg.get("message") or "").split("\n")[0]
        spans = msg.get("spans") or []
        primary = next((s for s in spans if s.get("is_primary")), None) or \
            (spans[0] if spans else None)
        if not primary:
            continue
        file_name = primary.get("file_name", "")
        # Cargo reports paths relative to each crate; keep them as given —
        # they are still unique enough to grep, and rewriting them guesses.
        rows.append((file_name, primary.get("line_start", 0), level, code, text))

    # Cargo re-emits diagnostics for every target that compiles the same file
    # (lib + tests + bins), so dedupe on the anchor.
    rows = sorted(set(rows), key=lambda r: (r[3], r[0], r[1]))

    with (out / "lint.tsv").open("w") as fh:
        fh.write("file\tline\tlevel\trule\tmessage\n")
        for r in rows:
            fh.write(f"{r[0]}\t{r[1]}\t{r[2]}\t{r[3]}\t{r[4]}\n")

    by_rule: dict[str, list[str]] = collections.defaultdict(list)
    by_file: dict[str, list[str]] = collections.defaultdict(list)
    for file_name, _line, _level, code, _text in rows:
        by_rule[code].append(file_name)
        by_file[file_name].append(code)

    with (out / "lint_by_rule.tsv").open("w") as fh:
        fh.write("rule\tcount\tfiles\ttop_files\n")
        for rule, files in sorted(by_rule.items(), key=lambda kv: -len(kv[1])):
            top = collections.Counter(files).most_common(3)
            fh.write(f"{rule}\t{len(files)}\t{len(set(files))}\t"
                     + " ".join(f"{f}({n})" for f, n in top) + "\n")

    with (out / "lint_by_file.tsv").open("w") as fh:
        fh.write("file\tcount\trules\n")
        for f, codes in sorted(by_file.items(), key=lambda kv: -len(kv[1])):
            fh.write(f"{f}\t{len(codes)}\t{len(set(codes))}\n")

    print(f"  lint.tsv: {len(rows)} diagnostics, {len(by_rule)} distinct rules, "
          f"{len(by_file)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
