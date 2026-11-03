# Brief: implement — <one-line job name>

Six blocks, this order, none skipped. The peer has no other context.

## Goal

<One paragraph. The outcome, not the steps. Name the repo and the branch or worktree to work in,
which the lead created or names here. "Done" means the Scope's acceptance check passes.>

## Ruled out

<What the lead already knows does not work, is out of bounds, or was decided otherwise. One line
each, with the reason, so the peer does not rediscover it. "Nothing" is a valid entry.>

## Read first

<Files and docs by path, in the order to read them. No retyped content. Include the design doc
section, the test that pins current behavior, and the nearest existing example of the pattern.>

## Scope

- In: <files or areas expected to change>
- Out: <what must not change, even if it looks related; propose it in the report instead>
- Acceptance: <the exact command, usually the repo's gate, and the result expected>

## Rules

<The Rules block from the workspace file, verbatim.>

## Report

Send the lead one message with, in this order:

1. Changed files, one line each with what changed.
2. The acceptance command's output tail, including the test count.
3. What was left out and why, one line each. "Nothing" if complete.
4. Open questions or proposals for things outside the Scope, one line each.

Do not summarize the diff in prose; the lead reads the diff in the worktree.
