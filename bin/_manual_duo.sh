#!/usr/bin/env bash
# Explicit legacy interactive messaging mode; code editing needs separately prepared worktrees.
set -euo pipefail
source "$(dirname "$(readlink -f "$0")")/_kit_env.sh"
BIN="$(dirname "$(readlink -f "$0")")"
SESSION="${LLM_DUO_SESSION:-claude-duo}"; N=1; PROFILES=""; DIR="$PWD"
while [ $# -gt 0 ]; do
 case "$1" in
  --kill) tmux kill-session -t "$SESSION"; exit;;
  -w|--workers) N="$2"; shift 2;;
  -P|--profile|--profiles) PROFILES="$2"; shift 2;;
  -h|--help) echo 'claude-duo --manual [-w N] [-P profile,profile] [project]'; exit;;
  -*) echo 'unknown manual option' >&2; exit 2;;
  *) DIR="$1"; shift;;
 esac
done
[[ "$N" =~ ^[0-9][0-9]?$ ]] || exit 2
DIR="$(cd "$DIR" && pwd)"; CONF_DIR="$LLM_WORKER_CONF_DIR"
[ -f "$CONF_DIR/env" ] || { echo 'configure the kit first' >&2; exit 2; }
name_of() { (source "$1"; printf '%s' "${WORKER_NAME:-llm-worker}"); }
BASE="$(name_of "$CONF_DIR/env")"; COMMANDS=(); LABELS=()
append_worker() {
 local profile="$1" label="$2" command
 local args=(env "LLM_WORKER_NAME=$label" "$BIN/llm-worker")
 [ -z "$profile" ] || args+=(-P "$profile")
 printf -v command '%q ' "${args[@]}"; COMMANDS+=("$command; exec bash"); LABELS+=("$label")
}
for ((i=1;i<=N;i++)); do label="$BASE"; [ "$N" = 1 ] || label="$BASE-$i"; append_worker '' "$label"; done
IFS=',' read -r -a profiles <<< "$PROFILES"
for profile in "${profiles[@]}"; do
 [ -n "$profile" ] || continue
 [[ "$profile" =~ ^[A-Za-z0-9_-]+$ ]] && [ -f "$CONF_DIR/env.$profile" ] || exit 2
 append_worker "$profile" "$(name_of "$CONF_DIR/env.$profile")"
done
[ "${#COMMANDS[@]}" -gt 0 ] || exit 2
if tmux has-session -t "$SESSION" 2>/dev/null; then exec tmux attach -t "$SESSION"; fi
printf -v main '%q' "$BIN/claude-main"
tmux new-session -d -s "$SESSION" -c "$DIR" -x 200 -y 60 "$main; exec bash"
for i in "${!COMMANDS[@]}"; do
 pane="$(tmux split-window -P -F '#{pane_id}' -t "$SESSION" -c "$DIR" "${COMMANDS[$i]}")"
 tmux select-pane -t "$pane" -T "${LABELS[$i]}"
 tmux select-layout -t "$SESSION" tiled
done
exec tmux attach -t "$SESSION"
