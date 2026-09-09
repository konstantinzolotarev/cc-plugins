---
name: audit
description: Standing health audit of a whole codebase — duplication that should be unified, logic that got complicated by accretion, dead code, and drift from the project's own conventions. Mechanical signal pass first, then sharded subagents, then verification, then a ranked report. Use when the user asks to audit / review / health-check the project, to find dead or duplicated code, or to look for things worth simplifying across the codebase. NOT for reviewing a diff, a branch, or a PR — that is /code-review and /simplify.
---

# Whole-codebase audit

Diff-scoped review tools all review **a change**. This reviews **what is
already merged** — the drift no single PR introduced, so no diff review could
ever have seen it.

Four checks, whole repo:

| check | rubric | finds |
|---|---|---|
| duplication | `rubrics/duplication.md` | the same decision made twice |
| overcomplication | `rubrics/overcomplication.md` | logic that accreted feature by feature |
| dead code | `rubrics/dead-code.md` | unreachable in every build |
| conventions | `rubrics/conventions.md` | drift from the project's own written rules |

**It never edits code.** The deliverable is a report; the user decides what
becomes a plan. Do not commit the report unless asked.

Languages: Rust and TypeScript/JavaScript (incl. Svelte/Vue). Other languages
still get the language-agnostic signals (clones, churn, complexity, git), and
`summary.txt` names what could not be collected.

## Where things live

- **This skill** — the engine. Rubrics and scripts under its own directory;
  refer to them by the base directory given when the skill was invoked.
- **The repo** — `.claude/audit/config.json` (machine config, a delta over
  `assets/defaults.json`) and `.claude/audit/shards.md` (the shard map, the
  per-area invariants, the Non-findings list). Both are hand-edited and both
  are where this audit's knowledge of *this* repo accumulates.

## Arguments

| form | meaning |
|---|---|
| `/audit` | full sweep (see Phase 1 for the agent count) |
| `/audit <shard>` | one shard, patched into today's report |
| `/audit --init` | bootstrap `.claude/audit/` for a repo that has none |
| `/audit --signals-only` | Phase 0 only, no agents |
| `/audit --quick` | full sweep on a `--quick` signal pack (no lint build) |
| `/audit --deep` | promote the shard agents to the stronger model |

If the user asks for something narrower than a shard, map it to the nearest
shard and say which one you picked.

---

## Phase 0 — signals

```bash
bash <skill>/scripts/signals.sh --out "$SCRATCH/audit-signals"
```

`$SCRATCH` = the session scratchpad. Add `--quick` to skip the lint builds
(~30 s instead of minutes), which drops `lint.tsv` and the web check, so the
conventions check runs on reading alone.

Read `summary.txt` and report the counts before fanning out — including its
**signals NOT collected** list, which the report has to carry so a reader
never mistakes an uncollected signal for a clean one. If the pack looks wrong
(zero symbols, zero clones), stop and fix the pack; every downstream agent
depends on it.

Outputs, TSV with a header row unless noted:

```
files.<lane>                 the file lists the shards are cut from
symbols.tsv  …_candidates    every public Rust item + reference counts
exports.tsv  …_candidates    same for JS/TS exports
clones_<lane>.tsv            clone groups, exact + structural
complexity.tsv               per-fn metrics x churn, top 150 + file rollup
allow_census.tsv             suppression sites, justified or not
lint.tsv lint_by_rule.tsv    linter rows + per-rule rollup
deps.txt  web_check.txt      unused deps, type-check output
uncovered.txt                lane files matching no shard glob
<project tables>             whatever config.json's extra_signals produced
summary.txt                  counts, lanes, and what was skipped
```

**`uncovered.txt` is a finding in its own right** — files no agent will read
because no shard claims them. Report the count; if it is large, say so before
fanning out, because the sweep is that much less complete.

## Phase 1 — fan out

All agents in **one message** so they run concurrently:

```
N shard agents  (from shards.md, on the cheaper model; --deep promotes them)
1 cross-area-duplication agent   (stronger model)
1 agent per extra_signals entry declaring an `agent`
2 verifier agents                (Phase 2)
```

Pre-filter the pack per shard first — without it every agent reads thousands
of lint rows and symbols:

```bash
bash <skill>/scripts/slice.sh "$SCRATCH/audit-signals" <shard>
```

`slice.sh` reads the shard's globs out of `shards.md` itself, so a brief and
its slice cannot disagree. Get the shard list with
`python3 <skill>/scripts/shards.py list`.

Give each shard agent exactly this, filled in:

> You are auditing the **`<shard>`** area of `<project>`. Read-only: do not
> edit any file.
>
> **Your files:** `<globs from shards.md>`
> **Signal pack:** `<SCRATCH>/audit-signals/` — the rows for your files are
> pre-filtered into `<SCRATCH>/audit-signals/shards/<shard>/`.
> **Rubrics — follow them exactly, including the "what does not count"
> sections:** `<skill>/rubrics/{duplication,overcomplication,dead-code,conventions}.md`
> **Invariants that bind this area:** `<the "Read first" and "Hazards" lines
> from shards.md>`, plus the project rules they point at.
> **Standing rejections — do not re-report these:** `<the Non-findings section
> of shards.md, verbatim>`
>
> Work in this order: read the signals for your files, then read the code the
> signals point at, then look for what the signals cannot see (the
> overcomplication and semantic-duplication rubrics are mostly the latter).
>
> **Report at most 8 findings.** If you have more, report the 8 with the best
> payoff÷risk and give the count of the rest. Rank them yourself.
> **Every finding needs the evidence its rubric demands** — spans you actually
> read, greps you actually ran. A finding without evidence is worse than no
> finding, because it costs the verifier a full investigation to reject.
>
> Return JSON only, no prose:
> ```json
> {"shard": "...", "reviewed_files": 0, "tail_count": 0, "findings": [
>   {"check": "duplication|overcomplication|dead-code|conventions",
>    "title": "one line, specific",
>    "spans": ["path:start-end"],
>    "evidence": "what you read/ran that proves it",
>    "why": "the change that must touch both / what breaks / why it's dead",
>    "proposal": "the concrete first step",
>    "effort": "S|M|L", "risk": "low|medium|high", "confidence": "high|medium|low"}
> ]}
> ```

The global agents get their brief from `shards.md`'s **Global agents** and
**Extra signals** sections, the whole (unfiltered) pack, and the same schema
and cap.

## Phase 2 — verify

Pool the findings, drop exact duplicates (same check + overlapping spans),
then two verifier agents on the stronger model, batched **by check** because
the technique is per-check:

- **verifier A** — dead code + duplication. Re-run the four reachability greps
  for every dead-code claim (manifest, table, string, conditional build); read
  both spans in full for every duplication claim and decide whether one change
  really must touch both.
- **verifier B** — overcomplication + conventions. Re-measure the metric; find
  the doc comment or plan file that explains the complexity (if one exists,
  the finding is usually wrong); for conventions, confirm the rule is the
  project's, quoted, not generic dogma.

Each returns `CONFIRMED` / `PLAUSIBLE` / `REJECTED` per finding with one line
of reasoning. Rejected findings leave the report but are **counted per shard**
in the appendix — a shard rejecting 80% is a broken rubric or a stale
Non-findings list, and the user should see that immediately.

## Phase 3 — rank and write

Tiers, by payoff ÷ risk:

- **Act now** — high payoff, contained blast radius, `CONFIRMED`.
- **Worth doing** — real, but needs a plan first.
- **Noted** — true, not worth touching yet. One line each, no elaboration.

Read the most recent report in `report_dir` first and carry unresolved
findings forward under **Carried over**, with the date first seen. Give every
finding a stable id — `sha1(check + file + symbol)[:8]` — so it survives line
drift.

Write `<report_dir>/YYYY-MM-DD-audit.md`:

```markdown
# <Project> — Codebase Audit

**Date** · **Commit** · **Scope** (shards, agents, signal pack, what was skipped)

## 1. Executive summary            ≤200 words, health verdict first
## 2. Headline findings            table: # | finding | tier | check | shard
## 3. Duplication
## 4. Overcomplication
## 5. Dead code
## 6. Conventions
## 7. Carried over                 open findings from prior audits, with dates
## 8. Calibration                  per-shard confirmed/rejected counts
## 9. Signal pack                  raw counts, so a later run can compare
```

Each finding: `**[id] Title** · tier · spans · evidence · why · proposal ·
effort/risk`. Tone: concrete, ranked, no hedging, no praise padding. Every
finding names spans you actually read. Never "consider possibly".

Then tell the user, in the terminal: the tier counts, the three findings you'd
act on first, and the rejection rate. Nothing else — the report is the
artifact.

## `--init` — bootstrap a repo

For a repo with no `.claude/audit/`. In order:

1. Run `signals.sh --quick --out "$SCRATCH/audit-signals"`. **First**, so the
   shard map is cut against real file lists, line counts and the clone index
   rather than a guess at the tree.
2. Read what the repo has written down: `CLAUDE.md` / `AGENTS.md` /
   `README` / `CONTRIBUTING`, any ADR or plans directory, the build files.
3. Write `.claude/audit/config.json` — **only the delta** over
   `assets/defaults.json`. Lanes and lint commands are detected; most repos
   need nothing but `exclude_paths`. Read that file's header before adding a
   key, especially the two exclude mechanisms: **a pattern with a wildcard
   belongs in `exclude_re`, never in `exclude_paths`**, because git matches a
   wildcard `:(exclude)` pathspec by extension alone.
4. Write `.claude/audit/shards.md` from `assets/shards.template.md`. Sizing:
   ~20–40 files or ~25k lines per shard, 3–12 shards, boundaries
   architectural. Mark every inferred invariant `TODO(verify)`.
5. Re-run `shards.py coverage` and iterate until `uncovered.txt` is empty or
   every exception is deliberate.
6. Report: the shards, the `TODO(verify)` count — which is the honest measure
   of how much this repo documents itself — and what to review first.

Do not run the full sweep in the same turn. The map is worth a human read
before fifteen agents act on it.

## Re-runs

`/audit <shard>` re-runs one shard against a fresh signal pack and patches
that section of the day's report in place. Use it after fixing something, to
confirm the finding is gone rather than re-reading the whole repo.

## Cost

`N + 3 + extras` agents plus one lint build. This is a periodic audit —
monthly, or before a release — not something to run per branch. `--quick`
halves the wall clock; `/audit <shard>` costs a fraction.
