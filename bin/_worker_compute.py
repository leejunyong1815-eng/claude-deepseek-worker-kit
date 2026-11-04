"""GPU admission and scoped job supervision, shared by local and SSH execution.

No daemon, model selection, source upload, package installation or Git mutation.
The same stdlib executor is sent to the explicitly configured SSH destination.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import threading
import time
import uuid


def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def normalize(raw):
    if not isinstance(raw, dict):
        raise ValueError('compute_job must be an object')
    unknown = set(raw) - {'resource', 'transport', 'ssh_host', 'cwd', 'command', 'verify', 'gpus', 'gpu_count',
                         'max_memory_mb', 'max_utilization', 'idle_samples', 'poll_interval',
                         'wait_timeout', 'timeout', 'verify_timeout', 'expected_commit', 'heartbeat_timeout'}
    if unknown:
        raise ValueError('unknown compute job fields: ' + ', '.join(sorted(unknown)))
    job = dict(resource='gpu', transport='local', gpus=[0], gpu_count=1, max_memory_mb=1024,
               max_utilization=10, idle_samples=2, poll_interval=5, wait_timeout=1800,
               timeout=3600, verify_timeout=300, heartbeat_timeout=30)
    job.update(raw)
    if job['resource'] not in ('cpu', 'gpu'):
        raise ValueError('resource must be cpu or gpu')
    if job['transport'] not in ('local', 'ssh'):
        raise ValueError('transport must be local or ssh')
    if job['transport'] == 'ssh':
        host = job.get('ssh_host', '')
        if not isinstance(host, str) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.@-]*', host):
            raise ValueError('ssh_host must be an explicit SSH alias or user@host')
    cwd = job.get('cwd')
    if not isinstance(cwd, str) or (cwd != '@worktree' and not cwd.startswith('/')) or '\x00' in cwd or '..' in cwd.split('/'):
        raise ValueError('compute cwd must be an absolute path on the selected computer')
    def argv(value):
        return isinstance(value, list) and bool(value) and all(isinstance(x, str) and x and '\x00' not in x for x in value)
    if not argv(job.get('command')):
        raise ValueError('command must be a nonempty argv array (no shell interpolation)')
    if not isinstance(job.get('verify'), list) or not job['verify'] or not all(argv(v) for v in job['verify']):
        raise ValueError('verify must contain explicit argv arrays')
    if not isinstance(job['gpus'], list) or not job['gpus'] or not all(type(g) is int and 0 <= g < 256 for g in job['gpus']):
        raise ValueError('gpus must list GPU indices')
    if len(set(job['gpus'])) != len(job['gpus']):
        raise ValueError('duplicate GPU indices')
    for name, low, high in [('gpu_count', 1, len(job['gpus'])), ('idle_samples', 1, 100),
                             ('max_memory_mb', 0, 1048576), ('max_utilization', 0, 100)]:
        if type(job[name]) is not int or not low <= job[name] <= high:
            raise ValueError('invalid ' + name)
    for name, low, high in [('poll_interval', .05, 300), ('wait_timeout', .05, 604800),
                             ('timeout', .05, 604800), ('verify_timeout', .05, 86400),
                             ('heartbeat_timeout', 3, 300)]:
        value = job[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
            raise ValueError('invalid ' + name)
    if job.get('expected_commit') is not None and (not isinstance(job['expected_commit'], str) or not re.fullmatch(r'[0-9a-fA-F]{40,64}', job['expected_commit'])):
        raise ValueError('expected_commit must be a full Git commit ID')
    if cwd == '@worktree' and job['transport'] != 'local':
        raise ValueError('@worktree requires local transport')
    return job


def atomic(path, data):
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex)
    with tmp.open('x') as out:
        os.chmod(tmp, 0o600)
        json.dump(data, out, indent=2)
        out.write('\n')
        out.flush()
        os.fsync(out.fileno())
    os.replace(tmp, path)


def identity(pid):
    try:
        fields = Path('/proc/%d/stat' % pid).read_text().rsplit(')', 1)[1].split()
        return (fields[19], fields[0])
    except (OSError, IndexError):
        return None


def stop(child):
    if child is None:
        return
    expected, current = getattr(child, '_compute_identity', None), identity(child.pid)
    if expected and current and expected[0] != current[0]:
        return  # A recycled PID never grants authority to signal a new group.
    # The child owns a fresh session; only this job's process group is targeted.
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(child.pid, sig)
        except ProcessLookupError:
            return
        if sig == signal.SIGTERM:
            time.sleep(.15)
    child.wait()


def gpu_rows():
    args = ['nvidia-smi', '--query-gpu=index,uuid,memory.used,utilization.gpu', '--format=csv,noheader,nounits']
    result = subprocess.run(args, capture_output=True, text=True, timeout=10, check=True)
    rows = {}
    for line in result.stdout.splitlines():
        fields = [s.strip() for s in line.split(',')]
        if len(fields) != 4:
            raise ValueError('unreadable GPU counters')
        index, gpu, used, util = fields
        rows[int(index)] = (gpu, float(used), float(util))
    processes = subprocess.run(['nvidia-smi', '--query-compute-apps=gpu_uuid,pid', '--format=csv,noheader,nounits'],
                               capture_output=True, text=True, timeout=10, check=True)
    busy = set()
    for line in processes.stdout.splitlines():
        if not line.strip():
            continue
        fields = [s.strip() for s in line.split(',')]
        if len(fields) != 2 or not fields[1].isdigit():
            raise ValueError('unreadable compute-process counters; refusing GPU admission')
        busy.add(fields[0])
    return rows, busy


def executor():
    """One RPC over stdin/stdout; heartbeat loss stops this job, not other jobs."""
    envelope = json.loads(sys.stdin.readline())
    job = normalize(envelope['job'])
    run_id = envelope['run_id']
    if not re.fullmatch(r'c-[0-9a-f]{32}', run_id):
        raise ValueError('invalid run ID')
    root = Path(os.environ.get('XDG_STATE_HOME', str(Path.home() / '.local/state'))) / 'deepseek-worker/compute'
    folder = root / run_id
    try:
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        folder.mkdir(mode=0o700)  # Never overwrite an earlier run.
    except OSError:
        print(json.dumps(dict(run_id=run_id, spec_digest=checksum(job), state='failed', reason='compute_state_store_error')), flush=True)
        return
    state = dict(run_id=run_id, spec_digest=checksum(job), state='waiting', reason=None,
                 started_at=time.time(), command_exit_code=None, verification_exit_codes=[],
                 timed_out=False, wait_timed_out=False, verification_timed_out=False,
                 selected_gpus=[], selected_gpu_uuids=[], resource=job['resource'], cwd=job['cwd'],
                 source_commit=None, source_dirty=None, source_pinned=bool(job.get('expected_commit')),
                 stdout_path=str(folder / 'stdout.log'), stderr_path=str(folder / 'stderr.log'),
                 verification_log=str(folder / 'verification.log'), remote_result_path=str(folder / 'result.json'))
    cancelled = threading.Event()
    last_heartbeat = [time.monotonic()]
    def incoming():
        try:
            for line in sys.stdin:
                value = json.loads(line)
                if value.get('cancel'):
                    cancelled.set()
                if value.get('heartbeat'):
                    last_heartbeat[0] = time.monotonic()
        except (OSError, ValueError):
            pass
        finally:
            cancelled.set()
    threading.Thread(target=incoming, daemon=True).start()
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, lambda *_: cancelled.set())
    def aborted():
        if time.monotonic() - last_heartbeat[0] > job['heartbeat_timeout']:
            state['reason'] = 'heartbeat_lost'
            cancelled.set()
        return cancelled.is_set()
    def emit():
        atomic(folder / 'result.json', state)
        try:
            print(json.dumps(state), flush=True)
        except (BrokenPipeError, OSError):
            cancelled.set()
    locks, child = [], None
    try:
        cwd = Path(job['cwd']).resolve(strict=True)
        if not cwd.is_dir():
            raise ValueError('compute cwd is not a directory')
        git_env = {k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
        git_env['GIT_OPTIONAL_LOCKS'] = '0'
        revision = subprocess.run(['git', '-C', str(cwd), 'rev-parse', 'HEAD'], env=git_env,
                                  capture_output=True, text=True, timeout=10)
        if revision.returncode == 0:
            state['source_commit'] = revision.stdout.strip()
            dirty = subprocess.run(['git', '-C', str(cwd), 'status', '--porcelain=v1'], env=git_env,
                                   capture_output=True, text=True, timeout=10, check=True)
            state['source_dirty'] = bool(dirty.stdout)
        if job.get('expected_commit') and (state['source_commit'] != job['expected_commit'] or state['source_dirty']):
            state.update(state='failed', reason='source_revision_mismatch')
            return
        (root / 'gpu-locks').mkdir(exist_ok=True, mode=0o700)
        deadline, stable = time.monotonic() + job['wait_timeout'], {}
        emit()
        while not aborted():
            if job['resource'] == 'cpu':
                break
            rows, busy = gpu_rows()
            if any(g not in rows for g in job['gpus']):
                raise ValueError('requested GPU is not present')
            available = []
            for g in sorted(job['gpus']):
                gpu, used, util = rows[g]
                idle = gpu not in busy and used <= job['max_memory_mb'] and util <= job['max_utilization']
                stable[g] = stable.get(g, 0) + 1 if idle else 0
                if stable[g] >= job['idle_samples']:
                    lock = (root / 'gpu-locks' / (gpu.replace('/', '_') + '.lock')).open('a')
                    try:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        lock.close()
                        continue
                    available.append((g, gpu, lock))
            if len(available) >= job['gpu_count']:
                chosen = available[:job['gpu_count']]
                for _, _, lock in available[job['gpu_count']:]:
                    lock.close()
                locks = [v[2] for v in chosen]
                # Recheck after acquiring the common per-user GPU locks.
                fresh, busy = gpu_rows()
                if all(g in fresh and fresh[g][0] == gpu and gpu not in busy and
                       fresh[g][1] <= job['max_memory_mb'] and fresh[g][2] <= job['max_utilization'] for g, gpu, _ in chosen):
                    state['selected_gpus'] = [v[0] for v in chosen]
                    state['selected_gpu_uuids'] = [v[1] for v in chosen]
                    break
                for lock in locks:
                    lock.close()
                locks = []
            else:
                for _, _, lock in available:
                    lock.close()
            if time.monotonic() >= deadline:
                state.update(state='failed', reason='gpu_wait_timeout', wait_timed_out=True)
                return
            pause_until = min(time.monotonic() + job['poll_interval'], deadline)
            while time.monotonic() < pause_until and not aborted():
                cancelled.wait(min(.1, max(0, pause_until - time.monotonic())))
        if aborted():
            state.update(state='cancelled', reason=state['reason'] or 'cancelled')
            return
        env = {k:v for k,v in os.environ.items() if not (k.startswith(('ANTHROPIC_', 'LLM_')) or k in {'GITHUB_TOKEN','OPENAI_API_KEY'})}
        env['CUDA_VISIBLE_DEVICES'] = ','.join(state['selected_gpu_uuids'])
        env['WORKER_COMPUTE_RUN_ID'] = run_id
        def execute(argv, timeout, stdout, stderr):
            nonlocal child
            child = subprocess.Popen(argv, cwd=cwd, env=env, stdout=stdout, stderr=stderr,
                                     start_new_session=True)
            child._compute_identity = identity(child.pid)
            limit = time.monotonic() + timeout
            while child.poll() is None:
                if aborted():
                    stop(child)
                    return child.returncode, False
                if time.monotonic() >= limit:
                    stop(child)
                    return child.returncode, True
                time.sleep(.05)
            rc = child.returncode
            stop(child)  # Clean up any background members left in this job's group.
            return rc, False
        state['state'] = 'running'
        emit()
        with open(state['stdout_path'], 'xb') as stdout, open(state['stderr_path'], 'xb') as stderr:
            rc, timeout = execute(job['command'], job['timeout'], stdout, stderr)
        state.update(command_exit_code=rc, timed_out=timeout)
        if aborted():
            state.update(state='cancelled', reason=state['reason'] or 'cancelled')
            return
        if rc or timeout:
            state.update(state='failed', reason='compute_timeout' if timeout else 'compute_exit_nonzero')
            return
        state['state'] = 'verifying'
        emit()
        with open(state['verification_log'], 'xb') as log:
            for argv in job['verify']:
                rc, timeout = execute(argv, job['verify_timeout'], log, log)
                state['verification_exit_codes'].append(rc)
                state['verification_timed_out'] = timeout
                if aborted():
                    state.update(state='cancelled', reason=state['reason'] or 'cancelled')
                    return
                if rc or timeout:
                    state.update(state='failed', reason='compute_verification_timeout' if timeout else 'compute_verification_failed')
                    return
        if job.get('expected_commit'):
            final = subprocess.run(['git', '-C', str(cwd), 'rev-parse', 'HEAD'], env=git_env,
                                   capture_output=True, text=True, timeout=10)
            diff = subprocess.run(['git', '-C', str(cwd), 'diff', '--quiet', job['expected_commit'], '--'],
                                  env=git_env, capture_output=True, timeout=10)
            if final.returncode or final.stdout.strip() != job['expected_commit'] or diff.returncode:
                state.update(state='failed', reason='source_changed_during_compute')
                return
        state['state'] = 'succeeded'
    except (OSError, ValueError, subprocess.SubprocessError):
        state.update(state='failed', reason='compute_execution_error')
    finally:
        stop(child)
        for lock in locks:
            lock.close()
        state.update(finished_at=time.time(), duration_seconds=time.time() - state['started_at'])
        emit()


if __name__ == '__main__':
    executor()
