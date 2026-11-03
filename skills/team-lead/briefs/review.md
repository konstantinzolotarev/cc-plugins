# Brief: review — <one-line change name>

Six blocks, this order, none skipped. The reviewer has not seen the implementation brief and must
not be given the lead's or the implementer's opinion of the change.

## Goal

<What the change claims to do, in one paragraph taken from the acceptance criteria, not from the
implementer's report. Where the diff is: the worktree path and the base commit, or the PR number.>

## Ruled out

<Findings already known and decided: deferred to backlog with the issue number, or rejected with
the reason. The reviewer does not re-report these.>

## Read first

<The diff first. Then the tests that pin the changed behavior, the design doc section, and the
project's conventions file.>

## Scope

- In: correctness, the project's own conventions, missing tests for changed behavior
- Out: style preferences not written down anywhere, rewrites, scope creep
- Run: <the repo's gate, so findings about the build are facts, not guesses>

## Rules

<The Rules block from the workspace file, verbatim.>

## Report

Send the lead one message with, in this order:

1. Findings ranked most severe first. Each: `file:line`, one sentence stating the defect, and a
   concrete failure scenario (inputs or state, then the wrong outcome). No finding without a
   scenario.
2. If there are none: "nothing found", followed by the list of what was checked.
3. Gate output tail.

Do not fix anything. Do not praise. Do not pad with nits unless asked for them.
