# Check: dead code

**The question.** Is this reachable, from anything, in any build?

This is the check with the highest false-positive rate and the most expensive
false positives — deleting something load-bearing. The bar is proof, not
absence of evidence.

## The four ways code is reached without a direct reference

Check every one before claiming a symbol is dead. Most codebases have all four
in some form; the project's shard map names the specific ones.

1. **Manifest / config codegen.** A build script, a bundler plugin, or a
   virtual module that turns a `.toml` / `.json` / `.yaml` file into code. A
   name that appears only in a manifest is still wired.
2. **Table indirection.** A registry, a dispatch table, a command list, a
   route map. A function referenced only from a table entry looks unreferenced
   to a grep for its call.
3. **String references.** Injected or templated source, event names, settings
   keys, dynamic imports, reflection. Grep the *string*, not just the
   identifier.
4. **Conditional compilation / bundling.** Feature flags, `cfg` attributes,
   debug-only builds, per-platform files, tree-shaken entry points. Code that
   is dead in this build may be the entire point of another one.

A fifth, weaker path: a `pub` / exported item may be part of a deliberate API
surface consumed from outside this repo.

## What counts

- A public item with no reference anywhere, in any build, after all five
  checks.
- A private item the compiler already flags (`dead_code` rows in `lint.tsv`) —
  cheap and safe, but say so rather than padding the report with them.
- **Test-only production code**: a public function whose only callers are
  tests. Not automatically dead — a testing seam is legitimate — but worth
  naming when the seam has no comment saying it is one.
- A config or settings key that nothing reads. Usually a renamed setting whose
  default was left behind.
- An unused dependency (`deps.txt`).
- A whole module or file kept "for reference" — those belong in git history.

## What does not count

- Anything under a path the project excluded as vendored or foreign.
- Fixtures, test constants, and sample data.
- A public item an adapter or downstream package *should* be using — that is a
  wiring finding, not a deletion finding, and it reads completely differently.
- Feature-gated code for a feature that still exists.
- Deprecated-but-documented compatibility shims, if a comment says why.

## Evidence required

1. The `symbols_candidates.tsv` / `exports_candidates.tsv` row
   (`total / test / nontest / codegen`).
2. **The greps you actually ran**, quoted: the identifier across all file
   types, the string form, the manifest/table lookup, and the conditional-
   compilation search. A finding without these is rejected at verification.
3. Whether deleting it also deletes something else (its module, its tests, a
   trait or interface implementation).
4. The `codegen` column is a red flag, not a verdict: non-zero means the name
   appears in a non-source file, so a deletion claim needs to explain that hit.

## Known blind spots of the signal

Both produce **false negatives** (dead code that looks alive), never false
positives, so the candidate list is conservative and short:

- Common names (`new`, `run`, `state`, `init`) collide with unrelated tokens.
- Method names declared on a trait/interface count every implementation site
  as a reference.
- Inline test blocks are attributed to the `test` column by brace depth, which
  misses a test module written in an unusual shape.

Which means: **the candidate list is not the whole population**. If you notice
an obviously dead module the list missed, report it — with the same evidence.

`uncovered.txt`, when present, is a different kind of miss: files in the audit
lanes that no shard glob matches, so no agent read them at all. It is a
finding about the shard map, not about the code.
