"""Named manual sessions, explicit permissions and hooks without Claude/tmux."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

KIT = Path(__file__).resolve().parents[1]
MOCK = r'''#!/usr/bin/env python3
import json, os, subprocess, sys
from pathlib import Path
tool, args = Path(sys.argv[0]).name, sys.argv[1:]
with Path(os.environ['INTERACTIVE_CALLS']).open('a') as out:
    out.write(json.dumps(dict(tool=tool, args=args, env={k: os.environ.get(k) for k in ('LLM_WORKER_PROFILE', 'COMPUTE_HOST')})) + '\n')
if tool == 'claude': raise SystemExit(0)
if args[0] == 'has-session': raise SystemExit(1)
if args[0] in ('new-session', 'split-window'):
    result = subprocess.run(['bash', '-c', args[-1]], cwd=args[args.index('-c') + 1], stdin=subprocess.DEVNULL)
    if args[0] == 'split-window': print('%1')
    raise SystemExit(result.returncode)
'''


class InteractiveSessions(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='interactive-helpers-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        mock = self.root / 'mock'
        mock.mkdir()
        for name in ('claude', 'tmux'):
            path = mock / name
            path.write_text(MOCK)
            path.chmod(0o755)
        self.conf = self.root / 'conf'
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(
            ('LLM_', 'CLAUDE_', 'DEEPSEEK_', 'ORCHESTRATOR_', 'GIT_', 'ANTHROPIC_'))}
        self.env.update(HOME=str(self.root), LLM_WORKER_CONF_DIR=str(self.conf),
                        PATH=str(mock) + os.pathsep + os.environ['PATH'],
                        INTERACTIVE_CALLS=str(self.root / 'calls.jsonl'), PYTHONDONTWRITEBYTECODE='1')
        self.call(KIT / 'install.sh', '--non-interactive', '--prefix', self.root / 'installed')
        self.projects = [self.root / 'one', self.root / 'two']
        for project in self.projects:
            project.mkdir()

    def call(self, *args, env=None, cwd=None, code=0, data=None):
        result = subprocess.run(list(map(str, args)), env=env or self.env, cwd=cwd or KIT,
                                input=data, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def records(self, tool='claude'):
        return [x['args'] for x in map(json.loads, (self.root / 'calls.jsonl').read_text().splitlines())
                if x['tool'] == tool]

    def test_explicit_names_match_prompts_and_defaults_do_not_collide(self):
        self.call(KIT / 'bin/llm-worker', '-n', 'llm-worker-검토 v2', '-p', 'fixture')
        args = self.records()[-1]
        self.assertEqual(args.count('--name'), 1)
        self.assertEqual(args[args.index('--name') + 1], 'llm-worker-검토 v2')
        self.assertIn('Active worker: llm-worker-검토 v2.', args[args.index('--append-system-prompt') + 1])
        for command in ('llm-worker', 'claude-main'):
            for _ in range(2):
                self.call(KIT / ('bin/' + command), '-p', 'fixture')
            records = self.records()[-2:]
            self.assertNotEqual(*[x[x.index('--name') + 1] for x in records])
        self.call(KIT / 'bin/claude-main', '-n', 'my-main')
        args = self.records()[-1]
        self.assertEqual(args[args.index('--name') + 1], 'my-main')

    def test_manual_duo_passes_exact_suffixed_worker_names_to_named_main(self):
        self.call(KIT / 'bin/claude-duo', '--manual', '-n', 'ozaki', '-w', '2', self.projects[0])
        records = self.records()
        self.assertEqual(len(records), 3)
        main = records[0]
        self.assertEqual(main[main.index('--name') + 1], 'ozaki')
        prompt = main[main.index('--append-system-prompt') + 1]
        self.assertIn('Native delegation mode: selective', prompt)
        names = [x[x.index('--name') + 1] for x in records[1:]]
        self.assertEqual(len(set(names)), 2)
        for name in names:
            self.assertIn(name, prompt)
        self.assertIn('exact display names to live session IDs', prompt)
        self.call(KIT / 'bin/claude-duo', '--manual', '-n', 'ozaki', '-w', '2', self.projects[1])
        sessions = [x[x.index('-s') + 1] for x in self.records('tmux') if x[0] == 'new-session']
        self.assertEqual(len(set(sessions)), 2)
        all_names = [x[x.index('--name') + 1] for x in self.records() if x[x.index('--name') + 1] != 'ozaki']
        self.assertEqual(len(set(all_names)), 4)

    def test_manual_explicit_permissions_do_not_modify_configuration(self):
        before = {p.name: p.read_bytes() for p in self.conf.glob('env*')}
        self.call(KIT / 'bin/llm-worker', '--permission-profile', 'workspace',
                  '--read-path', str(self.projects[1]), '-p', 'fixture', cwd=self.projects[0])
        args = self.records()[-1]
        settings = json.loads(args[args.index('--settings') + 1])
        policy = settings['permissions']
        self.assertIn('Bash', policy['allow'])
        self.assertEqual(policy['defaultMode'], 'dontAsk')
        prefix = '//' + str(self.projects[0]).lstrip('/')
        self.assertIn('Edit(' + prefix + '/**)', policy['allow'])
        self.assertNotIn('Edit(' + prefix + '/**)', policy['deny'])
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.conf.glob('env*')})
        self.assertFalse(list(self.projects[0].iterdir()))
        self.call(KIT / 'bin/llm-worker', '-p', 'fixture', cwd=self.projects[0])
        args = self.records()[-1]
        self.assertNotIn('permissions', json.loads(args[args.index('--settings') + 1]))
        self.call(KIT / 'bin/llm-worker', '--read-path', str(self.projects[1]), code=2)

    def test_manual_profile_and_runtime_compute_host_reach_child_tools(self):
        self.call(KIT / 'install.sh', '--non-interactive', '--profile', 'impl', '--prefix', self.root / 'installed')
        self.call(KIT / 'bin/llm-worker', '-P', 'impl', '-p', 'fixture',
                  env=dict(self.env, COMPUTE_HOST='runtime-lab'))
        record = json.loads((self.root / 'calls.jsonl').read_text().splitlines()[-1])
        self.assertEqual(record['env']['LLM_WORKER_PROFILE'], 'impl')
        self.assertEqual(record['env']['COMPUTE_HOST'], 'runtime-lab')

    def test_managed_session_identity_and_permissions_cannot_be_overridden(self):
        for args in (['-n', 'other'], ['--name=other'], ['--permission-profile', 'workspace']):
            self.call(KIT / 'bin/llm-worker', *args, env=dict(self.env, LLM_TASK_MANAGED='1'), code=2)
        self.assertFalse((self.root / 'calls.jsonl').exists())

    def test_manual_native_modes_reach_main_and_use_separate_sessions(self):
        for mode in ('off', 'selective'):
            self.call(KIT / 'bin/claude-duo', '--manual', '--native-agents', mode,
                      '-n', 'my-main', '-w', '1', self.projects[0])
        records = self.records()
        default, selected = records[0], records[2]
        for args, native in ((default, True), (selected, False)):
            denied = args[args.index('--disallowedTools') + 1:args.index('--system-prompt-snapshot')]
            self.assertEqual('Agent' in denied, native)
        sessions = [x[x.index('-s') + 1] for x in self.records('tmux') if x[0] == 'new-session']
        self.assertEqual(len(set(sessions)), 2)

    def test_hooks_report_failures_without_leaving_files_in_either_mode(self):
        project = self.projects[0]
        (project / 'agents/hooks').mkdir(parents=True)
        (project / 'agents/hooks/check.conf').write_text('LINT_PY=none\nTEST_CMD=none\n')
        source = project / 'source.py'
        data = json.dumps({'tool_input': {'file_path': str(source)}})
        hook = KIT / 'templates/project/agents/hooks/post-edit-check.sh'
        for mode in ('0', '1'):
            env = dict(self.env, CLAUDE_PROJECT_DIR=str(project), LLM_TASK_MANAGED=mode)
            source.write_text('value = 1\n')
            self.call('bash', hook, data=data, env=env)
            self.assertEqual(sorted(p.name for p in (project / 'agents/hooks').iterdir()), ['check.conf'])
            source.write_text('def broken(:\n')
            result = self.call('bash', hook, data=data, env=env, code=2)
            self.assertIn('[syntax]', result.stderr)
            self.assertFalse((project / 'agents/hooks/last-check.log').exists())
