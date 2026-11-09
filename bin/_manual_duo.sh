#!/usr/bin/env bash
# Explicit legacy interactive messaging mode; code editing needs separately prepared worktrees.
set -euo pipefail
source "$(dirname "$(readlink -f "$0")")/_kit_env.sh"
BIN="$(dirname "$(readlink -f "$0")")"
N=1; PROFILES=""; DIR="$PWD"; NAME="${ORCHESTRATOR_NAME:-}"; KILL=0; PERMISSIONS=(); NATIVE_AGENTS=selective
while [ $# -gt 0 ]; do
 case "$1" in
  --kill) KILL=1; shift;;
  -n|--name) [ $# -ge 2 ] && [ -n "$2" ] || exit 2; NAME="$2"; shift 2;;
  --name=*) NAME="${1#*=}"; [ -n "$NAME" ] || exit 2; shift;;
  --native-agents) [ $# -ge 2 ] || exit 2; NATIVE_AGENTS="$2"; shift 2;;
  --native-agents=*) NATIVE_AGENTS="${1#*=}"; shift;;
  -w|--workers) [ $# -ge 2 ] || exit 2; N="$2"; shift 2;;
  -P|--profile|--profiles) [ $# -ge 2 ] || exit 2; PROFILES="$2"; shift 2;;
  --permission-profile|--permissions-file|--read-path|--scratch-path)
    [ $# -ge 2 ] || exit 2; PERMISSIONS+=("$1" "$2"); shift 2;;
  -h|--help) echo 'claude-duo --manual [-n main-name] [-w N] [-P profiles] [--native-agents off|selective] [--permission-profile workspace] [project]'; exit;;
  -*) echo 'unknown manual option' >&2; exit 2;;
  *) DIR="$1"; shift;;
 esac
done
case "$NATIVE_AGENTS" in off|selective) ;; *) echo '--native-agents must be off or selective' >&2; exit 2;; esac
[[ "$N" =~ ^[0-9][0-9]?$ ]] && [ "$N" -le 32 ] || exit 2
DIR="$(cd "$DIR" && pwd)"; CONF_DIR="$LLM_WORKER_CONF_DIR"
DIR="$(git -C "$DIR" rev-parse --show-toplevel 2>/dev/null || printf '%s' "$DIR")"
KEY="$(python3 - "$DIR" "$NAME" "$NATIVE_AGENTS" <<'PY'
import hashlib, json, sys
values = sys.argv[1:3]
if sys.argv[3] != 'off':
    values.append(sys.argv[3])
print(hashlib.sha256(json.dumps(values).encode()).hexdigest()[:16])
PY
)"
SESSION="${LLM_DUO_SESSION:-claude-duo-$KEY}"
[[ "$SESSION" =~ ^[A-Za-z0-9_-]+$ ]] || { echo 'invalid LLM_DUO_SESSION' >&2; exit 2; }
if [ "$KILL" = 1 ]; then exec tmux kill-session -t "=$SESSION"; fi
[ -n "$NAME" ] || NAME="orchestrator-$KEY"
[ -f "$CONF_DIR/env" ] || { echo 'configure the kit first' >&2; exit 2; }
name_of() { (source "$1"; printf '%s' "${WORKER_NAME:-llm-worker}"); }
BASE="$(name_of "$CONF_DIR/env")"; COMMANDS=(); LABELS=()
append_worker() {
 local profile="$1" label="$2" command
 local args=(env "LLM_WORKER_NAME=$label" "$BIN/llm-worker" "${PERMISSIONS[@]}")
 [ -z "$profile" ] || args+=(-P "$profile")
 printf -v command '%q ' "${args[@]}"; COMMANDS+=("$command; exec bash"); LABELS+=("$label")
}
for ((i=1;i<=N;i++)); do append_worker '' "$BASE-$KEY-$i"; done
IFS=',' read -r -a profiles <<< "$PROFILES"
for profile in "${profiles[@]}"; do
 [ -n "$profile" ] || continue
 [[ "$profile" =~ ^[A-Za-z0-9_-]+$ ]] && [ -f "$CONF_DIR/env.$profile" ] || exit 2
 append_worker "$profile" "$(name_of "$CONF_DIR/env.$profile")-$KEY-$((${#LABELS[@]}+1))"
done
[ "${#COMMANDS[@]}" -gt 0 ] || exit 2
if tmux has-session -t "=$SESSION" 2>/dev/null; then exec tmux attach -t "=$SESSION"; fi
CONTEXT="$(python3 - "$DIR" "$SESSION" "${LABELS[@]}" <<'PY'
import json, sys
print(json.dumps(dict(project=sys.argv[1], tmux_session=sys.argv[2], workers=sys.argv[3:]), ensure_ascii=False))
PY
)"
printf -v main '%q ' env "LLM_MANUAL_WORKERS=$CONTEXT" "$BIN/claude-main" --name "$NAME" --native-agents "$NATIVE_AGENTS"
tmux new-session -d -s "$SESSION" -c "$DIR" -x 200 -y 60 "$main; exec bash"
for i in "${!COMMANDS[@]}"; do
 pane="$(tmux split-window -P -F '#{pane_id}' -t "=$SESSION" -c "$DIR" "${COMMANDS[$i]}")"
 tmux select-pane -t "$pane" -T "${LABELS[$i]}"
 tmux select-layout -t "=$SESSION" tiled
done
exec tmux attach -t "=$SESSION"
