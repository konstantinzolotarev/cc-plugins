#!/usr/bin/env python3
"""Clone index — a zero-install stand-in for jscpd.

Reads a newline-separated file list on stdin, emits a TSV of duplicate
groups sorted by (span length x occurrences).

Two passes, reported separately because they mean different things:

  exact       comments and whitespace normalized away, identifiers kept.
              A hit is copy-paste, or two things that started as copy-paste.
              High confidence, low judgement needed.

  structural  identifiers, literals and numbers collapsed to placeholders.
              A hit is the *same shape* written twice with different names —
              which is where "these two drivers are the same state machine"
              lives, and also where the noise lives, so a window must carry
              at least --min-struct distinct keyword/operator tokens to
              count. Without that filter every Rust match arm and every
              Svelte prop declaration collides.

Windows are merged: a 30-line clone reports as one 30-line group, not as
23 overlapping 8-line ones.

Line numbers in the output are ORIGINAL file lines — blank/comment/trivial
lines are dropped before hashing but the mapping back is preserved, so a
span can be read straight out of the file.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from collections import defaultdict

# Lines that carry no structure on their own. Dropping them keeps a window
# from being 8 closing braces, which otherwise matches everywhere.
TRIVIAL = {
    "{", "}", "};", "});", ")", ");", "],", "]", "[", "(", ",", "=> {",
    "} else {", "});", "})", "});", "return;", "break;", "continue;",
    "<script>", "</script>", "<style>", "</style>", "---", "```",
}

RUST_KEYWORDS = {
    "as", "async", "await", "break", "const", "continue", "crate", "dyn",
    "else", "enum", "extern", "false", "fn", "for", "if", "impl", "in",
    "let", "loop", "match", "mod", "move", "mut", "pub", "ref", "return",
    "self", "Self", "static", "struct", "super", "trait", "true", "type",
    "unsafe", "use", "where", "while", "Some", "None", "Ok", "Err",
}
JS_KEYWORDS = {
    "async", "await", "break", "case", "catch", "class", "const", "continue",
    "default", "delete", "do", "else", "export", "extends", "finally", "for",
    "function", "if", "import", "in", "instanceof", "let", "new", "return",
    "static", "switch", "this", "throw", "try", "typeof", "var", "void",
    "while", "yield", "true", "false", "null", "undefined",
}
KEYWORDS = RUST_KEYWORDS | JS_KEYWORDS

IDENT = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
NUMBER = re.compile(r"\b\d[\d_.eExXaAbBcCdDfF]*\b")
STRING = re.compile(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'")
LINE_COMMENT = re.compile(r"//.*$")
HASH_COMMENT = re.compile(r"^\s*#.*$")
OPERATORS = re.compile(r"[=!<>+\-*/%&|^?:;,.(){}\[\]]+")


def strip_block_comments(text: str) -> str:
    """Remove /* ... */ spans. Crude — a /* inside a string literal eats
    until the next */. Acceptable: this is a candidate generator, and the
    verifier reads the real file."""
    out, i, n = [], 0, len(text)
    while i < n:
        j = text.find("/*", i)
        if j < 0:
            out.append(text[i:])
            break
        out.append(text[i:j])
        k = text.find("*/", j + 2)
        if k < 0:
            break
        # Keep newlines so line numbering survives.
        out.append("\n" * text.count("\n", j, k + 2))
        i = k + 2
    return "".join(out)


def normalize(line: str, structural: bool) -> str:
    line = LINE_COMMENT.sub("", line)
    line = line.strip()
    if not line or line in TRIVIAL:
        return ""
    line = re.sub(r"\s+", " ", line)
    if structural:
        line = STRING.sub('"S"', line)
        line = NUMBER.sub("0", line)
        line = IDENT.sub(lambda m: m.group(0) if m.group(0) in KEYWORDS else "#", line)
    return line


def struct_score(window: list[str]) -> int:
    """Distinct keyword + operator-run tokens in a window. The noise filter
    for structural mode."""
    seen = set()
    for line in window:
        for tok in IDENT.findall(line):
            if tok in KEYWORDS:
                seen.add(tok)
        for op in OPERATORS.findall(line):
            seen.add(op)
    return len(seen)


def load(path: str, structural: bool) -> tuple[list[str], list[int]]:
    try:
        raw = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return [], []
    raw = strip_block_comments(raw)
    kept, lineno = [], []
    for idx, line in enumerate(raw.split("\n"), start=1):
        if path.endswith((".toml", ".sh", ".py")) and HASH_COMMENT.match(line):
            continue
        norm = normalize(line, structural)
        if norm:
            kept.append(norm)
            lineno.append(idx)
    return kept, lineno


def run(files: list[str], window: int, min_occ: int, structural: bool,
        min_struct: int, top: int, cross_file_only: bool) -> list[dict]:
    kept: dict[str, list[str]] = {}
    lines: dict[str, list[int]] = {}
    for f in files:
        k, l = load(f, structural)
        if len(k) >= window:
            kept[f], lines[f] = k, l

    # hash -> [(file, kept_index)]
    index: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for f, k in kept.items():
        for i in range(len(k) - window + 1):
            h = hashlib.blake2b("\n".join(k[i:i + window]).encode(),
                                digest_size=12).hexdigest()
            index[h].append((f, i))

    consumed: set[tuple[str, int]] = set()
    groups = []
    # Longest first would need the merge to run first; instead merge greedily
    # in file order and let the merge eat the shifted duplicates.
    for h, occ in index.items():
        if len(occ) < min_occ:
            continue
        if any(o in consumed for o in occ):
            continue
        distinct_files = len({f for f, _ in occ})
        if cross_file_only and distinct_files < 2:
            continue
        if distinct_files < 2:
            # Same-file repeats must be genuinely apart, not overlapping.
            idxs = sorted(i for _, i in occ)
            if min(b - a for a, b in zip(idxs, idxs[1:])) < window:
                continue

        length = window
        cur = occ
        while True:
            nxt = [(f, i + 1) for f, i in cur]
            if any(i + window > len(kept[f]) for f, i in nxt):
                break
            nh = {hashlib.blake2b("\n".join(kept[f][i:i + window]).encode(),
                                  digest_size=12).hexdigest() for f, i in nxt}
            if len(nh) != 1:
                break
            nh = nh.pop()
            if set(index.get(nh, [])) != set(nxt):
                break
            consumed.update(nxt)
            cur = nxt
            length += 1

        first_f, first_i = occ[0]
        win = kept[first_f][first_i:first_i + window]
        if structural and struct_score(win) < min_struct:
            continue

        spans = []
        for f, i in sorted(occ):
            start = lines[f][i]
            end = lines[f][min(i + length - 1, len(lines[f]) - 1)]
            spans.append(f"{f}:{start}-{end}")
        groups.append({
            "lines": length,
            "occ": len(occ),
            "files": distinct_files,
            "spans": spans,
            "sample": " | ".join(win[:3])[:160],
        })

    groups.sort(key=lambda g: (g["lines"] * g["occ"], g["files"]), reverse=True)
    return groups[:top]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=8)
    ap.add_argument("--min-occ", type=int, default=2)
    ap.add_argument("--min-struct", type=int, default=6)
    ap.add_argument("--top", type=int, default=120)
    ap.add_argument("--mode", choices=["exact", "structural", "both"],
                    default="both")
    ap.add_argument("--cross-file-only", action="store_true")
    args = ap.parse_args()

    files = [ln.strip() for ln in sys.stdin if ln.strip()]
    modes = ["exact", "structural"] if args.mode == "both" else [args.mode]

    print("mode\tlines\toccurrences\tfiles\tspans\tsample")
    for mode in modes:
        groups = run(files, args.window, args.min_occ, mode == "structural",
                     args.min_struct, args.top, args.cross_file_only)
        for g in groups:
            print(f"{mode}\t{g['lines']}\t{g['occ']}\t{g['files']}\t"
                  f"{' '.join(g['spans'])}\t{g['sample']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
