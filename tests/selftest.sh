#!/usr/bin/env bash
# Offline checks; no Claude installation, lab credentials, server or model calls.
set -euo pipefail
KIT="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
cd "$KIT"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$KIT/bin${PYTHONPATH:+:$PYTHONPATH}"
for script in install.sh uninstall.sh bin/qwen-worker bin/llm-worker bin/claude-main bin/claude-duo bin/project-init bench/run.sh; do
    bash -n "$script"
done
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
python3 -B -m unittest discover -s demo/tests -v
