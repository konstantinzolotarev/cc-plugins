# cc-plugins

Claude Code skills, installed as one plugin.

| skill | use |
|---|---|
| `audit` | whole-codebase health audit: duplication, overcomplication, dead code, convention drift |
| `brainstorm` | turn an idea into a design through one-question-at-a-time dialogue |
| `clarify` | untangle a mismatch between what the user expected and what happened |
| `interview` | question a plan before implementing it |
| `multi-review` | run several review tools, validate findings, fix the safe ones |
| `pr-review` | verify finished work against its requirements |
| `pr-validate-review` | check review feedback before acting on it |
| `rust-review` | idiomatic Rust guidance |
| `team-lead` | one agent per agterm workspace that briefs and verifies peer sessions |

`team-lead` needs a workspace file at `$CLAUDE_CONFIG_DIR/team/<workspace>.md`; start from
`skills/team-lead/assets/workspace.template.md`.
