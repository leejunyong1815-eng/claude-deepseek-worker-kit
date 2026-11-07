#!/usr/bin/env bash
# Offline install/configuration; network requests require --probe.
set -euo pipefail
KIT="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
command -v python3 >/dev/null 2>&1 || { echo 'Python 3.9+ is required. On Ubuntu: sudo apt install python3' >&2; exit 2; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))' || { echo 'Python 3.9+ is required; use Ubuntu 22.04/24.04 or install a newer Python.' >&2; exit 2; }
exec python3 "$KIT/lib/install.py" "$@"
