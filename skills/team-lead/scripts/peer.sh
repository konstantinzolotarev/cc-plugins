#!/usr/bin/env bash
# peer.sh — spawn, list, tail and close Claude peer sessions in an agterm workspace.
#
#   peer.sh spawn <workspace> <name> <cwd> [--effort LEVEL]   start `claude -n <name>` in a new session
#   peer.sh list  <workspace>                                  sessions in the workspace: name, status, cwd
#   peer.sh tail  <name> [lines]                               last lines of the named session's buffer
#   peer.sh close <name> [--workspace-file FILE]               close an ephemeral session (refuses standing roles)
#
# Names: agterm shows a session as "<glyph> <name>" once Claude sets the terminal title, so every
# lookup strips a leading non-alphanumeric glyph and whitespace before comparing.
# Needs: agtermctl on PATH, jq, claude on PATH. The peer gets the lead's PATH and CLAUDE_CONFIG_DIR.
set -euo pipefail

die() { echo "peer.sh: $*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "$1 not on PATH"; }
need agtermctl; need jq

# Sessions of a workspace as TSV: id \t clean-name \t status \t cwd
sessions_of() {
  local ws=$1
  agtermctl tree --json | jq -r --arg ws "$ws" '
    .result.tree.workspaces[] | select(.name == $ws) | .sessions[]
    | [ .id,
        ((.name // .title // "") | sub("^[^A-Za-z0-9~/._-]+\\s*"; "")),
        (.status // "idle"),
        (.cwd // "") ]
    | @tsv'
}

# Find a session id by clean name in any workspace; prints "id\tworkspace" or nothing.
find_session() {
  local name=$1
  agtermctl tree --json | jq -r --arg name "$name" '
    .result.tree.workspaces[] as $w | $w.sessions[]
    | select(((.name // .title // "") | sub("^[^A-Za-z0-9~/._-]+\\s*"; "")) == $name)
    | [ .id, $w.name ] | @tsv' | head -n 1
}

cmd=${1:-}; shift || true
case "$cmd" in
  spawn)
    [ $# -ge 3 ] || die "usage: spawn <workspace> <name> <cwd> [--effort LEVEL]"
    ws=$1; name=$2; cwd=$3; shift 3
    effort=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --effort) effort=$2; shift 2 ;;
        *) die "unknown option $1" ;;
      esac
    done
    [[ "$name" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die "name must be [A-Za-z0-9._-], got '$name'"
    [ -d "$cwd" ] || die "cwd does not exist: $cwd"
    if [ -n "$(find_session "$name")" ]; then
      die "a session named '$name' already exists; pick another name or close it first"
    fi
    # agterm runs --command argv-style from the app's own environment: no user PATH, no
    # CLAUDE_CONFIG_DIR. Pass the lead's PATH, profile dir and the absolute claude binary through
    # env, so the peer lands in the lead's profile with the lead's tools. --wait holds the row
    # open after claude exits so a crash stays readable.
    claude_bin=$(command -v claude) || die "claude not on PATH"
    profile=${CLAUDE_CONFIG_DIR:-$HOME/.claude}
    # The tokenizer respects double quotes, so values with spaces (app bundle paths) are quoted.
    [[ "$PATH$profile$claude_bin" != *\"* ]] || die "PATH, profile or claude path contains a double quote; spawn cannot pass it argv-style"
    claude_cmd="env \"PATH=$PATH\" \"CLAUDE_CONFIG_DIR=$profile\" \"$claude_bin\" -n $name"
    [ -n "$effort" ] && claude_cmd="$claude_cmd --effort $effort"
    id=$(agtermctl session new --workspace-name "$ws" --cwd "$cwd" --name "$name" \
          --command "$claude_cmd" --wait --no-select --json | jq -r '.result.id')
    [ -n "$id" ] && [ "$id" != "null" ] || die "session new returned no id"
    # Wait until Claude has taken over the title (the glyph appears) or 30 s pass.
    for _ in $(seq 1 30); do
      title=$(agtermctl tree --json | jq -r --arg id "$id" '
        .result.tree.workspaces[].sessions[] | select(.id == $id) | (.name // .title // "")')
      if [[ "$title" =~ ^[^A-Za-z0-9] ]]; then break; fi
      sleep 1
    done
    echo "$name"
    ;;
  list)
    [ $# -ge 1 ] || die "usage: list <workspace>"
    printf 'NAME\tSTATUS\tCWD\n'
    sessions_of "$1" | awk -F'\t' 'BEGIN{OFS="\t"} {print $2, $3, $4}'
    ;;
  tail)
    [ $# -ge 1 ] || die "usage: tail <name> [lines]"
    name=$1; lines=${2:-40}
    hit=$(find_session "$name"); [ -n "$hit" ] || die "no session named '$name'"
    id=${hit%%$'\t'*}
    agtermctl session text --lines "$lines" --target "$id" --json | jq -r '.result.text'
    ;;
  close)
    [ $# -ge 1 ] || die "usage: close <name> [--workspace-file FILE]"
    name=$1; shift
    wsfile=""
    while [ $# -gt 0 ]; do
      case "$1" in
        --workspace-file) wsfile=$2; shift 2 ;;
        *) die "unknown option $1" ;;
      esac
    done
    hit=$(find_session "$name"); [ -n "$hit" ] || die "no session named '$name'"
    id=${hit%%$'\t'*}; ws=${hit#*$'\t'}
    # Standing roles come from the workspace file's roles table: the second column, backticked.
    [ -n "$wsfile" ] || wsfile="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/team/$ws.md"
    if [ -f "$wsfile" ] && grep -Eq "^\|[^|]*\|[[:space:]]*\`$name\`[[:space:]]*\|" "$wsfile"; then
      die "'$name' is a standing role in $wsfile; the lead never closes standing roles"
    fi
    agtermctl session close --target "$id" >/dev/null
    echo "closed $name"
    ;;
  *)
    sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
    exit 2
    ;;
esac
