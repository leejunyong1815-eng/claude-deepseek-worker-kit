#!/usr/bin/env bash
# Offline install/configuration; network requests require --probe.
set -euo pipefail
KIT="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
exec python3 "$KIT/lib/install.py" "$@"
