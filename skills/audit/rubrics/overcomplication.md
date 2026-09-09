# Check: logic that got complicated by accretion

**The question.** Would someone implementing this *today*, knowing everything
the code now has to handle, write it this way? If not, what did it accumulate,
and can the accumulation be removed without losing a behaviour?

This is the check no tool can do and the reason the audit exists. Feature
after feature lands on the same function; each addition is locally reasonable;
the result is a shape nobody would choose. That shape is invisible in a diff —
only a whole-file read finds it.

## What counts

- **A flag that became a state machine.** Three or four booleans whose valid
  combinations are fewer than 2ⁿ, tracked separately. If the project models
  states as enums or unions elsewhere, a boolean cluster is drift from that.
- **A condition nobody can evaluate.** A branch guard that needs four facts
  from three modules to decide. Findable by reading the guard aloud.
- **Special cases that are no longer special.** A branch added for one caller,
  one page, one customer — where the general path now handles it.
- **Layered guards that re-check the same thing.** The caller checks, the
  dispatcher checks, the executor checks. One of them owns it; the others are
  cargo.
- **A function doing three jobs** where the seam is obvious and mechanical —
  the parse, the decision and the I/O in one body, when the pure part could
  move somewhere testable.
- **Dead conditionals**: a branch whose guard cannot be true any more because
  an upstream change made it unreachable. High value, easy to miss, and the
  complexity signal will not point at it — only reading does.

## What does not count

- **Long but flat.** A 900-line dispatch table, a big match over variants, a
  catalogue. Length is not complexity; nesting, branch density and coupling
  are. Expect the largest such file to top the metric ranking and to be fine —
  say something more useful about it than "it is large", or say nothing.
- **Complexity that pays for an invariant.** Ordering rules, retry policies,
  concurrency fixes, cache-coherency dances. Each looks like it could be
  simpler and each may be load-bearing. **Before proposing to simplify one,
  find the doc comment, plan file or test that explains it.** If you can't
  find one, that's a *documentation* finding, not a simplification.
- **Generated or mirrored code.**
- "Extract a helper" for something used once.
- Anything the project's Non-findings section already rules out.

## Evidence required

1. `path:start-end` for the function, plus its metrics row from
   `complexity.tsv` (lines / nesting / branches / arms / churn90).
2. **The accretion story.** What was added over time — from `git log -L` on
   the function, or the plan files and PRs that touched it. A finding that can
   name the three features that landed on one function is credible; one that
   just says "this is complex" is not.
3. **What breaks if you touch it.** Which tests cover it, which invariants it
   carries, what has to keep working.
4. **A concrete first step**, not a redesign. "Lift the cooldown branch into
   its own function and give it the two tests that exist" beats "refactor into
   a state machine" every time. If the only honest proposal is a rewrite, the
   finding is tier `Noted`, not `Act now`.

## Reading the signal

`complexity.tsv` scores `(lines/40 + nesting + branches/8 + arms/25 +
params/4) × log1p(churn90)`. **Churn is the discriminator.** A gnarly function
untouched in a year is not where the risk is; a gnarly function that changed
eleven times last quarter is still absorbing features and will keep doing it.

Rows with `kind=file` are file-level rollups — useful for spotting a module
that has outgrown its file even when no single function is an outlier.
