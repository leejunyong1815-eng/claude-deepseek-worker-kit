#!/usr/bin/env bash
# Remove only Local Worker Kit commands; preserve configuration/results by default.
set -euo pipefail
source "$(dirname "$(readlink -f "$0")")/bin/_kit_env.sh"
PREFIX="${PREFIX:-$HOME/.local/bin}"; PURGE=0
while [ $# -gt 0 ]; do
 case "$1" in --prefix) PREFIX="$2"; shift 2;; --purge) PURGE=1; shift;; *) echo "unknown option: $1" >&2; exit 2;; esac
done
for name in _backends.py _config_migration.py _deepseek_permissions.py _duo.py _kit_env.py _kit_env.sh _manual_duo.sh _worker_compute.py _worker_permissions.py _worker_pool.py claude-duo claude-main claude-worker codex-duo codex-main deepseek-doctor deepseek-duo deepseek-main deepseek-probe deepseek-project-init deepseek-project-update deepseek-task deepseek-worker llm-backend llm-probe llm-task llm-worker project-init project-update qwen-worker remote-common.sh remote-fetch remote-info remote-run remote-submit remote-sync worker-compute-job worker-doctor worker-task; do
 if [ -f "$PREFIX/$name" ]; then rm -f -- "$PREFIX/$name"; fi
done
if [ "$PURGE" = 1 ]; then rm -rf -- "$LLM_WORKER_CONF_DIR"; else echo "Configuration and all results preserved: $LLM_WORKER_CONF_DIR"; fi
