# Check: drift from the project's own conventions

**The question.** Does this code look like the rest of this codebase, and does
it hold the rules the project decided on?

**The hard gate, and the reason this check is worth running at all: a finding
must quote a rule the project wrote down.** Generic language dogma is out of
scope. "Prefer composition over inheritance", "this should use a builder",
"add doc comments" — none of these are findings unless this project said so
somewhere you can cite.

Where a written rule legitimately lives:

- `CLAUDE.md` / `AGENTS.md` / `CONTRIBUTING.md` / a style doc
- a module-level doc comment that states a decision
- the shard map's *Read first* line for this area
- a plan file, ADR, or PR description that decided it
- a lint config the project maintains (a rule set someone chose)

**If the repo has no written conventions at all, this check reports exactly
that and stops.** A conventions section full of invented rules is worse than
an empty one: it trains the reader to skip the report.

## What counts

- **Boundary violations.** A layering rule the project holds — pure core with
  no I/O, adapters with no business logic, a bundle that must not import the
  app, a package that must not depend upward. These are the highest-value
  findings in the check because they compile fine and rot silently.
- **Idiom the project settled on** and this code departs from: how errors are
  returned, how logging is done, how state is modelled, where a constructor
  lives, which shared widget every instance of a control must use.
- **A convention nobody decided.** One lint firing 50+ times inside one module
  is a de-facto local style that was never argued for. Either the module
  should change or the lint should be silenced at module level with a reason —
  both are findings; pick one and argue it.
- **Hygiene**: a suppression with no comment above it (`allow_census.tsv`,
  `justified = no`) is a lint someone silenced rather than answered. Anything
  at `level = error` in `lint.tsv` is a finding on its own.

## What does not count

- Formatting. The formatter owns it.
- Style preferences the codebase consistently rejects. **If 200 sites do it
  one way, that *is* the convention** — a rubric disagreeing with the codebase
  is the thing that's wrong.
- Pedantic lints on test code.
- Renaming for taste; documentation you'd like to exist on private helpers.
- Accessibility, i18n or performance work the project hasn't scoped.
- Anything the project's Non-findings section already rules out.

## How to use the lint tables

**Do not list rows.** A pedantic run over a large repo emits thousands, the
owner can run the linter themselves, and a report full of low-value rule hits
is a report nobody reads.

Read `lint_by_rule.tsv` for **shape**:

- One rule, one module, 50+ hits → a convention nobody decided. Finding.
- A rule firing 2–3 times across the repo → noise. Skip it.
- `level = error`, or a rule that maps to a real bug class (lock held across
  an await, a mutable key type, an unhandled promise) → report individually,
  with the row.

`lint.tsv` may be absent entirely — that means the signal was not collected
(`--quick`, or no lint command configured). Absent is not clean; say which.

## Evidence required

1. `path:line`, and the rule or convention violated, named exactly.
2. For a cluster finding: the count and the module, from `lint_by_rule.tsv`.
3. **The project rule, quoted, with its source file.** A style finding with no
   project rule behind it is personal taste and gets rejected at verification.
