---
name: multi-review
description: Run multiple code reviews (/simplify, coderabbit, codex), validate every finding against the real code, then auto-fix only the valid + safe ones and report the rest. Use when the user wants a thorough multi-tool review-and-fix pass before commit/merge, or says "multi review", "run all reviews", "review and fix".
---

# Multi-Review

Orchestrate several code reviewers, validate their findings, auto-fix the safe valid
ones, and report everything else. You (the main agent) own the orchestration and the
fix application; subagents only produce and validate findings.

**Core principle:** Reviewers report, the validator judges, the main agent fixes.
A finding is fixed automatically only if it is both *valid* and *safe to apply
mechanically*. Everything else is reported for the user to decide.

## Pipeline

```
1. RESOLVE SCOPE      → detect main branch, parse arg overrides
2. RUN /simplify      → self-applies quality fixes to the working tree first
3. FAN OUT (parallel) → coderabbit + codex review subagents → normalized findings
4. MERGE + DEDUPE     → collapse overlapping findings across tools
5. VALIDATE           → single subagent marks each valid|invalid|uncertain
6. AUTO-FIX           → apply only valid + fix_safe findings (serial)
6.5 VERIFY            → auto-detect & run build/test/lint
7. REPORT             → fixed / needs-decision / uncertain / dismissed / tool status
```

> ⚠️ This skill operates on **uncommitted working changes**. `/simplify` and the
> review CLIs critique local changes and `/simplify` edits files in place. There is
> no automatic stash — tell the user if the tree is dirty in unexpected ways.

## Step 1 — Resolve Scope

Detect the main branch:

```bash
git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/origin/@@'
# fallback: main, then master
```

Accept arg overrides:
- `--base <branch>` — base branch for the CLIs (default: detected main)
- `--verify "<cmd>"` — explicit verification command (overrides auto-detect)
- a tool name list to restrict reviewers (e.g. `coderabbit` only)

If there are no changes in scope, stop and report "nothing to review."

## Step 2 — Run /simplify

Invoke the `/simplify` skill (Skill tool). It reviews changed code for
reuse/simplification/efficiency and **applies fixes itself**. Its changes are trusted
and are NOT re-run through the validation pass — they go straight into the report's
"simplify" section. The CLIs in step 3 then review the already-simplified code.

## Step 3 — Fan Out Review CLIs (parallel subagents)

Dispatch one subagent per CLI **in parallel** (single message, multiple Task calls).
Each subagent runs its CLI, parses the output, normalizes findings, and returns ONLY
the structured result — keeping noisy CLI output out of the main context.

**CodeRabbit subagent** runs:
```bash
coderabbit review --agent --base <main>
```
`--agent` emits structured findings. Parse them into the schema below.

**Codex subagent** runs:
```bash
codex exec review --base <main>
```
Codex may fail (out of tokens, auth, rate limit). On failure the subagent returns
`status: "failed"` with a short `note` and an empty `findings` array — **never abort
the pipeline**.

Each review subagent returns:
```json
{
  "tool": "coderabbit",
  "status": "ok | failed",
  "note": "reason if failed, else empty",
  "findings": [ /* normalized findings, see schema */ ]
}
```

### Normalized finding schema

```json
{
  "id": "cr-1",
  "tool": "coderabbit",
  "file": "src/foo.rs",
  "line": "42",
  "severity": "critical | major | minor | nit",
  "category": "correctness | security | perf | style | other",
  "claim": "Off-by-one in loop bound skips the last element",
  "suggested_fix": "Change `< n` to `<= n`",
  "raw": "original tool snippet, for the report"
}
```

The subagent maps the tool's own severity labels onto the 4-level scale
(critical/major/minor/nit). `line` may be a range ("42-50") or null for file-level
findings.

## Step 4 — Merge + Dedupe

Collapse findings that are the **same file + overlapping line + semantically similar
claim**. The merged finding records both tools (e.g. `"tool": "coderabbit+codex"`).
Agreement across tools is a useful validity signal — preserve it for the validator.

## Step 5 — Validate (single pass)

Dispatch ONE validation subagent with the deduped findings list and repo access. For
each finding it checks the **claim against the actual current code** (post-`/simplify`),
anchored on the code and claim only — not the reviewer's wording or confidence.

It returns, per finding:
```json
{
  "id": "cr-1",
  "verdict": "valid | invalid | uncertain",
  "reason": "why",
  "fix_safe": true
}
```

`fix_safe` = the suggested fix is mechanical and low-risk to apply automatically
(e.g. a clear off-by-one, a null check). Set `false` for judgment calls
(e.g. "consider refactoring this module").

## Step 6 — Auto-Fix

Apply a finding **only if `verdict == "valid"` AND `fix_safe == true`**. Apply fixes
one at a time. If a fix does not apply cleanly (code already changed, ambiguous
location), downgrade it to the report instead of forcing it.

| verdict | fix_safe | action |
|---------|----------|--------|
| valid | true | auto-fix |
| valid | false | report → "Valid, needs your call" |
| uncertain | any | report → "Uncertain, verify" |
| invalid | any | report → "Dismissed (+ reason)" |

Do not perform any performative agreement; just apply and record.

## Step 6.5 — Verify

After fixes, run verification:
1. Use `--verify "<cmd>"` if provided.
2. Else auto-detect from the project: `Cargo.toml` → `cargo build` / `cargo test`;
   `package.json` → test/lint script; etc.
3. Else report "no verification run" — do not guess.

If verification **fails**, flag it in the report and list the applied fixes so the
user can pinpoint or revert. **Do not silently revert** — the user stays in control.

## Step 7 — Report

```
Multi-Review Summary

✅ Fixed (N)
  - src/foo.rs:42 — off-by-one skips last element  [coderabbit+codex]

⚠️ Valid, needs your decision (N)
  - src/bar.rs:10 — consider extracting helper      [coderabbit]

❓ Uncertain, verify (N)
  - ...

❌ Dismissed (N)
  - src/baz.rs:7 — claimed leak; tested false: <reason>  [codex]

🛠 Tools: simplify ✓ (3 edits) · coderabbit ✓ (6 findings) · codex ✗ (out of tokens)
🔬 Verify: `cargo test` → passed
```

## Edge Cases

- **No changes in scope** → skip everything; report "nothing to review."
- **A CLI not installed / not authenticated** → that subagent returns `status: failed`;
  continue with the rest.
- **All review CLIs fail** → still report `/simplify`'s result; note no external findings.
- **Zero valid findings** → report it; run verification only if the tree was changed.
- **Fix doesn't apply cleanly** → downgrade to report, never force.
