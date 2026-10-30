#!/usr/bin/env bash
# Offline checks; no Claude installation, lab credentials, server or model calls.
set -euo pipefail
KIT="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"
cd "$KIT"
export PYTHONDONTWRITEBYTECODE=1
for script in install.sh uninstall.sh bin/deepseek-worker bin/deepseek-main bin/deepseek-duo bin/deepseek-project-init bench/run.sh; do
    bash -n "$script"
done
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
python3 -B -m unittest discover -s demo/tests -v
