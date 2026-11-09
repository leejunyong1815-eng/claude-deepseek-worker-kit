"""Registry, owned pools and actual managed processes; no model/server required."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
KIT = Path(__file__).resolve().parents[1]
from _worker_pool import create, manifest, stop
MOCK = "#!/usr/bin/env python3\nimport json,os,sys,time\nfrom pathlib import Path\nif '--version' in sys.argv:print('2.1.314');raise SystemExit(0)\nif '--help' in sys.argv:print('--name --disallowedTools --system-prompt-snapshot');raise SystemExit(0)\nPath(os.environ['CALL_MARKER']).touch()\nassert '--dangerously-skip-permissions' not in sys.argv\nprompt=sys.argv[sys.argv.index('-p')+1]\nargs=json.loads(prompt.rsplit('\\n\\n',1)[1])\np=Path('reports');p.mkdir(exist_ok=True)\n(p/'model.txt').write_text(os.environ['ANTHROPIC_MODEL'])\nprint(os.environ.get('ANTHROPIC_AUTH_TOKEN',''),file=sys.stderr)\ntime.sleep(args.get('sleep',0))\nprint(json.dumps({'is_error':False,'result':'done'}))\n"

class Pools(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / 'project'
        self.repo.mkdir()
        (self.repo / 'source.txt').write_text('base')
        self.mock = self.root / 'mock'
        self.mock.mkdir()
        (self.mock / 'claude').write_text(MOCK)
        (self.mock / 'claude').chmod(493)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('LLM_', 'DEEPSEEK_', 'CLAUDE_', 'GIT_', 'ANTHROPIC_'))}
        self.env.update(HOME=str(self.root / 'home'), PATH=str(self.mock) + os.pathsep + os.environ['PATH'], LLM_WORKER_CONF_DIR=str(self.root / 'conf'), XDG_STATE_HOME=str(self.root / 'state'), LLM_POOL_HOME=str(self.root / 'pools'), CALL_MARKER=str(self.root / 'called'), PYTHONDONTWRITEBYTECODE='1', LLM_MODEL='mock-default')
        self.call(KIT / 'install.sh', '--non-interactive', '--prefix', self.root / 'installed')
        self.call('git', 'init', '-q', cwd=self.repo)
        self.call('git', 'add', 'source.txt', cwd=self.repo)
        self.call('git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@local', 'commit', '-qm', 'base', cwd=self.repo)
        self.children = []
        self.pool_dirs = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        with patch.dict(os.environ, self.env, clear=True):
            for folder in self.pool_dirs:
                stop(folder)
        for p in self.children:
            try:
                p.communicate(timeout=8)
            except subprocess.TimeoutExpired:
                p.terminate()
                p.communicate(timeout=4)

    def call(self, *args, cwd=KIT, env=None, code=0):
        r = subprocess.run(list(map(str, args)), cwd=cwd, env=env or self.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        return r

    def add(self, name, model, **kwargs):
        env = dict(self.env, TEST_PRIVATE_KEY='private-' + name + '-secret-123456')
        return self.call(KIT / 'bin/llm-backend', 'add', name, '--url', 'https://' + name + '.invalid', '--model', model, '--auth', 'api_key', '--key-env', 'TEST_PRIVATE_KEY', env=env, **kwargs)

    def pool(self, backends=None, labels=None, count='2'):
        with patch.dict(os.environ, self.env, clear=True):
            folder, data = create(self.repo, 'codex', count, backends or ['default'], [], [], labels or [], 'my suffix')
        self.pool_dirs.append(folder)
        return (folder, data)

    def submit(self, folder, model=None, role='implementer', **extra):
        env = dict(self.env, LLM_POOL_DIR=str(folder), LLM_TASK_HOME=str(folder / 'tasks'))
        spec = dict(purpose='pool fixture', repository=str(self.repo), instructions=json.dumps(extra), role=role, allowed_paths=['reports/'], verify=['test -s reports/model.txt'], timeout=8, verify_timeout=2)
        if model:
            spec['model'] = model
        path = self.root / ('spec-' + str(time.monotonic_ns()) + '.json')
        path.write_text(json.dumps(spec))
        task = self.call(KIT / 'bin/worker-task', 'submit', path, env=env).stdout.strip()
        return (task, env)

    def serve(self, folder, slot):
        p = subprocess.Popen([str(KIT / 'bin/llm-worker'), 'serve', '--pool-dir', str(folder), '--worker-id', slot['worker_id']], env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.children.append(p)
        return p

    def result(self, task, env):
        return json.loads(self.call(KIT / 'bin/worker-task', 'wait', task, '--timeout', '10', env=env).stdout)

    def test_multiple_servers_models_and_private_credentials_survive_update(self):
        result = self.add('one', 'model-one')
        self.add('two', 'model-two')
        self.assertNotIn('private-one-secret', result.stdout + result.stderr)
        self.call(KIT / 'bin/llm-backend', 'model-add', 'one', 'review-one', '--roles', 'reviewer', '--context', '65536')
        listed = json.loads(self.call(KIT / 'bin/llm-backend', 'list').stdout)
        self.assertNotIn('private-', json.dumps(listed))
        self.assertEqual(len(next((x for x in listed if x['name'] == 'one'))['models']), 2)
        self.assertEqual((self.root / 'conf/backends/one.json').stat().st_mode & 511, 384)
        before = (self.root / 'conf/backends/one.json').read_bytes()
        self.call(KIT / 'install.sh', '--update', '--prefix', self.root / 'installed')
        self.assertEqual((self.root / 'conf/backends/one.json').read_bytes(), before)
        self.add('one', 'model-one', code=2)

    def test_two_owned_workers_route_backend_models_and_preserve_source(self):
        self.add('one', 'model-one')
        self.add('two', 'model-two')
        labels = ['llm-worker-fast v2', 'llm-worker-내것 ;$(touch SHOULD_NOT_EXIST)']
        folder, data = self.pool(['one', 'two'], labels)
        for slot in data['workers']:
            self.serve(folder, slot)
        time.sleep(0.2)
        self.assertFalse((self.root / 'called').exists(), 'idle workers must not invoke the model')
        a, env = self.submit(folder, sleep=0.4)
        b, _ = self.submit(folder, sleep=0.4)
        one = self.result(a, env)
        two = self.result(b, env)
        self.assertEqual({one['worker_id'], two['worker_id']}, {w['worker_id'] for w in data['workers']})
        self.assertEqual({one['backend'], two['backend']}, {'one', 'two'})
        self.assertEqual({one['model'], two['model']}, {'model-one', 'model-two'})
        self.assertNotEqual(one['worktree'], two['worktree'])
        for record in (one, two):
            self.assertTrue(record['verification_valid'])
            self.assertNotIn('private-', Path(record['logs']['worker_stderr']).read_text())
        self.assertEqual(self.call('git', 'status', '--porcelain', cwd=self.repo).stdout, '')
        listed = json.loads(self.call(KIT / 'bin/llm-worker', 'list').stdout)
        self.assertEqual([s['label'] for s in listed[0]['workers']], labels)
        self.assertTrue(all((s['owned'] for s in listed[0]['workers'])))
        self.assertFalse((self.repo / 'SHOULD_NOT_EXIST').exists())

    def test_role_routing_uses_registered_model_without_name_guessing(self):
        self.add('one', 'implementation')
        self.call(KIT / 'bin/llm-backend', 'model-add', 'one', 'a-completely-different-name', '--roles', 'reviewer')
        folder, data = self.pool(['one'], count='1')
        self.serve(folder, data['workers'][0])
        task, env = self.submit(folder, role='reviewer')
        record = self.result(task, env)
        self.assertEqual(record['model'], 'a-completely-different-name')

    def test_auto_worker_allocation_honors_server_capacity(self):
        self.call_backend_capacity('small', 1)
        self.call_backend_capacity('large', 3)
        folder, data = self.pool(['small', 'large'], count='auto')
        self.assertEqual(len(data['workers']), 4)
        self.assertEqual(sum((w['backend'] == 'small' for w in data['workers'])), 1)
        self.assertEqual(sum((w['backend'] == 'large' for w in data['workers'])), 3)
        self.assertFalse((self.root / 'called').exists())

    def call_backend_capacity(self, name, capacity):
        self.call(KIT / 'bin/llm-backend', 'add', name, '--url', 'https://' + name + '.invalid', '--model', name, '--max-parallel', str(capacity))

    def test_launch_and_submit_from_a_repository_subdirectory(self):
        subdir=self.repo/'subdirectory';subdir.mkdir()
        with patch.dict(os.environ,self.env,clear=True):folder,data=create(subdir,'codex','1',['default'],[],[],[],'subdir')
        self.pool_dirs.append(folder);self.assertEqual(data['project'],str(self.repo))
        self.serve(folder,data['workers'][0])
        spec=self.root/'subdir-spec.json';spec.write_text(json.dumps(dict(purpose='subdir',repository=str(subdir),instructions='{}',allowed_paths=['reports/'],verify=['test -s reports/model.txt'])))
        env=dict(self.env,LLM_POOL_DIR=str(folder),LLM_TASK_HOME=data['state_dir'])
        task=self.call(KIT/'bin/worker-task','submit',spec,env=env).stdout.strip()
        self.assertEqual(self.result(task,env)['state'],'succeeded')

    def test_foreign_worker_id_and_project_are_not_owned(self):
        first, data = self.pool()
        second, other = self.pool()
        path = self.root / 'foreign.json'
        path.write_text(json.dumps(dict(purpose='foreign', repository=str(self.repo), instructions='bad', worker_id=other['workers'][0]['worker_id'], allowed_paths=['reports/'], verify=['true'])))
        env = dict(self.env, LLM_POOL_DIR=str(first), LLM_TASK_HOME=str(first / 'tasks'))
        self.call(KIT / 'bin/worker-task', 'submit', path, env=env, code=2)
        with patch.dict(os.environ, self.env, clear=True):
            changed = json.loads((first / 'pool.json').read_text())
            changed['owner_uid'] += 1
            (first / 'pool.json').write_text(json.dumps(changed))
            with self.assertRaises(ValueError):
                manifest(first)
            changed['owner_uid'] = os.getuid()
            (first / 'pool.json').write_text(json.dumps(changed))

    def test_explicit_profile_model_takes_precedence_over_automatic_role_routing(self):
        self.add('one', 'general-model')
        self.call(KIT / 'bin/llm-backend', 'model-add', 'one', 'profile-model')
        conf = self.root / 'conf'
        (conf / 'env.impl').write_text((conf / 'env').read_text().replace('mock-default', 'profile-model'))
        with patch.dict(os.environ, self.env, clear=True):
            folder, data = create(self.repo, 'codex', '1', ['one'], [], ['impl'], [], 'profile')
        self.pool_dirs.append(folder)
        self.serve(folder, data['workers'][0])
        task, env = self.submit(folder)
        self.assertEqual(self.result(task, env)['model'], 'profile-model')

    def test_default_backend_selection_and_unknown_model_fail_closed(self):
        self.add('one', 'model-one')
        self.call(KIT / 'bin/llm-backend', 'default', 'one')
        task_spec = self.root / 'standalone.json'
        task_spec.write_text(json.dumps(dict(purpose='standalone', repository=str(self.repo), instructions='{}', allowed_paths=['reports/'], verify=['test "$(cat reports/model.txt)" = model-one'])))
        task = self.call(KIT / 'bin/worker-task', 'submit', task_spec).stdout.strip()
        self.call(KIT / 'bin/worker-task', 'run', task)
        self.call(KIT / 'bin/llm-worker', '--backend', 'one', '--model', 'missing', '-p', '{}', code=2)

    def test_stopping_one_owned_pool_does_not_cancel_another(self):
        first, one = self.pool(count='1')
        second, two = self.pool(count='1')
        self.serve(first, one['workers'][0])
        self.serve(second, two['workers'][0])
        a, ea = self.submit(first, sleep=4)
        b, eb = self.submit(second, sleep=0.5)
        end = time.monotonic() + 5
        while time.monotonic() < end:
            state = json.loads((first / 'tasks' / a / 'state.json').read_text())
            if state['state'] == 'running' and state.get('child'):
                break
            time.sleep(0.03)
        with patch.dict(os.environ, self.env, clear=True):
            stop(first)
        cancelled = json.loads(self.call(KIT / 'bin/worker-task', 'wait', a, '--timeout', '6', env=ea, code=1).stdout)
        self.assertEqual(cancelled['state'], 'cancelled')
        self.assertEqual(self.result(b, eb)['state'], 'succeeded')

    def test_pool_task_command_keeps_ownership_when_main_shell_filters_environment(self):
        folder, data = self.pool(count='1')
        self.serve(folder, data['workers'][0])
        spec = self.root / 'filtered.json'
        spec.write_text(json.dumps(dict(purpose='filtered shell', repository=str(self.repo), instructions='{}', allowed_paths=['reports/'], verify=['test -s reports/model.txt'])))
        minimal = {'HOME': self.env['HOME'], 'PATH': os.defpath, 'LANG': 'C.UTF-8'}
        task = self.call(folder / 'worker-task', 'submit', spec, env=minimal).stdout.strip()
        record = json.loads(self.call(folder / 'worker-task', 'wait', task, '--timeout', '10', env=minimal).stdout)
        self.assertEqual(record['state'], 'succeeded')
        self.assertEqual(record['worker_id'], data['workers'][0]['worker_id'])

    def main_driver(self):
        script = self.root / 'main-driver.py'
        script.write_text("import json,os,subprocess,sys\nfrom pathlib import Path\npool=json.loads((Path(os.environ['LLM_POOL_DIR'])/'pool.json').read_text())\nids=[]\nfor i in range(2):\n spec=dict(purpose='main delegation',repository=pool['project'],instructions='{}',allowed_paths=['reports/'],verify=['test -s reports/model.txt'])\n p=Path(os.environ['LLM_POOL_DIR'])/('spec%d.json'%i);p.write_text(json.dumps(spec))\n ids.append(subprocess.check_output(['worker-task','submit',str(p)],text=True).strip())\nresults=[json.loads(subprocess.check_output(['worker-task','wait',tid,'--timeout','10'],text=True)) for tid in ids]\nPath(os.environ['MAIN_CAPTURE']).write_text(json.dumps({'args':sys.argv[1:],'pool':pool,'states':[r['state'] for r in results]}))\nprint('MAIN_FINISHED')\n")
        self.env['MAIN_CAPTURE'] = str(self.root / 'main-capture.json')
        code = '#!/usr/bin/env python3\nimport runpy\nrunpy.run_path(' + repr(str(script)) + ',run_name="__main__")\n'
        (self.mock / 'codex').write_text(code)
        (self.mock / 'codex').chmod(493)
        combined = '#!/usr/bin/env python3\nimport os,runpy\nif os.environ.get("LLM_TASK_MANAGED") != "1":\n runpy.run_path(' + repr(str(script)) + ',run_name="__main__");raise SystemExit(0)\n' + MOCK.split('\n', 1)[1]
        (self.mock / 'claude').write_text(combined)

    def test_headless_codex_and_claude_use_the_same_pool_and_actual_task_runner(self):
        self.main_driver()
        for kind in ('codex', 'claude'):
            result = self.call(KIT / ('bin/' + kind + '-duo'), '--headless', '-w', '2', '내 풀 ;$(touch INJECTED)', cwd=self.repo)
            self.assertIn('MAIN_FINISHED', result.stdout)
            capture = json.loads(Path(self.env['MAIN_CAPTURE']).read_text())
            self.assertEqual(capture['states'], ['succeeded', 'succeeded'])
            self.assertEqual(capture['pool']['label'], '내 풀 ;$(touch INJECTED)')
            self.assertEqual(capture['pool']['native_agents'], 'selective')
            args = capture['args']
            if kind == 'codex':
                self.assertIn('features.multi_agent=true', args)
                self.assertIn('agents.enabled=true', args)
                self.assertTrue(any((x.startswith('developer_instructions=') and 'worker-task wait' in x for x in args)))
                self.assertIn('--add-dir', args)
            else:
                self.assertIn('--disallowedTools', args)
                denied = args[args.index('--disallowedTools') + 1:args.index('--system-prompt-snapshot')]
                self.assertNotIn('Agent', denied)
            self.assertFalse((self.repo / 'INJECTED').exists())
            self.assertEqual(self.call('git', 'status', '--porcelain', cwd=self.repo).stdout, '')

    def test_explicit_off_keeps_actual_managed_delegation_in_both_mains(self):
        self.main_driver()
        for kind in ('codex', 'claude'):
            options = ['--native-agents', 'off'] if kind == 'claude' else ['--', '--native-agents', 'off']
            self.call(KIT / ('bin/' + kind + '-duo'), '-w', '2', *options, cwd=self.repo)
            capture = json.loads(Path(self.env['MAIN_CAPTURE']).read_text())
            self.assertEqual(capture['states'], ['succeeded', 'succeeded'])
            self.assertEqual(capture['pool']['native_agents'], 'off')
            args = capture['args']
            if kind == 'codex':
                self.assertIn('agents.enabled=false', args)
                self.assertIn('features.multi_agent=false', args)
            else:
                denied = args[args.index('--disallowedTools') + 1:args.index('--system-prompt-snapshot')]
                self.assertIn('Agent', denied)
            self.assertEqual(self.call('git', 'status', '--porcelain', cwd=self.repo).stdout, '')

    def test_pane_commands_quote_paths_and_treat_labels_as_data(self):
        self.main_driver()
        log = self.root / 'tmux.jsonl'
        self.env['TMUX_CAPTURE'] = str(log)
        (self.mock / 'tmux').write_text("#!/usr/bin/env python3\nimport json,os,sys\nwith open(os.environ['TMUX_CAPTURE'],'a') as f:f.write(json.dumps(sys.argv[1:])+'\\n')\nif sys.argv[1]=='split-window':print('%1')\n")
        (self.mock / 'tmux').chmod(493)
        self.call(KIT / 'bin/codex-duo', '--panes', '--no-attach', '-w', '2', '--label', 'llm-worker x;$(touch PWN)', cwd=self.repo)
        rows = [json.loads(x) for x in log.read_text().splitlines()]
        self.assertEqual(sum((x[0] == 'split-window' for x in rows)), 2)
        self.assertTrue(any((x[0] == 'select-pane' and 'x;$(touch PWN)' in x[-1] for x in rows)))
        self.assertFalse((self.repo / 'PWN').exists())

    def test_explicit_preflight_checks_selectable_models_and_keeps_named_main(self):
        from _duo import launch
        self.main_driver()
        self.call(KIT / 'install.sh', '--non-interactive', '--profile', 'impl', '--prefix', self.root / 'installed')
        probes = []
        original = subprocess.run

        def run(command, **kwargs):
            if Path(command[0]).name == 'llm-probe':
                probes.append(command)
                self.assertFalse((self.root / 'called').exists(), 'probe must precede workers')
                return subprocess.CompletedProcess(command, 0)
            return original(command, **kwargs)

        with patch.dict(os.environ, self.env, clear=True), patch('_duo.subprocess.run', side_effect=run):
            self.assertEqual(launch('claude', ['-C', str(self.repo), '-w', '2', '-P', 'impl', '-n', 'named-main', '--probe']), 0)
        models = [x[x.index('--model') + 1] for x in probes]
        self.assertEqual(set(models), {'mock-default', 'qwen3.8-flash-next'})
        self.assertEqual(len(models), len(set(models)))
        capture = json.loads(Path(self.env['MAIN_CAPTURE']).read_text())
        args = capture['args']
        self.assertEqual(args[args.index('--name') + 1], 'named-main')
        self.assertEqual(capture['states'], ['succeeded', 'succeeded'])

    def test_failed_preflight_never_starts_main_or_workers(self):
        from _duo import launch
        original = subprocess.run

        def run(command, **kwargs):
            if Path(command[0]).name == 'llm-probe':
                raise subprocess.CalledProcessError(1, command)
            return original(command, **kwargs)

        with patch.dict(os.environ, self.env, clear=True), patch('_duo.subprocess.run', side_effect=run):
            with self.assertRaises(subprocess.CalledProcessError):
                launch('claude', ['-C', str(self.repo), '-w', '2', '--probe'])
        self.assertFalse((self.root / 'called').exists())
        folders = list((self.root / 'pools').glob('*'))
        self.assertEqual(len(folders), 1)
        self.assertTrue((folders[0] / 'STOP').exists())
if __name__ == '__main__':
    unittest.main()
