#!/usr/bin/env python3
"""Resolve the audit config: skill defaults + repo detection + project delta.

The bash passes call this instead of hardcoding globs, excludes and toolchain
commands, so one skill audits every repo and a project's own file only carries
what is genuinely different about it.

Resolution order, later wins:

  1. <skill>/assets/defaults.json
  2. detection — a lane turns on when its `detect` file exists at the repo
     root, and the web lane's lint command is read off package.json's scripts
  3. <repo>/.claude/audit/config.json   (deep-merged; lists REPLACE)

Dicts merge key by key; lists replace wholesale. A project overriding
`exclude` therefore owns the whole list — which is the behaviour you want,
because half the point of overriding it is to drop a default that is wrong
for this repo.

Usage (all commands print to stdout, one item per line where plural):

  cfg.py root                     repo root
  cfg.py show                     merged config as JSON
  cfg.py lanes                    active lane names
  cfg.py get <dotted.path>        one scalar, empty line if absent
  cfg.py list <dotted.path>       list items
  cfg.py pathspecs <lane>         git pathspecs for that lane's own files
  cfg.py exclude-re <lane>        ERE to grep -v out of that lane's file list
  cfg.py refspecs                 pathspecs for the symbol reference pass
  cfg.py codegenspecs             pathspecs for the non-source reference pass
  cfg.py testspecs                pathspecs for the test-reference pass
  cfg.py extra-signals            extra signal script paths
  cfg.py extra-tables <mode>      extra tables with slice mode whole|path
  cfg.py extra-agents             extra-signal agent names
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

SKILL_DIR = pathlib.Path(__file__).resolve().parent.parent
DEFAULTS = SKILL_DIR / "assets" / "defaults.json"
PROJECT_REL = pathlib.Path(".claude") / "audit" / "config.json"


def repo_root() -> pathlib.Path:
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, check=True,
    )
    return pathlib.Path(out.stdout.strip())


def load_json(path: pathlib.Path) -> dict:
    with path.open() as fh:
        data = json.load(fh)
    # `_comment` keys document the schema in-file; they are not config.
    return {k: v for k, v in data.items() if not k.startswith("_")}


def deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for key, value in over.items():
        if key.startswith("_"):
            continue
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def detect_web_lint(root: pathlib.Path) -> str | None:
    """The type-check command a JS/TS repo already has.

    Preference order is by how much it tells us: a `check` script is what the
    project itself runs in CI, `tsc --noEmit` is the fallback that at least
    type-checks. A lint-only script is NOT used — style output duplicates what
    the conventions check reads from the code, and drowns the signal.
    """
    pkg = root / "package.json"
    if not pkg.is_file():
        return None
    try:
        data = json.loads(pkg.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    scripts = data.get("scripts") or {}
    for name in ("check", "type-check", "typecheck", "tsc"):
        if name in scripts:
            return f"npm run {name}"
    deps = {**(data.get("devDependencies") or {}), **(data.get("dependencies") or {})}
    if "typescript" in deps:
        return "npx --no-install tsc --noEmit"
    return None


def resolve(root: pathlib.Path) -> dict:
    cfg = load_json(DEFAULTS)
    project = root / PROJECT_REL
    if project.is_file():
        cfg = deep_merge(cfg, load_json(project))

    for name, lane in (cfg.get("lanes") or {}).items():
        if "enabled" not in lane:
            detect = lane.get("detect")
            lane["enabled"] = bool(detect) and (root / detect).exists()
        if name == "web" and lane.get("enabled") and not (lane.get("lint") or {}).get("cmd"):
            lane.setdefault("lint", {})["cmd"] = detect_web_lint(root)
    return cfg


def dotted(cfg: dict, path: str):
    node = cfg
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def excludes(cfg: dict) -> list[str]:
    """`:(exclude)` pathspecs for foreign code.

    Only literal directory prefixes belong here — git matches a WILDCARD
    exclude pathspec by extension alone, so `:(exclude)*.d.ts` would drop
    every `.ts` file in the repo. Patterns go through exclude_re instead.
    """
    bad = [p for p in cfg.get("exclude_paths", []) if any(c in p for c in "*?[")]
    if bad:
        raise SystemExit(
            "cfg: exclude_paths must be literal directory prefixes, no "
            f"wildcards (git matches those by extension): {bad}. "
            "Move the pattern to exclude_re."
        )
    return [f":(exclude){p}" for p in cfg.get("exclude_paths", [])]


def lane(cfg: dict, name: str) -> dict:
    found = (cfg.get("lanes") or {}).get(name)
    if not found:
        raise SystemExit(f"cfg: no such lane: {name}")
    return found


def lane_pathspecs(cfg: dict, name: str) -> list[str]:
    return [*lane(cfg, name).get("include", []), *excludes(cfg)]


def lane_exclude_re(cfg: dict, name: str) -> str:
    parts = [p for p in (cfg.get("exclude_re"), lane(cfg, name).get("exclude_re")) if p]
    return "|".join(parts)


def emit(items) -> None:
    for item in items:
        print(item)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    cmd, args = argv[1], argv[2:]
    root = repo_root()
    if cmd == "root":
        print(root)
        return 0

    cfg = resolve(root)
    lanes = cfg.get("lanes") or {}
    extras = cfg.get("extra_signals") or []

    if cmd == "show":
        print(json.dumps(cfg, indent=2))
    elif cmd == "lanes":
        emit(n for n, lane in lanes.items() if lane.get("enabled"))
    elif cmd == "get":
        value = dotted(cfg, args[0])
        print("" if value is None else value)
    elif cmd == "list":
        value = dotted(cfg, args[0])
        emit(value or [])
    elif cmd == "pathspecs":
        emit(lane_pathspecs(cfg, args[0]))
    elif cmd == "exclude-re":
        print(lane_exclude_re(cfg, args[0]))
    elif cmd == "refspecs":
        emit([*cfg["symbols"]["reference_paths"], *excludes(cfg)])
    elif cmd == "codegenspecs":
        emit([*cfg["symbols"]["codegen_paths"], *excludes(cfg)])
    elif cmd == "testspecs":
        emit([*cfg["symbols"]["test_paths"], *excludes(cfg)])
    elif cmd == "extra-signals":
        emit(e["script"] for e in extras if e.get("script"))
    elif cmd == "extra-tables":
        mode = args[0]
        emit(t for e in extras if e.get("slice", "whole") == mode
             for t in e.get("tables", []))
    elif cmd == "extra-agents":
        emit(e["agent"] for e in extras if e.get("agent"))
    else:
        print(f"cfg: unknown command: {cmd}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
