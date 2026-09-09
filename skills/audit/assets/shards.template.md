# Shard map — <PROJECT>

Derived at `<COMMIT>` by `/audit --init`. **Hand-edited since** — this file is
where the audit's knowledge of this repo accumulates, and every edit makes the
next audit better. `TODO(verify)` marks something the bootstrap inferred
rather than read; confirm or delete each one.

Boundaries are **architectural, not size-based**: two files that have to land
in the same agent's head belong in the same shard, however large that makes
it. Globs are git pathspecs, brace-expanded (`src/{a,b}.ts` works, and may
wrap across lines).

---

## Shards

### 1 · `<name>` — <what this area is>

```
<git pathspecs, whitespace-separated>
```

Read first: <the invariants that bind this area — module docs, a plan file,
the section of CLAUDE.md that governs it. Name files, not topics.>
Hazards: <what looks like a finding here but isn't, and why. The repetition
that is deliberate, the file that will top the complexity ranking, the symbol
reached from a string.>

### 2 · `<name>` — …

<!-- Repeat. Target ~20–40 files or ~25k lines per shard, 3–12 shards total.
     `signals.sh` reports files matching no shard glob in uncovered.txt —
     that number should be 0, or every exception should be deliberate. -->

---

## Global agents

Run alongside the shards; their subject is cross-area by definition and no
single shard can see it.

- **`cross-area-duplication`** — reads the whole `clones_*.tsv` plus
  `symbols.tsv` / `exports.tsv`, looking only at groups whose spans cross
  shard boundaries, and at same-idea-different-name pairs the clone index
  cannot catch.
- <one per `extra_signals` entry that declares an `agent`; brief it below.>

## Extra signals

<For each script in config.json's `extra_signals`: what it checks, what its
tables mean, and which column being blank is the actual finding. Delete this
section if the project has none.>

## Non-findings

The project's standing rejections. Every entry here is something an agent will
otherwise report every single run, so each one saves an audit's worth of
verifier time. Add to it whenever a finding is rejected as "that's deliberate".

- <the repetition that is deliberate, and where the reasoning is written down>
- <the sanctioned exception to a rule, and the comment that sanctions it>
- <a finding already closed by a compile-time or test-time check>
