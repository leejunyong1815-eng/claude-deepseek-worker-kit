"""Owned local worker pools; execution/locking/verification remain in worker-task."""
import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid
from _backends import atomic, choose, load
BIN = Path(__file__).resolve().parent
TERMINAL = {'succeeded', 'failed', 'cancelled', 'interrupted'}

def home():
    return Path(os.environ.get('LLM_POOL_HOME', str(Path(os.environ.get('XDG_STATE_HOME', Path.home() / '.local/state')) / 'local-worker/pools'))).expanduser().resolve()

def identity(pid):
    try:
        start = Path('/proc', str(pid), 'stat').read_text().split(') ', 1)[1].split()[19]
        return {'pid': pid, 'start': start, 'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}
    except (OSError, IndexError):
        return None

def alive(who):
    return isinstance(who, dict) and who == identity(who.get('pid', 0))

def manifest(folder):
    folder = Path(folder).resolve()
    data = json.loads((folder / 'pool.json').read_text())
    if data['owner_uid'] != os.getuid() or folder != home() / data['pool_id']:
        raise ValueError('pool is not owned by this user or registry')
    return data

def repository_root(project):
    project=Path(project).resolve()
    environment={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
    try:
        return Path(subprocess.check_output(['git','-C',str(project),'rev-parse','--show-toplevel'],env=environment,stderr=subprocess.PIPE,text=True).strip()).resolve()
    except subprocess.CalledProcessError:
        raise ValueError('managed pools require a Git project; use --manual for untracked conversation')


def create(project, kind, count, backends, models, profiles, labels, tag, maximum=4):
    project = repository_root(project)
    if not project.is_dir():
        raise ValueError('project directory missing')
    backends = backends or [choose(profiles[0] if profiles else '')[0]]
    for backend in backends:
        load(backend)
    if count == 'auto':
        count = min(maximum, sum((load(b).get('max_parallel', 2) for b in set(backends))))
    else:
        count = int(count)
    if not 1 <= count <= 32:
        raise ValueError('workers must be auto or 1..32')
    if len(labels) > count:
        raise ValueError('more worker labels than workers')
    for value in [tag, *labels]:
        if len(value) > 256 or any((ord(c) < 32 for c in value)):
            raise ValueError('labels must be single-line text up to 256 characters')
    if len(backends) > count:
        raise ValueError('increase workers/max-workers to cover all selected backends')
    for values in (models, profiles):
        if values and len(values) not in (1, count):
            raise ValueError('provide one backend/model/profile or one per worker')
    root = home()
    if root == project or project in root.parents:
        raise ValueError('pool state must be outside the original checkout')
    pool_id = 'p-' + uuid.uuid4().hex
    folder = root / pool_id
    folder.mkdir(parents=True, mode=448)
    (folder / 'tasks').mkdir(mode=448)
    (folder / 'workers').mkdir(mode=448)
    slots = []
    allocation = list(backends)
    while len(allocation) < count:
        selected = max(dict.fromkeys(backends), key=lambda b: load(b).get('max_parallel', 2) - allocation.count(b))
        allocation.append(selected)
    for i in range(count):
        backend = allocation[i]
        model = models[i % len(models)] if models else None
        profile = profiles[i % len(profiles)] if profiles else ''
        if model:
            choose(profile, backend, model)
        slots.append({'worker_id': 'w-' + uuid.uuid4().hex[:12], 'label': labels[i] if i < len(labels) else 'llm-worker-' + str(i + 1), 'backend': backend, 'model': model, 'profile': profile})
    data = {'pool_id': pool_id, 'owner_uid': os.getuid(), 'project': str(project), 'kind': kind, 'label': tag, 'created_at': time.time(), 'workers': slots, 'state_dir': str(folder / 'tasks'), 'task_command': str(folder / 'worker-task'), 'tmux_session': 'local-worker-' + pool_id[2:14]}
    routing = {'LLM_POOL_DIR': str(folder), 'LLM_TASK_HOME': data['state_dir'], 'LLM_POOL_HOME': str(home()), 'LLM_WORKER_CONF_DIR': os.environ['LLM_WORKER_CONF_DIR']}
    command = folder / 'worker-task'
    command.write_text('#!/usr/bin/env python3\nimport os,sys\nos.environ.update(' + repr(routing) + ')\nos.execv(' + repr(str(BIN / 'worker-task')) + ',["worker-task",*sys.argv[1:]])\n')
    command.chmod(448)
    atomic(folder / 'pool.json', data)
    return (folder, data)

def route_spec(raw, state_dir):
    folder = Path(os.environ['LLM_POOL_DIR'])
    data = manifest(folder)
    if Path(state_dir).resolve() != Path(data['state_dir']) or Path(raw.get('repository', '.')).resolve() != Path(data['project']):
        raise ValueError('task must use its owned pool project and state directory')
    role = raw.get('role', 'implementer')
    candidates = []
    loads = {w['worker_id']: 0 for w in data['workers']}
    for path in Path(data['state_dir']).glob('t-*/state.json'):
        saved = json.loads(path.read_text())
        if saved['state'] in {'queued', 'running', 'verifying'} and saved.get('worker_id') in loads:
            loads[saved['worker_id']] += 1
    for slot in data['workers']:
        if raw.get('worker_id') and raw['worker_id'] != slot['worker_id']:
            continue
        if raw.get('backend') and raw['backend'] != slot['backend']:
            continue
        if 'profile' in raw and raw['profile'] != slot['profile']:
            continue
        if raw.get('model') and slot['model'] and (raw['model'] != slot['model']):
            continue
        try:
            backend, _, model = choose(slot['profile'], slot['backend'], raw.get('model') or slot['model'], role)
        except (ValueError, OSError):
            continue
        candidates.append((loads[slot['worker_id']], slot, backend, model['id']))
    if not candidates:
        raise ValueError('no owned worker has a registered model for this task; configure backend/model/roles')
    _, slot, backend, model = min(candidates, key=lambda item: item[0])
    return dict(raw, worker_id=slot['worker_id'], backend=backend, model=model, profile=slot['profile'])

def owned():
    result = []
    for folder in sorted(home().glob('p-*')):
        try:
            data = manifest(folder)
            workers = []
            for slot in data['workers']:
                path = folder / 'workers' / (slot['worker_id'] + '.json')
                status = json.loads(path.read_text()) if path.is_file() else {}
                workers.append(dict(slot, owned=True, alive=alive(status.get('process')), status=status.get('state', 'not_started'), task_id=status.get('task_id')))
            result.append(dict(data, owned=True, workers=workers))
        except (OSError, ValueError, KeyError):
            continue
    return result

def stop(folder):
    data = manifest(folder)
    (Path(folder) / 'STOP').touch(mode=384)
    for slot in data['workers']:
        path = Path(folder) / 'workers' / (slot['worker_id'] + '.json')
        try:
            who = json.loads(path.read_text()).get('process')
            if alive(who):
                os.kill(who['pid'], signal.SIGTERM)
        except (OSError, ValueError):
            pass

@contextlib.contextmanager
def admission(backend):
    limit = load(backend).get('max_parallel', 2)
    folder = home().parent / 'backend-locks' / hashlib.sha256(backend.encode()).hexdigest()
    folder.mkdir(parents=True, exist_ok=True, mode=448)
    acquired = None
    for i in range(limit):
        stream = (folder / str(i)).open('a')
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = stream
            break
        except BlockingIOError:
            stream.close()
    try:
        yield acquired
    finally:
        if acquired:
            acquired.close()

def serve(folder, worker_id, once=False):
    folder = Path(folder).resolve()
    data = manifest(folder)
    slot = next((x for x in data['workers'] if x['worker_id'] == worker_id), None)
    if slot is None:
        raise ValueError('worker does not belong to this pool')
    lock = (folder / 'workers' / (worker_id + '.lock')).open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise ValueError('worker already serving')
    halted = []
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: halted.append(True))
    output = folder / 'workers' / (worker_id + '.json')
    who = identity(os.getpid())

    def status(state, task=None):
        atomic(output, dict(process=who, state=state, task_id=task, updated_at=time.time()))
    print('[owned ' + data['pool_id'][-8:] + '] ' + slot['label'] + ' / ' + worker_id + ' / ' + slot['backend'] + ' / ' + (slot['model'] or 'role-auto'), flush=True)
    status('idle')
    try:
        while not halted and (not (folder / 'STOP').exists()):
            candidates = []
            for path in (folder / 'tasks').glob('t-*/state.json'):
                state = json.loads(path.read_text())
                if state['state'] == 'queued' and state.get('worker_id') == worker_id and (state.get('reason') != 'uncommitted_dependency'):
                    candidates.append((state['created_at'], state['task_id']))
            if not candidates:
                if once:
                    break
                time.sleep(0.15)
                continue
            task = min(candidates)[1]
            with admission(slot['backend']) as granted:
                if not granted:
                    status('waiting_backend', task)
                    time.sleep(0.15)
                    continue
                status('running', task)
                print('RUN ' + task, flush=True)
                log = folder / 'workers' / (task + '.runner.log')
                env = dict(os.environ, LLM_TASK_HOME=data['state_dir'])
                env.pop('LLM_POOL_DIR', None)
                with log.open('a') as stream:
                    child = subprocess.Popen([str(BIN / 'worker-task'), 'run', task], env=env, stdout=stream, stderr=subprocess.STDOUT, pass_fds=(granted.fileno(),))
                    while child.poll() is None:
                        if halted or (folder / 'STOP').exists():
                            subprocess.run([str(BIN / 'worker-task'), 'cancel', task], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        time.sleep(0.1)
                    state = json.loads((folder / 'tasks' / task / 'state.json').read_text())
                print(state['state'].upper() + ' ' + task + ' ' + str(state.get('reason') or ''), flush=True)
                status('idle')
            if once:
                break
    finally:
        status('stopped')
        lock.close()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    s = sub.add_parser('serve')
    s.add_argument('--pool-dir', type=Path, required=True)
    s.add_argument('--worker-id', required=True)
    s.add_argument('--once', action='store_true')
    sub.add_parser('list')
    s = sub.add_parser('stop')
    s.add_argument('pool_id')
    args = p.parse_args()
    if args.command == 'serve':
        serve(args.pool_dir, args.worker_id, args.once)
    elif args.command == 'list':
        print(json.dumps(owned(), ensure_ascii=False, indent=2))
    else:
        stop(home() / args.pool_id)
if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, KeyError):
        raise SystemExit('worker pool error; inspect owned pool status and preserved logs')
