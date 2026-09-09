#!/usr/bin/env python3
"""Read the project's shard map out of .claude/audit/shards.md.

The shard map is a document a human maintains — the globs are only half of it,
the "read first" and "hazards" lines beside them are the part that makes an
agent's findings worth reading. So it stays Markdown, and this parses the
mechanical half back out rather than asking the model to retype globs into a
shell command each run.

Expected shape (anything else in the file is ignored):

    ### 1 · `proxy` — the transform pipeline
    ```
    crates/never_engine/src/proxy/  crates/never_engine/src/proxy_state.rs
    ```
    Read first: ...

A shard is any `###` heading followed by a fenced block before the next
heading. Sections from `## Global agents` onward are prose for the agents and
hold no shards.

Usage:
  shards.py list [<shards.md>]             shard names, in file order
  shards.py globs <name> [<shards.md>]     that shard's git pathspecs
  shards.py coverage <signal-dir> [<md>]   lane files no shard glob matches
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

HEADING = re.compile(r"^###\s+(?:\d+\s*[.)·\-]\s*)?`?([A-Za-z0-9_.\-]+)`?")
BRACE = re.compile(r"\{([^{}]*)\}")
SECTION = re.compile(r"^##\s+(.*)")
FENCE = re.compile(r"^\s*```")
# Everything from these sections on is agent briefing, not shard definitions.
STOP_SECTIONS = ("global agents", "non-findings", "extra signals", "appendix")


def repo_root() -> pathlib.Path:
    out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True, check=True)
    return pathlib.Path(out.stdout.strip())


def default_map(root: pathlib.Path) -> pathlib.Path:
    return root / ".claude" / "audit" / "shards.md"


def tokenize(block: str) -> list[str]:
    """Split a fenced glob block into patterns.

    Whitespace inside a brace group is dropped rather than treated as a
    separator: a shard map wraps a long group across lines, and splitting it
    there would leave two halves that each match nothing.
    """
    depth, out, cur = 0, [], []
    for ch in block:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth = max(0, depth - 1)
        if ch.isspace():
            if depth:
                continue
            if cur:
                out.append("".join(cur))
                cur = []
            continue
        cur.append(ch)
    if cur:
        out.append("".join(cur))
    return out


def expand(pattern: str) -> list[str]:
    """Brace-expand one glob: `src/{a,b}.rs` → `src/a.rs`, `src/b.rs`.

    A shard map is written for a human, and a human writes the six files of a
    module as one braced group. git pathspecs have no braces, so an unexpanded
    group matches nothing at all — silently, which is the worst way for a
    shard to end up empty.
    """
    match = BRACE.search(pattern)
    if not match:
        return [pattern]
    out: list[str] = []
    for alt in match.group(1).split(","):
        out.extend(expand(pattern[: match.start()] + alt.strip() + pattern[match.end():]))
    return out


def parse(path: pathlib.Path) -> list[tuple[str, list[str]]]:
    if not path.is_file():
        raise SystemExit(f"shards: no shard map at {path} — run /audit --init")
    shards: list[tuple[str, list[str]]] = []
    name: str | None = None
    block: list[str] = []
    in_fence = False
    stopped = False

    for line in path.read_text().splitlines():
        section = SECTION.match(line)
        if section and not line.startswith("###"):
            stopped = section.group(1).strip().lower().startswith(STOP_SECTIONS)
            continue
        if stopped:
            continue
        if FENCE.match(line):
            # A shard's globs are the FIRST fenced block after its heading;
            # later blocks under the same heading are examples, not pathspecs.
            in_fence = not in_fence
            if not in_fence and name and block:
                globs: list[str] = []
                for token in tokenize("\n".join(block)):
                    globs.extend(expand(token))
                shards.append((name, globs))
                name, block = None, []
            continue
        if in_fence:
            if name:
                block.append(line)
            continue
        heading = HEADING.match(line)
        if heading:
            name, block = heading.group(1), []
    return shards


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    cmd = argv[1]
    root = repo_root()

    if cmd == "list":
        path = pathlib.Path(argv[2]) if len(argv) > 2 else default_map(root)
        for name, _ in parse(path):
            print(name)
        return 0

    if cmd == "globs":
        want = argv[2]
        path = pathlib.Path(argv[3]) if len(argv) > 3 else default_map(root)
        for name, globs in parse(path):
            if name == want:
                for glob in globs:
                    print(glob)
                return 0
        raise SystemExit(f"shards: no shard named '{want}' in {path}")

    if cmd == "coverage":
        sig = pathlib.Path(argv[2])
        path = pathlib.Path(argv[3]) if len(argv) > 3 else default_map(root)
        listed: set[str] = set()
        for lane_file in sorted(sig.glob("files.*")):
            listed.update(lane_file.read_text().split())

        covered: set[str] = set()
        for _, globs in parse(path):
            out = subprocess.run(["git", "ls-files", "--", *globs],
                                 capture_output=True, text=True, cwd=root)
            covered.update(out.stdout.split())

        uncovered = sorted(listed - covered)
        (sig / "uncovered.txt").write_text("".join(f"{f}\n" for f in uncovered))
        print(f"  uncovered.txt: {len(uncovered)} of {len(listed)} lane files "
              f"match no shard glob")
        return 0

    print(f"shards: unknown command: {cmd}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
