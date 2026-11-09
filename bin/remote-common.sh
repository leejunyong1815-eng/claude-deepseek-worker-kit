# remote-common.sh — remote-* 스크립트 공용. 직접 실행하지 않는다.
source "$(dirname "$(readlink -f "$0")")/_kit_env.sh"
REMOTE_BIN="$(dirname "$(readlink -f "$0")")"
PROFILE="${LLM_WORKER_PROFILE:-}"
[[ -z "$PROFILE" || "$PROFILE" =~ ^[A-Za-z0-9_-]+$ ]] || { echo 'remote: invalid profile' >&2; exit 2; }
# Save explicitly supplied values before sourcing trusted profile configuration.
declare -A _remote_overrides=()
for _remote_key in COMPUTE_HOST COMPUTE_WORK_DIR COMPUTE_SSH_CONFIG; do
    [ -z "${!_remote_key+x}" ] || _remote_overrides[$_remote_key]="${!_remote_key}"
done
CONF="$LLM_WORKER_CONF_DIR/env${PROFILE:+.$PROFILE}"
if [ -f "$CONF" ]; then
    # shellcheck disable=SC1090
    source "$CONF"
elif [ -n "$PROFILE" ]; then
    echo "remote: configuration missing: $CONF" >&2; exit 2
fi
for _remote_key in "${!_remote_overrides[@]}"; do
    printf -v "$_remote_key" '%s' "${_remote_overrides[$_remote_key]}"
done
unset _remote_key _remote_overrides
COMPUTE_HOST="${COMPUTE_HOST:-}"
COMPUTE_WORK_DIR="${COMPUTE_WORK_DIR:-claude-work}"
if [ -z "$COMPUTE_HOST" ]; then
    echo "remote: COMPUTE_HOST 가 비어 있습니다. $CONF 에서 ssh 별칭을 지정하세요." >&2
    exit 2
fi
ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
# Every checkout/worktree (including every managed attempt) gets its own remote
# namespace. Never reduce a managed root to its shared basename, "worktree".
REMOTE_VALUES="$(python3 - "$ROOT" "$COMPUTE_HOST" "$COMPUTE_WORK_DIR" "${COMPUTE_SSH_CONFIG:-}" <<'PY'
import hashlib, re, shlex, sys
from pathlib import Path, PurePosixPath
root, host, directory, config = sys.argv[1:]
if not re.fullmatch(r'[A-Za-z0-9_.@:%\[\]-]+', host) or host.startswith('-'):
    raise SystemExit('remote: invalid COMPUTE_HOST; use an SSH alias or user@host')
if (any(ord(c) < 32 for c in directory) or '~' in directory or
        '..' in PurePosixPath(directory).parts or str(PurePosixPath(directory)) in ('/', '.')):
    raise SystemExit('remote: COMPUTE_WORK_DIR must name a dedicated directory without ~ or ..')
root = str(Path(root).resolve())
slug = re.sub(r'[^A-Za-z0-9_-]+', '-', Path(root).name).strip('-')[:40] or 'project'
namespace = slug + '-' + hashlib.sha256(root.encode()).hexdigest()[:20]
ssh = ['ssh']
if config:
    config = str(Path(config).expanduser().resolve())
    if not Path(config).is_file():
        raise SystemExit('remote: COMPUTE_SSH_CONFIG does not exist')
    ssh += ['-F', config]
print('PROJECT=' + shlex.quote(Path(root).name))
print('REMOTE_NAMESPACE=' + shlex.quote(namespace))
print('REMOTE_ROOT=' + shlex.quote(str(PurePosixPath(directory) / namespace)))
print('RSYNC_SSH=' + shlex.quote(shlex.join(ssh + ['-o', 'BatchMode=yes'])))
print('SSH=(' + shlex.join(ssh + ['-o', 'BatchMode=yes', '--', host]) + ')')
PY
)" || exit 2
eval "$REMOTE_VALUES"
unset REMOTE_VALUES
export COMPUTE_HOST COMPUTE_WORK_DIR
export LLM_WORKER_PROFILE="$PROFILE"
# POSIX shell quoting for the remote login shell, including spaces/apostrophes.
remote_quote() { printf "'%s'" "${1//\'/\'\\\'\'}"; }
