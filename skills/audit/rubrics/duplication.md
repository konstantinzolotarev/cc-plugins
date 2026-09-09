# Check: duplication that should be unified

**The question.** Is the same *decision* made in two places, such that changing
one and forgetting the other is a bug waiting to happen?

Not "do these lines look alike". Similar-looking code that encodes two
independent decisions is fine, and unifying it creates coupling that later has
to be undone. The test is: **if a rule changes, must both sites change
together?** If yes, that's the finding. If no, leave it.

## What counts

- The same constant, threshold, endpoint, timeout, or wire format written
  twice — the highest-value class, because the two copies silently diverge.
- Two implementations of the same parse / format / normalize / convert step.
- The same multi-step sequence written out where a shared helper already
  exists and was missed.
- A helper implemented once per language — the same rounding, the same
  validation, the same date math in the backend and again in the frontend.
  That pair drifts across a boundary where no compiler looks.
- Copy-pasted blocks that have already partially diverged. The divergence is
  the evidence: one copy got a fix and the other didn't.

## What does not count

- **Parallel-by-design plumbing.** Registration functions, dispatch arms,
  adapter methods, per-feature config wiring — code that is parallel because
  the architecture made it parallel. Collapsing it behind a trait, a macro or
  a base class makes every instance harder to read and hides the per-instance
  differences that are the whole point.
- **Data.** Long lists of near-identical rows are a catalogue, not logic.
  Adding a row is meant to be a row.
- **Tests.** Repetitive setup is how tests stay readable.
- Anything under 8 lines that isn't a constant or a wire format.
- **Anything the project's Non-findings section already rules out.** Read it
  before you write a finding: a repetition the project deliberately chose, and
  wrote down why, is a rejected finding, not a new one.

## Evidence required

Every finding carries:

1. **At least two spans** as `path:start-end`, read in full — not the clone
   index's word for it.
2. **What differs** between the copies, explicitly. "Identical except the
   timeout" is a much stronger finding than "identical".
3. **The change that would have to touch both.** Name a concrete edit — a
   protocol change, a new field, a fixed bug — that must land in every copy.
4. **The unification you propose, and where it should live.** If the right
   home would violate a boundary the project holds (a purity rule, a crate or
   package layering, a bundle that must not import the app), say so and drop
   the finding.

## Reading the signal

`clones_<lane>.tsv` has two modes:

- `exact` — comments and whitespace normalized, identifiers kept. Copy-paste.
  High confidence; go straight to reading the spans.
- `structural` — identifiers and literals collapsed. Same *shape*, different
  names. Mostly noise (match arms, builder chains, prop declarations) but this
  is the only mode that finds "these two modules are the same state machine".
  Expect to reject most of it; the few survivors are the best findings in the
  check.

Sorted by `lines × occurrences`. A 20-line group appearing twice generally
beats an 8-line group appearing nine times — the latter is usually shape.
