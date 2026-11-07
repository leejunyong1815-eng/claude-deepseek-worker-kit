"""Supervise one native main and an owned pool, with optional tmux panes."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import time
from _worker_pool import BIN, create, home, identity, owned, stop, alive, repository_root
from _backends import atomic

def launch(kind, args):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('-w', '--workers', default='auto')
    p.add_argument('--max-workers', type=int, default=4)
    p.add_argument('-B', '--backends', default='')
    p.add_argument('--models', default='')
    p.add_argument('-P', '--profiles', default='')
    p.add_argument('-C', '--project', type=Path, default=Path.cwd())
    p.add_argument('--label', action='append', default=[])
    modes = p.add_mutually_exclusive_group()
    modes.add_argument('--panes', action='store_true')
    modes.add_argument('--headless', action='store_true')
    p.add_argument('--kill', action='store_true')
    p.add_argument('--pool')
    p.add_argument('--no-attach', action='store_true')
    p.add_argument('words', nargs='*')
    if '--' in args:
        cut = args.index('--')
        forward = args[cut + 1:]
        args = args[:cut]
    else:
        forward = []
    a = p.parse_args(args)
    if a.words and Path(a.words[0]).is_dir():
        a.project = Path(a.words.pop(0))
    project = repository_root(a.project)
    if a.kill:
        pools = [x for x in owned() if x['project'] == str(project) and x['kind'] == kind and (not a.pool or x['pool_id'] == a.pool) and (not a.words or x['label'] == ' '.join(a.words))]
        if not pools:
            p.error('no owned pool for this project')
        data = max(pools, key=lambda x: x['created_at'])
        folder = home() / data['pool_id']
        stop(folder)
        if shutil.which('tmux'):
            subprocess.run(['tmux', 'kill-session', '-t', data['tmux_session']], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        who = data.get('main_process')
        if alive(who):
            os.kill(who['pid'], signal.SIGTERM)
        return 0
    if not shutil.which(kind):
        p.error(kind + ' is required')
    if a.panes and (not shutil.which('tmux')):
        p.error('tmux is required for --panes')
    if not 1 <= a.max_workers <= 32:
        p.error('max-workers must be 1..32')
    split = lambda value: value.split(',') if value else []
    folder, data = create(project, kind, a.workers, split(a.backends), split(a.models), split(a.profiles), a.label, ' '.join(a.words), a.max_workers)
    env = dict(os.environ, LLM_POOL_DIR=str(folder), LLM_TASK_HOME=data['state_dir'])
    main = [str(BIN / (kind + '-main')), *forward]
    print('Owned pool: ' + data['pool_id'] + ' | ' + str(len(data['workers'])) + ' workers | ' + ('panes' if a.panes else 'headless'), flush=True)
    if a.panes:
        session = data['tmux_session']
        prefix = ['env', 'LLM_POOL_DIR=' + str(folder), 'LLM_TASK_HOME=' + data['state_dir']]
        subprocess.run(['tmux', 'new-session', '-d', '-s', session, '-c', str(project), '-x', '200', '-y', '60', shlex.join(prefix + main)], check=True)
        try:
            for slot in data['workers']:
                command = [str(BIN / 'llm-worker'), 'serve', '--pool-dir', str(folder), '--worker-id', slot['worker_id']]
                pane = subprocess.check_output(['tmux', 'split-window', '-P', '-F', '#{pane_id}', '-t', session, '-c', str(project), shlex.join(command)], text=True).strip()
                subprocess.run(['tmux', 'select-pane', '-t', pane, '-T', '[owned] ' + slot['label']], check=True)
                subprocess.run(['tmux', 'select-layout', '-t', session, 'tiled'], check=True)
        except Exception:
            stop(folder)
            subprocess.run(['tmux', 'kill-session', '-t', session])
            raise
        if not a.no_attach:
            return subprocess.run(['tmux', 'attach-session', '-t', session]).returncode
        return 0
    workers = []
    streams = []
    child = None

    def interrupt(*_):
        if child and child.poll() is None:
            child.terminate()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupt)
    try:
        for slot in data['workers']:
            stream = (folder / 'workers' / (slot['worker_id'] + '.console.log')).open('a')
            streams.append(stream)
            workers.append(subprocess.Popen([str(BIN / 'llm-worker'), 'serve', '--pool-dir', str(folder), '--worker-id', slot['worker_id']], cwd=project, env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True))
        child = subprocess.Popen(main, cwd=project, env=env)
        data['main_process'] = identity(child.pid)
        atomic(folder / 'pool.json', data)
        return child.wait()
    finally:
        stop(folder)
        for proc in workers:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.terminate()
        for stream in streams:
            stream.close()
if __name__ == '__main__':
    try:
        raise SystemExit(launch(sys.argv[1], sys.argv[2:]))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise SystemExit('duo setup failed: ' + str(exc))
