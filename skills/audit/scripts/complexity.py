#!/usr/bin/env python3
"""Complexity outliers, crossed with churn.

Reads a newline-separated file list on stdin, emits one TSV row per function
(and one per file) with the metrics that correlate with "this grew a feature
at a time and nobody ever went back":

  lines     body length
  nesting   max brace depth inside the body
  branches  if / match / while / for / && / || / ? occurrences
  arms      `=>` count (match arms, closures)
  params    parameter count
  churn90   commits touching the file in the last 90 days
  score     (lines/40 + nesting + branches/8 + arms/25 + params/4)
            x log1p(churn90)

The churn factor is the point. A 400-line function nobody has touched in a
year is not where the risk is; a 200-line one that changed eleven times last
quarter is a function that is still absorbing features, and that is what
"overcomplicated by accretion" looks like from the outside.

Strings, chars, raw strings (r#"..."#) and comments are masked out before any
counting, so the injected JS/HTML literals in the proxy don't register as
2000 branches.
"""

from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
from collections import defaultdict

RUST_FN = re.compile(
    r"^[ \t]*(?:pub(?:\([^)]*\))?[ \t]+)?(?:default[ \t]+)?(?:const[ \t]+)?"
    r"(?:async[ \t]+)?(?:unsafe[ \t]+)?(?:extern[ \t]+\"[^\"]*\"[ \t]+)?"
    r"fn[ \t]+([A-Za-z_][A-Za-z0-9_]*)",
    re.M,
)
JS_FN = re.compile(
    r"^[ \t]*(?:export[ \t]+)?(?:default[ \t]+)?(?:async[ \t]+)?function[ \t]*"
    r"\*?[ \t]*([A-Za-z_$][A-Za-z0-9_$]*)|"
    r"^[ \t]*(?:export[ \t]+)?(?:const|let|var)[ \t]+([A-Za-z_$][A-Za-z0-9_$]*)"
    r"[ \t]*=[ \t]*(?:async[ \t]+)?(?:function|\()",
    re.M,
)
SCRIPT_BLOCK = re.compile(r"<script[^>]*>(.*?)</script>", re.S | re.I)


def mask_code(text: str, rust: bool) -> str:
    """Replace comment/string/char content with spaces, preserving length and
    newlines, so offsets and line numbers stay valid."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            j = text.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                out[k] = " "
            i = j
            continue
        if c == "/" and nxt == "*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, j):
                if out[k] != "\n":
                    out[k] = " "
            i = j
            continue
        if rust and c == "r" and i + 1 < n and text[i + 1] in "#\"":
            j = i + 1
            hashes = 0
            while j < n and text[j] == "#":
                hashes += 1
                j += 1
            if j < n and text[j] == '"':
                term = '"' + "#" * hashes
                end = text.find(term, j + 1)
                end = n if end < 0 else end + len(term)
                for k in range(i, end):
                    if out[k] != "\n":
                        out[k] = " "
                i = end
                continue
        if c in "\"'" or (c == "`" and not rust):
            quote = c
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == quote:
                    j += 1
                    break
                if text[j] == "\n" and quote == "'":
                    break
                j += 1
            for k in range(i, min(j, n)):
                if out[k] != "\n":
                    out[k] = " "
            i = j
            continue
        i += 1
    return "".join(out)


def body_span(masked: str, start: int) -> tuple[int, int] | None:
    """From a signature start, find the body's { .. } by brace matching."""
    open_at = masked.find("{", start)
    if open_at < 0:
        return None
    # A signature that hits a `;` before `{` is a trait method declaration.
    semi = masked.find(";", start)
    if 0 <= semi < open_at:
        return None
    depth, i, n = 0, open_at, len(masked)
    while i < n:
        if masked[i] == "{":
            depth += 1
        elif masked[i] == "}":
            depth -= 1
            if depth == 0:
                return open_at, i
        i += 1
    return None


def metrics(masked_body: str) -> dict:
    depth = max_depth = 0
    for ch in masked_body:
        if ch == "{":
            depth += 1
            max_depth = max(max_depth, depth)
        elif ch == "}":
            depth -= 1
    branches = (
        len(re.findall(r"\bif\b|\bmatch\b|\bwhile\b|\bfor\b|\bcatch\b",
                       masked_body))
        + masked_body.count("&&")
        + masked_body.count("||")
        + len(re.findall(r"\?[^.]", masked_body))
    )
    return {
        "nesting": max_depth,
        "branches": branches,
        "arms": masked_body.count("=>"),
    }


def params_of(masked: str, sig_start: int, body_open: int) -> int:
    seg = masked[sig_start:body_open]
    open_paren = seg.find("(")
    if open_paren < 0:
        return 0
    depth, count, seen = 0, 0, False
    for ch in seg[open_paren:]:
        if ch in "([<":
            depth += 1
        elif ch in ")]>":
            depth -= 1
            if depth == 0:
                break
        elif ch == "," and depth == 1:
            count += 1
        elif depth == 1 and not ch.isspace():
            seen = True
    return count + 1 if seen else 0


def churn_map(days: int) -> dict[str, int]:
    try:
        out = subprocess.run(
            ["git", "log", f"--since={days}.days", "--format=", "--name-only"],
            capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {}
    counts: dict[str, int] = defaultdict(int)
    for line in out.split("\n"):
        line = line.strip()
        if line:
            counts[line] += 1
    return counts


def scan(path: str, churn: dict[str, int]) -> tuple[list[dict], dict | None]:
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return [], None
    rust = path.endswith(".rs")
    segments = [(0, text)]
    if path.endswith(".svelte"):
        segments = [(m.start(1), m.group(1)) for m in SCRIPT_BLOCK.finditer(text)]
    pattern = RUST_FN if rust else JS_FN

    rows = []
    for offset, seg in segments:
        masked = mask_code(seg, rust)
        for m in pattern.finditer(masked):
            name = next((g for g in m.groups() if g), "<anon>")
            span = body_span(masked, m.start())
            if not span:
                continue
            open_at, close_at = span
            body = masked[open_at:close_at + 1]
            start_line = text.count("\n", 0, offset + m.start()) + 1
            end_line = text.count("\n", 0, offset + close_at) + 1
            met = metrics(body)
            lines = end_line - start_line + 1
            met.update({
                "file": path, "fn": name, "start": start_line, "end": end_line,
                "lines": lines, "params": params_of(masked, m.start(), open_at),
            })
            rows.append(met)

    c = churn.get(path, 0)
    for r in rows:
        raw = (r["lines"] / 40 + r["nesting"] + r["branches"] / 8
               + r["arms"] / 25 + r["params"] / 4)
        r["churn"] = c
        r["score"] = round(raw * math.log1p(c + 1), 2)

    total = text.count("\n") + 1
    file_row = {
        "file": path, "lines": total, "fns": len(rows), "churn": c,
        "score": round((total / 400) * math.log1p(c + 1), 2),
    }
    return rows, file_row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top-fns", type=int, default=150)
    ap.add_argument("--top-files", type=int, default=60)
    ap.add_argument("--churn-days", type=int, default=90)
    args = ap.parse_args()

    files = [ln.strip() for ln in sys.stdin if ln.strip()]
    churn = churn_map(args.churn_days)

    fn_rows, file_rows = [], []
    for f in files:
        rows, frow = scan(f, churn)
        fn_rows.extend(rows)
        if frow:
            file_rows.append(frow)

    fn_rows.sort(key=lambda r: r["score"], reverse=True)
    file_rows.sort(key=lambda r: r["score"], reverse=True)

    print("kind\tfile\tname\tstart\tend\tlines\tnesting\tbranches\tarms"
          "\tparams\tchurn90\tscore")
    for r in fn_rows[:args.top_fns]:
        print(f"fn\t{r['file']}\t{r['fn']}\t{r['start']}\t{r['end']}\t"
              f"{r['lines']}\t{r['nesting']}\t{r['branches']}\t{r['arms']}\t"
              f"{r['params']}\t{r['churn']}\t{r['score']}")
    for r in file_rows[:args.top_files]:
        print(f"file\t{r['file']}\t-\t1\t{r['lines']}\t{r['lines']}\t-\t-\t-"
              f"\t{r['fns']}\t{r['churn']}\t{r['score']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
