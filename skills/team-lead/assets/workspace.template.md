# Team: <workspace>

The lead reads this file at the start of every session and before every brief. It holds facts
about the team, never about the code. Keep every line a fact the lead would otherwise have to
remember; delete lines that stop being true.

## Workspace

- agterm workspace name: `<workspace>`
- profile: `<CLAUDE_CONFIG_DIR>` (peers inherit it from the lead's shell)
- ephemeral cap: 3 (ephemeral peers alive at once)

## Repos and standing roles

One row per repo. `role` is the peer name the lead spawns with `claude -n <role>` and messages
with SendMessage. A role is never closed by the lead.

| repo path | role | may | must never |
|---|---|---|---|
| `~/Coding/<repo>` | `<role>` | implement in a worktree the lead names, run the repo's gate, run this repo's services | commit, push, read or print secrets, start another repo's services |

## Services

Who runs what, so no peer starts a service that belongs to another role.

| service | owning role | how the lead asks for it |
|---|---|---|
| `<service>` | `<role>` | "start <service> for <reason>; report the URL and how to stop it" |

## Secrets

Where secrets live and that they stay there. The lead and every peer may say a secret's location,
never its value.

- `<what>`: `<path>` — never in chat, never in a repo, never in a brief

## Rules

Copied verbatim into the Rules block of every brief. Edit here, not in the briefs.

```
- Never commit or push. The lead commits only on the user's explicit request; you report and stop.
- Never add Co-Authored-By lines to anything.
- Never read, print, or relay a secret. Say where it lives if asked.
- Never start a service another role owns; ask the lead to route it.
- Tests and scripts never start databases or containers; read connection URLs from config and
  fail naming the variable if unset.
- <project conventions, one per line>
```

## Review threshold

A job is big, and gets a separate review peer before the lead reports, when any of:

- more than 5 files changed
- any change under `<auth|billing|storage|migrations>` paths
- the user says "review" or "big"

## Gate

What "the gate" means per repo, with the environment it needs and where that comes from.

- `<repo>`: `<command>`; needs `<VAR>` from `<file>`
