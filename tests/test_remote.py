"""Legacy remote helpers against local SSH/rsync stand-ins; no remote server."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

KIT = Path(__file__).resolve().parents[1]
MOCK = r'''#!/usr/bin/env python3
import json, os, shutil, subprocess, sys
from pathlib import Path
root = Path(os.environ['REMOTE_FIXTURE'])
tool, args = Path(sys.argv[0]).name, sys.argv[1:]
with (root / 'calls.jsonl').open('a') as out:
    out.write(json.dumps(dict(tool=tool, args=args)) + '\n')
remote = root / 'remote'
if tool == 'ssh':
    raise SystemExit(subprocess.run(['/bin/sh', '-c', args[-1]], cwd=remote).returncode)
if tool == 'tmux':
    raise SystemExit(1 if args[0] == 'has-session' else 0)
source, destination = args[-2:]
def path(value):
    if ':' not in value:
        return Path(value)
    target = (remote / value.split(':', 1)[1]).resolve()
    target.relative_to(remote)
    return target
source, destination = path(source), path(destination)
if not source.is_dir():
    raise SystemExit(23)
destination.mkdir(parents=True, exist_ok=True)
excluded = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.cache', 'outputs'} if '--exclude' in args else set()
if '--delete' in args:
    for item in destination.iterdir():
        if not (source / item.name).exists() and item.name not in excluded:
            if item.is_dir(): shutil.rmtree(item)
            else: item.unlink()
for item in source.iterdir():
    if item.name in excluded: continue
    if item.is_dir(): shutil.copytree(item, destination / item.name, dirs_exist_ok=True)
    else: shutil.copy2(item, destination / item.name)
'''


class RemoteHelpers(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='remote-helpers-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.conf = self.root / 'conf'
        self.conf.mkdir()
        self.mock = self.root / 'mock'
        self.mock.mkdir()
        (self.root / 'remote').mkdir()
        for name in ('ssh', 'rsync', 'tmux'):
            path = self.mock / name
            path.write_text(MOCK)
            path.chmod(0o755)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(
            ('LLM_', 'CLAUDE_', 'DEEPSEEK_', 'GIT_', 'COMPUTE_'))}
        self.env.update(HOME=str(self.root), LLM_WORKER_CONF_DIR=str(self.conf),
                        PATH=str(self.mock) + os.pathsep + os.environ['PATH'],
                        REMOTE_FIXTURE=str(self.root), PYTHONDONTWRITEBYTECODE='1')
        self.configure()
        self.repo = self.root / 'original'
        self.repo.mkdir()
        (self.repo / 'source.txt').write_text('base\n')
        self.call('git', 'init', '-q', cwd=self.repo)
        self.call('git', 'add', '.', cwd=self.repo)
        self.call('git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@local',
                  'commit', '-qm', 'base', cwd=self.repo)
        self.worktrees = []
        for name in ('a', 'b'):
            path = self.root / name / 'attempts/0001/worktree'
            path.parent.mkdir(parents=True)
            self.call('git', 'worktree', 'add', '--detach', '-q', path, 'HEAD', cwd=self.repo)
            (path / (name + '.txt')).write_text(name)
            self.worktrees.append(path)

    def configure(self, profile='', **values):
        values = dict(dict(COMPUTE_HOST='fixture-lab', COMPUTE_WORK_DIR='lab-work'), **values)
        (self.conf / ('env' + ('.' + profile if profile else ''))).write_text(
            ''.join('export ' + k + '=' + shlex.quote(v) + '\n' for k, v in values.items()))

    def call(self, *args, cwd=None, env=None, code=0):
        result = subprocess.run(list(map(str, args)), cwd=cwd or self.worktrees[0],
                                env=env or self.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def records(self, tool):
        return [x for x in map(json.loads, (self.root / 'calls.jsonl').read_text().splitlines())
                if x['tool'] == tool]

    def sync(self, path, env=None):
        return self.call(KIT / 'bin/remote-sync', cwd=path, env=env)

    def test_concurrent_worktrees_keep_distinct_remote_files_and_git_metadata_local(self):
        (self.repo / 'source.txt').write_text('staged\n')
        self.call('git', 'add', 'source.txt', cwd=self.repo)
        (self.repo / 'source.txt').write_text('unstaged\n')
        (self.repo / 'untracked.txt').write_text('keep')
        before = self.call('git', 'status', '--porcelain', cwd=self.repo).stdout
        env = dict(self.env, LLM_TASK_MANAGED='1')
        children = [subprocess.Popen([str(KIT / 'bin/remote-sync')], cwd=p, env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    for p in self.worktrees]
        for child in children:
            out, err = child.communicate(timeout=15)
            self.assertEqual(child.returncode, 0, out + err)
        destinations = [x['args'][-1] for x in self.records('rsync')]
        self.assertEqual(len(set(destinations)), 2)
        for destination in destinations:
            target = self.root / 'remote' / destination.split(':', 1)[1]
            self.assertFalse((target / '.git').exists())
            self.assertEqual(sum((target / name).exists() for name in ('a.txt', 'b.txt')), 1)
            (target / 'remote-only.txt').write_text('preserve')
        for path in self.worktrees:
            self.sync(path, env=env)
        for destination in destinations:
            target = self.root / 'remote' / destination.split(':', 1)[1]
            self.assertEqual((target / 'remote-only.txt').read_text(), 'preserve')
        self.assertTrue(all('--delete' not in x['args'] for x in self.records('rsync')))
        self.assertEqual(self.call('git', 'status', '--porcelain', cwd=self.repo).stdout, before)
        self.assertEqual((self.repo / 'source.txt').read_text(), 'unstaged\n')

    def test_profile_runtime_override_and_ssh_config_apply_to_sync_and_fetch(self):
        self.configure(COMPUTE_HOST='')
        self.configure('impl', COMPUTE_HOST='profile-lab')
        ssh_config = self.root / 'ssh config'
        ssh_config.write_text('Host fixture-*\n  HostName nowhere.invalid\n')
        env = dict(self.env, LLM_WORKER_PROFILE='impl', COMPUTE_SSH_CONFIG=str(ssh_config))
        self.sync(self.worktrees[0], env=env)
        self.assertEqual(self.records('ssh')[0]['args'][-2], 'profile-lab')
        env['COMPUTE_HOST'] = 'runtime-lab'
        self.call(KIT / 'bin/remote-fetch', env=env)
        for record in self.records('rsync'):
            command = shlex.split(record['args'][record['args'].index('-e') + 1])
            self.assertEqual(command[:3], ['ssh', '-F', str(ssh_config)])
            self.assertIn('BatchMode=yes', command)
        self.assertIn('runtime-lab:', self.records('rsync')[-1]['args'][-2])
        self.call(KIT / 'bin/remote-info', env=dict(env, COMPUTE_HOST=''), code=2)

    def test_runtime_host_survives_empty_saved_default(self):
        self.configure(COMPUTE_HOST='')
        self.sync(self.worktrees[0], env=dict(self.env, COMPUTE_HOST='runtime-lab'))
        self.assertEqual(self.records('ssh')[0]['args'][-2], 'runtime-lab')
        (self.conf / 'env').unlink()
        self.sync(self.worktrees[0], env=dict(self.env, COMPUTE_HOST='runtime-lab'))
        self.assertEqual(self.records('ssh')[-1]['args'][-2], 'runtime-lab')

    def test_missing_profile_or_bad_config_fails_before_ssh(self):
        self.call(KIT / 'bin/remote-sync', env=dict(self.env, LLM_WORKER_PROFILE='missing'), code=2)
        self.call(KIT / 'bin/remote-sync', env=dict(self.env, LLM_WORKER_PROFILE='../other'), code=2)
        for name, value in [('COMPUTE_HOST', '-oProxyCommand=bad'), ('COMPUTE_WORK_DIR', '/'),
                            ('COMPUTE_WORK_DIR', 'x/../shared'), ('COMPUTE_SSH_CONFIG', '/missing')]:
            self.call(KIT / 'bin/remote-sync', env=dict(self.env, **{name: value}), code=2)
        self.assertFalse((self.root / 'calls.jsonl').exists())

    def test_run_quotes_paths_fetches_outputs_and_preserves_remote_exit_code(self):
        env = dict(self.env, COMPUTE_WORK_DIR="remote copies/O'Brien")
        self.call(KIT / 'bin/remote-run', 'printf artifact > outputs/result.txt; exit 7', env=env, code=7)
        self.assertEqual((self.worktrees[0] / 'outputs/result.txt').read_text(), 'artifact')
        self.assertTrue(all('-e' in x['args'] for x in self.records('rsync')))

    def test_submit_namespaces_same_job_label_and_writes_valid_scripts(self):
        for worktree in self.worktrees:
            self.call(KIT / 'bin/remote-submit', 'job.v1', 'printf done > outputs/done.txt', cwd=worktree)
        sessions = [x['args'][x['args'].index('-s') + 1]
                    for x in self.records('tmux') if x['args'][0] == 'new-session']
        self.assertEqual(len(set(sessions)), 2)
        scripts = list((self.root / 'remote').glob('lab-work/*/.jobs/job.v1.sh'))
        self.assertEqual(len(scripts), 2)
        for script in scripts:
            self.call('bash', '-n', script)
            self.call('bash', script, cwd=self.root / 'remote')
            self.assertEqual((script.parent.parent / 'outputs/done.txt').read_text(), 'done')
