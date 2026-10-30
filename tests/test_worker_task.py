"""Offline integration tests: real Git worktrees + real wrappers + mock Claude."""
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import unittest


KIT = Path(__file__).resolve().parents[1]
CLI = KIT / "bin/deepseek-task"
MOCK = r'''#!/usr/bin/env python3
import json, os, subprocess, sys, time
from pathlib import Path
if '--version' in sys.argv:
    print('2.1.312 (mock)'); sys.exit(0)
assert '--dangerously-skip-permissions' not in sys.argv
assert '--permission-mode' not in sys.argv
if os.environ.get('DEEPSEEK_WORKER_SETTINGS'):
    from pathlib import Path
    settings_path=Path(os.environ['DEEPSEEK_WORKER_SETTINGS'])
    assert settings_path.is_file() and settings_path.parent != Path.cwd()
    assert sys.argv.count('--settings') == 1
    assert sys.argv[sys.argv.index('--settings')+1] == str(settings_path)
    settings=json.loads(settings_path.read_text())
    assert settings['permissions']['defaultMode'] == 'dontAsk'
    assert sys.argv[sys.argv.index('--tools')+1] == 'default'

assert not os.environ.get('CLAUDECODE')
assert not os.environ.get('CLAUDE_CODE_SESSION_ID')
assert not os.environ.get('CLAUDE_CODE_CHILD_SESSION')
assert os.environ['ANTHROPIC_MODEL'] == 'mock-model'
assert os.environ['CLAUDE_CODE_EFFORT_LEVEL'] == os.environ['DEEPSEEK_WORKER_EFFORT']
assert sys.argv[sys.argv.index('--effort') + 1] == os.environ['DEEPSEEK_WORKER_EFFORT']
assert sys.argv[sys.argv.index('--max-turns') + 1] == '120'
assert os.environ['DEEPSEEK_WORKER_ROLE'] in sys.argv[sys.argv.index('-p') + 1]
for tier in ('OPUS', 'SONNET', 'HAIKU', 'FABLE'):
    assert os.environ['ANTHROPIC_DEFAULT_' + tier + '_MODEL'] == 'mock-model'
assert os.environ['CLAUDE_CODE_SUBAGENT_MODEL'] == 'mock-model'
assert not os.environ.get('MAX_THINKING_TOKENS')
prompt = sys.argv[sys.argv.index('-p') + 1]
args = json.loads(prompt.rsplit('\n\n', 1)[1])
mode = args.get('mode', 'edit')
if mode == 'new_module':
    Path('src/generated.py').write_text('def twice(value):\n    return value * 2\n')
elif mode != 'candidate':
    Path('src/value.txt').write_text(args.get('value', 'worker'))
if mode == 'candidate':
    Path('candidate-tests').mkdir()
    Path('candidate-tests/test_candidate.py').write_text('assert 2 + 2 == 4\n')
if mode == 'symlink_output':
    Path('src/link.txt').symlink_to('value.txt')
if mode == 'input_edit':
    next(Path('.task-inputs').rglob('value.txt')).write_text('tampered')
if mode == 'consume':
    data = next(Path('.task-inputs').rglob('value.txt')).read_text()
    assert data == 'worker'
    Path('src/review.txt').write_text('reviewed: ' + data)
if mode == 'outside': Path('outside.txt').write_text('bad')
if mode == 'ignored': Path('ignored.txt').write_text('bad')
if mode == 'protected': Path('tests/check.txt').write_text('bad')
if mode == 'deleted': Path('tests/check.txt').unlink()
if mode == 'config': Path('config/check.txt').write_text('bad')
if mode == 'control': Path('.git').write_text('gitdir: /does/not/exist\n')
if mode == 'hook':
    Path('src/module.py').write_text('x = 1\n')
    subprocess.run(['bash', 'agents/hooks/post-edit-check.sh'], input=json.dumps({'tool_input': {'file_path': str(Path('src/module.py').resolve())}}), text=True, check=True)
if mode == 'background':
    subprocess.Popen([sys.executable, '-c', "import time; from pathlib import Path; time.sleep(1); Path('src/late.txt').write_text('late'); time.sleep(30)"])
if mode == 'untracked': Path('src/new.txt').write_text('new')
if mode == 'commit':
    subprocess.run(['git', 'add', 'src'], check=True, stdout=sys.stderr)
    subprocess.run(['git', '-c', 'user.name=Mock', '-c', 'user.email=mock@local', 'commit', '-qm', 'worker commit'], check=True)
if mode == 'sleep': time.sleep(30)
if mode == 'secret':
    print(os.environ['ANTHROPIC_AUTH_TOKEN'], file=sys.stderr)
    Path('src/value.txt').write_text(os.environ['ANTHROPIC_AUTH_TOKEN'])
if mode == 'settings_edit':
    Path(os.environ['DEEPSEEK_WORKER_SETTINGS']).write_text('{}')
if mode in ('permission_denied','permission_denied_exit'):
    print(json.dumps({'is_error':False,'permission_denials':[{'tool_name':'Write','tool_input':{'content':os.environ['ANTHROPIC_AUTH_TOKEN']}}]}))
    sys.exit(7 if mode == 'permission_denied_exit' else 0)
if mode == 'external_read':
    assert Path(args['input']).read_text() == 'dataset fixture'
    assert any(args['input'] in rule for rule in settings['permissions']['allow'])
    assert any(args['input'] in rule for rule in settings['permissions']['deny'])
if mode == 'nonzero': sys.exit(7)
if mode == 'invalid': print('Tests passed!'); sys.exit(0)
print(json.dumps({'is_error': mode == 'model_error', 'result': 'all tests passed'}))
'''


class ManagedTasks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.store = self.root / "state"
        self.mock = self.root / "mock"
        self.mock.mkdir()
        (self.mock / "claude").write_text(MOCK)
        (self.mock / "claude").chmod(0o755)
        conf = self.root / "conf"
        conf.mkdir()
        config = 'export LLM_BASE_URL=http://unused.invalid\nexport LLM_API_KEY=offline-secret-12345\nexport LLM_MODEL=mock-model\nexport LLM_CONTEXT_WINDOW=32000\n'
        (conf / "env").write_text(config)
        (conf / "env.impl").write_text(config)
        self.env = dict(os.environ, PATH=str(self.mock) + os.pathsep + os.environ["PATH"],
                        DEEPSEEK_WORKER_CONF_DIR=str(conf), PYTHONDONTWRITEBYTECODE="1")
        # Do not inherit the test runner's Git overrides.
        for key in list(self.env):
            if key.startswith("GIT_"):
                del self.env[key]
        self.git("init", "-q")
        self.git("config", "user.name", "Tests")
        self.git("config", "user.email", "tests@local")
        for folder in ("src", "tests", "config"):
            (self.repo / folder).mkdir()
        for name in ("src/value.txt", "src/other.txt", "tests/check.txt", "config/check.txt"):
            (self.repo / name).write_text("base")
        (self.repo / ".gitignore").write_text("ignored.txt\n")
        self.git("add", ".")
        self.git("commit", "-qm", "base")
        self.processes = []
        self.addCleanup(self.cleanup_processes)

    def cleanup_processes(self):
        # Ask the task runner to clean its own process group before test teardown.
        if self.store.exists():
            for task in self.store.glob("t-*"):
                self.call("cancel", task.name, check=False)
        for p in self.processes:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], env=self.env)

    def call(self, *args, check=True):
        p = subprocess.run([str(CLI), "--state-dir", str(self.store), *map(str, args)],
                           env=self.env, capture_output=True, text=True, timeout=12)
        if check and p.returncode:
            self.fail(f"{args}: {p.returncode}\n{p.stdout}\n{p.stderr}")
        return p

    def submit(self, mode="edit", **overrides):
        spec = dict(purpose="offline task", repository=str(self.repo), profile="impl",
                    instructions=json.dumps({"mode": mode}), references=["src/value.txt"],
                    allowed_paths=["src/"], protected_paths=["tests/"],
                    verify=["test \"$(cat src/value.txt)\" = worker"], timeout=5, verify_timeout=3)
        spec.update(overrides)
        path = self.root / "spec.json"
        path.write_text(json.dumps(spec))
        p = self.call("submit", path)
        self.assertRegex(p.stdout.strip(), r"^t-[a-f0-9]{32}$")
        return p.stdout.strip()

    def status(self, task):
        return json.loads(self.call("status", task).stdout)

    def start(self, task):
        p = subprocess.Popen([str(CLI), "--state-dir", str(self.store), "run", task], env=self.env,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.processes.append(p)
        return p

    def wait_for(self, task, predicate):
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            state = self.status(task)
            if predicate(state):
                return state
            time.sleep(0.03)
        self.fail(f"task {task} never reached expected state: {state}")

    def worker_started(self, state):
        return state.get("child") and Path(state["worktree"], "src/value.txt").read_text() == "worker"

    def run_task(self, task, success=True, *extra):
        p = self.call("run", task, *extra, check=False)
        self.assertEqual(p.returncode, 0 if success else 1, p.stderr + p.stdout)
        return json.loads(p.stdout)

    def test_role_and_effort_recorded_and_sent_to_actual_cli(self):
        for role in ("planner", "researcher", "implementer", "test-author", "runner", "analyst", "reviewer"):
            state = self.run_task(self.submit(role=role, effort="max"))
            self.assertEqual(state["role"], role)
            self.assertEqual(state["effort"], "max")
        state = self.run_task(self.submit(role="reviewer", effort="high"))
        self.assertEqual(state["effort"], "high")

    def test_verified_producer_inputs_are_copied_and_protected(self):
        producer = self.submit()
        first = self.run_task(producer)
        consumer = self.submit("consume", role="reviewer", inputs=[{"task_id": producer, "paths": ["src/value.txt"]}])
        result = self.run_task(consumer)
        self.assertEqual(result["inputs"][0]["attempt_id"], first["attempt_id"])
        copied = Path(result["worktree"]) / ".task-inputs" / producer / "src/value.txt"
        self.assertEqual(copied.read_text(), "worker")
        self.assertFalse(copied.is_symlink())
        self.assertNotEqual(copied.stat().st_ino, (Path(first["worktree"]) / "src/value.txt").stat().st_ino)
        self.assertEqual(self.status(producer)["state"], "succeeded")
        bad = self.submit("input_edit", inputs=[{"task_id": producer, "paths": ["src/value.txt"]}], allowed_paths=["*"])
        bad_result = self.run_task(bad, False)
        self.assertEqual(bad_result["reason"], "path_policy_violation")
        self.assertEqual(self.status(producer)["state"], "succeeded")

    def test_stale_or_failed_producer_is_never_consumed(self):
        producer = self.submit()
        state = self.run_task(producer)
        task = self.submit("consume", inputs=[{"task_id": producer, "paths": ["src/value.txt"]}])
        (Path(state["worktree"]) / "src/value.txt").write_text("changed after success")
        result = self.run_task(task, False)
        self.assertEqual(result["reason"], "execution_error")
        self.assertIsNone(result["worker_exit_code"])
        self.assertIn("input", result["error"])
        spec = self.root / "spec.json"
        for source in (producer, self.submit("model_error")):
            raw = dict(purpose="review", repository=str(self.repo), instructions="review", allowed_paths=["reports/"],
                       verify=["true"], inputs=[{"task_id": source, "paths": ["src/value.txt"]}])
            spec.write_text(json.dumps(raw))
            self.assertEqual(self.call("submit", spec, check=False).returncode, 2)

    def test_symlink_input_refused_even_from_successful_task(self):
        producer = self.submit("symlink_output")
        self.run_task(producer)
        spec = self.root / "bad-link.json"
        spec.write_text(json.dumps(dict(purpose="review", repository=str(self.repo), instructions="review",
            allowed_paths=["reports/"], verify=["true"], inputs=[{"task_id": producer, "paths": ["src/link.txt"]}])))
        self.assertEqual(self.call("submit", spec, check=False).returncode, 2)

    def test_test_author_candidates_cannot_replace_acceptance_tests(self):
        task = self.submit("candidate", role="test-author", allowed_paths=["candidate-tests/"],
                           verify=["python3 -B candidate-tests/test_candidate.py"])
        result = self.run_task(task)
        self.assertEqual(result["role"], "test-author")
        self.assertEqual((Path(result["worktree"]) / "tests/check.txt").read_text(), "base")
        result = self.run_task(self.submit("protected", role="test-author", allowed_paths=["*"]), False)
        self.assertEqual(result["reason"], "path_policy_violation")

    def test_input_symlink_and_unsubmitted_paths_refused(self):
        producer = self.submit()
        self.run_task(producer)
        for path in ("../outside", "tests/check.txt", "src/", ".git", "/absolute"):
            spec = self.root / "bad-input.json"
            spec.write_text(json.dumps(dict(purpose="review", repository=str(self.repo), instructions="review",
                allowed_paths=["reports/"], verify=["true"], inputs=[{"task_id": producer, "paths": [path]}])))
            self.assertEqual(self.call("submit", spec, check=False).returncode, 2)

    def test_worker_permissions_are_runtime_files_outside_worktree(self):
        state=self.run_task(self.submit())
        self.assertEqual(state['permission_profile'],'workspace')
        self.assertTrue(Path(state['worker_settings_path']).is_file())
        self.assertFalse(Path(state['worker_settings_path']).is_relative_to(Path(state['worktree'])))
        self.assertEqual(state['permission_denial_count'],0)
        state=self.run_task(self.submit(permission_profile='inherit'))
        self.assertIsNone(state['worker_settings_path'])

    def test_permission_denials_are_failures_and_not_natural_language_success(self):
        state=self.run_task(self.submit('permission_denied'),False)
        self.assertEqual(state['reason'],'permission_denied')
        self.assertEqual(state['permission_denial_count'],1)
        self.assertEqual(state['permission_denied_tools'],['Write'])
        self.assertFalse(state['verification_valid'])
        self.assertNotIn('offline-secret',json.dumps(state))
        state=self.run_task(self.submit('permission_denied_exit'),False)
        self.assertEqual(state['reason'],'permission_denied')
        self.assertEqual(state['worker_exit_code'],7)

    def test_external_data_and_proposed_settings_are_frozen_at_submit(self):
        data=self.root/'external dataset.txt';data.write_text('dataset fixture')
        proposed=self.root/'proposed-settings.json'
        proposed.write_text(json.dumps({'permissions':{'deny':['Bash(pip *)']}}))
        task=self.submit('external_read',instructions=json.dumps({'mode':'external_read','input':str(data)}),
                         read_paths=[str(data)],permissions_file=str(proposed))
        proposed.write_text('{}')
        state=self.run_task(task)
        settings=json.loads(Path(state['worker_settings_path']).read_text())
        self.assertIn('Bash(pip *)',settings['permissions']['deny'])
        self.assertEqual(data.read_text(),'dataset fixture')
        self.assertEqual(self.git('status','--porcelain'),b'')

    def test_worker_settings_tampering_invalidates_verification(self):
        state=self.run_task(self.submit('settings_edit'),False)
        self.assertEqual(state['reason'],'permission_settings_changed')
        state=self.run_task(self.submit())
        Path(state['worker_settings_path']).write_text('{}')
        self.assertEqual(self.status(state['task_id'])['state'],'failed')

    def test_workspaces_separate_and_original_dirty_preserved(self):
        (self.repo / "src/value.txt").write_text("staged")
        self.git("add", "src/value.txt")
        (self.repo / "src/value.txt").write_text("unstaged")
        (self.repo / "personal.txt").write_text("untracked")
        before = [self.git("rev-parse", "HEAD"), self.git("symbolic-ref", "HEAD"),
                  (self.repo / ".git/index").read_bytes(), self.git("diff", "--binary"),
                  self.git("diff", "--cached", "--binary"), self.git("status", "--porcelain", "-z")]
        a, b = self.submit(), self.submit()
        pa, pb = self.start(a), self.start(b)
        self.assertEqual(pa.wait(timeout=8), 0)
        self.assertEqual(pb.wait(timeout=8), 0)
        sa, sb = self.status(a), self.status(b)
        self.assertEqual(sa["state"], "succeeded")
        self.assertNotEqual(sa["worktree"], sb["worktree"])
        self.assertNotEqual(sa["logs"], sb["logs"])
        self.assertFalse(sa["uncommitted_changes_included"])
        after = [self.git("rev-parse", "HEAD"), self.git("symbolic-ref", "HEAD"),
                 (self.repo / ".git/index").read_bytes(), self.git("diff", "--binary"),
                 self.git("diff", "--cached", "--binary"), self.git("status", "--porcelain", "-z")]
        self.assertEqual(before, after)
        self.assertEqual((self.repo / "personal.txt").read_text(), "untracked")

    def test_dirty_dependency_blocked_and_missing_reference_fails(self):
        (self.repo / "new.py").write_text("uncommitted")
        task = self.submit(depends_on_uncommitted=True)
        self.assertEqual(self.call("run", task, check=False).returncode, 2)
        self.assertEqual(self.status(task)["reason"], "uncommitted_dependency")
        task = self.submit(references=["new.py"])
        self.assertEqual(self.run_task(task, False)["reason"], "execution_error")

    def test_duplicate_run_and_retry_preserves_attempt(self):
        task = self.submit("sleep", timeout=0.5)
        p = self.start(task)
        self.wait_for(task, self.worker_started)
        self.assertEqual(self.call("run", task, check=False).returncode, 2)
        self.assertEqual(p.wait(timeout=5), 1)
        old = (self.store / task / "attempts/0001/result.json").read_bytes()
        state = self.run_task(task, False, "--retry")
        self.assertEqual(state["attempts"], ["0001", "0002"])
        self.assertEqual((self.store / task / "attempts/0001/result.json").read_bytes(), old)
        self.assertTrue(Path(state["worktree"]).exists())

    def test_zero_worker_exit_does_not_override_verifier_failure(self):
        task = self.submit(verify=["echo '100 passed'; exit 3"])
        state = self.run_task(task, False)
        self.assertEqual(state["reason"], "verification_exit_nonzero")
        self.assertEqual(state["worker_exit_code"], 0)
        self.assertEqual(state["verification_exit_codes"], [3])
        state = self.run_task(self.submit(verify=["false | echo 'passed'"]), False)
        self.assertEqual(state["verification_exit_codes"], [1])

    def test_policy_outside_protected_deleted_and_ignored(self):
        for mode, path in [("outside", "outside.txt"), ("protected", "tests/check.txt"),
                           ("deleted", "tests/check.txt"), ("config", "config/check.txt"),
                           ("ignored", "ignored.txt")]:
            with self.subTest(mode=mode):
                state = self.run_task(self.submit(mode, allowed_paths=["*"]), False) if mode in {"protected", "deleted", "config"} else self.run_task(self.submit(mode), False)
                self.assertEqual(state["reason"], "path_policy_violation")
                self.assertIn(path, state["policy_violations"])

    def test_untracked_file_and_self_commit_in_result_and_diff(self):
        for mode in ("untracked", "commit"):
            with self.subTest(mode=mode):
                state = self.run_task(self.submit(mode))
                paths = [c["path"] for c in state["changed_files"]]
                self.assertIn("src/value.txt", paths)
                if mode == "untracked":
                    self.assertIn("src/new.txt", paths)
                    self.assertIn("new.txt", Path(state["diff_path"]).read_text())
                self.assertIn("worker", Path(state["diff_path"]).read_text())

    def test_separate_timeouts(self):
        state = self.run_task(self.submit("sleep", timeout=0.2), False)
        self.assertEqual(state["reason"], "worker_timeout")
        self.assertTrue(state["worker_timed_out"])
        self.assertFalse(state["verification_timed_out"])
        state = self.run_task(self.submit(verify=["sleep 30"], verify_timeout=0.2), False)
        self.assertEqual(state["reason"], "verification_timeout")
        self.assertFalse(state["worker_timed_out"])
        self.assertTrue(state["verification_timed_out"])

    def test_cancel_only_one_task(self):
        a, b = self.submit("sleep"), self.submit("sleep")
        pa, pb = self.start(a), self.start(b)
        self.wait_for(a, self.worker_started)
        self.wait_for(b, self.worker_started)
        self.call("cancel", a)
        self.assertEqual(pa.wait(timeout=5), 1)
        self.assertEqual(self.status(a)["state"], "cancelled")
        self.assertIsNone(pb.poll())
        self.assertEqual(self.status(b)["state"], "running")
        self.call("cancel", b)
        pb.wait(timeout=5)

    def test_recover_dead_runner_no_auto_rerun(self):
        task = self.submit("sleep")
        p = self.start(task)
        self.wait_for(task, self.worker_started)
        p.kill()
        p.wait(timeout=3)
        state = self.status(task)
        self.assertEqual(state["state"], "interrupted")
        self.assertEqual(state["reason"], "runner_lost")
        self.assertTrue(state["surviving_processes"])
        self.assertEqual(self.call("run", task, "--retry", check=False).returncode, 2)
        self.call("cancel", task)
        recovered = self.status(task)
        self.assertFalse(recovered["surviving_processes"])
        self.assertTrue(recovered["artifacts_complete"])
        self.assertIn("src/value.txt", [c["path"] for c in recovered["changed_files"]])
        self.assertIn("worker", Path(recovered["diff_path"]).read_text())

    def test_success_invalidated_after_edit_and_during_verification(self):
        task = self.submit()
        state = self.run_task(task)
        Path(state["worktree"], "src/value.txt").write_text("later")
        state = json.loads(self.call("result", task).stdout)
        self.assertEqual(state["reason"], "changed_after_verification")
        self.assertFalse(state["verification_valid"])
        state = self.run_task(self.submit(verify=["echo changed > src/value.txt"]), False)
        self.assertEqual(state["reason"], "changed_during_verification")

    def test_model_error_invalid_output_nonzero(self):
        for mode, reason in [("model_error", "model_error"), ("invalid", "invalid_worker_result"),
                             ("nonzero", "worker_exit_nonzero")]:
            with self.subTest(mode=mode):
                state = self.run_task(self.submit(mode), False)
                self.assertEqual(state["reason"], reason)
                self.assertEqual(state["verification_exit_codes"], [])

    def test_registered_spec_separate_and_secret_redaction(self):
        task = self.submit("secret", verify=["true"])
        state = self.run_task(task)
        for filename in [state["logs"]["worker_stderr"], state["diff_path"]]:
            text = Path(filename).read_text()
            self.assertNotIn("offline-secret-12345", text)
            self.assertIn("[REDACTED]", text)
        # Original spec file is copied on submit; later changes are not consulted.
        task = self.submit()
        (self.root / "spec.json").write_text('{}')
        self.run_task(task)
        task = self.submit()
        registered = self.store / task / "spec.json"
        spec = json.loads(registered.read_text())
        spec["verify"] = ["true"]
        registered.write_text(json.dumps(spec))
        self.assertEqual(self.call("run", task, check=False).returncode, 2)

    def test_control_file_and_background_children(self):
        state = self.run_task(self.submit("control", allowed_paths=["*"]), False)
        self.assertEqual(state["reason"], "path_policy_violation")
        self.assertIn(".git", state["policy_violations"])
        task = self.submit("background")
        state = self.run_task(task)
        time.sleep(1.1)
        self.assertFalse(Path(state["worktree"], "src/late.txt").exists())
        self.assertEqual(self.status(task)["state"], "succeeded")

    def test_managed_hook_leaves_no_cache_or_local_log(self):
        import shutil
        hook = self.repo / 'agents/hooks/post-edit-check.sh'
        hook.parent.mkdir(parents=True)
        shutil.copyfile(KIT / 'templates/project/agents/hooks/post-edit-check.sh', hook)
        self.git('add', 'agents')
        self.git('commit', '-qm', 'hook')
        self.env['CLAUDE_PROJECT_DIR'] = str(self.repo)
        self.env['LINT_PY'] = 'none'
        state = self.run_task(self.submit('hook'))
        self.assertFalse(Path(state['worktree'], 'agents/hooks/last-check.log').exists())
        self.assertFalse(list(Path(state['worktree']).rglob('__pycache__')))
        self.assertFalse((self.repo / 'agents/hooks/last-check.log').exists())

    def test_cancel_verification_and_runner_signal(self):
        task = self.submit(verify=["sleep 30"], verify_timeout=10)
        p = self.start(task)
        self.wait_for(task, lambda s: s["state"] == "verifying" and s.get("child"))
        self.call("cancel", task)
        self.assertEqual(p.wait(timeout=5), 1)
        self.assertEqual(self.status(task)["state"], "cancelled")
        self.assertFalse(self.status(task)["surviving_processes"])
        task = self.submit("sleep")
        p = self.start(task)
        self.wait_for(task, self.worker_started)
        p.send_signal(signal.SIGTERM)
        self.assertEqual(p.wait(timeout=5), 1)
        state = self.status(task)
        self.assertEqual(state["state"], "interrupted")
        self.assertEqual(state["reason"], "runner_signal")
        self.assertFalse(state["surviving_processes"])

    def test_spec_validation_profile_and_state_location(self):
        task = self.submit()
        self.assertEqual(self.call("run", task, "-P", "wrong", check=False).returncode, 2)
        self.assertEqual(self.status(task)["state"], "queued")
        p = subprocess.run([str(CLI), "--state-dir", str(self.repo / "forbidden"),
                            "submit", str(self.root / "spec.json")], env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertFalse((self.repo / "forbidden").exists())
        for values in ({"timeout": 0}, {"allowed_paths": ["../escape"]}, {"compute_backend": "ssh"},
                       {"verify": []}, {"instructions": "offline-secret-12345"}):
            with self.subTest(values=values):
                spec = json.loads((self.root / "spec.json").read_text())
                spec.update(values)
                path = self.root / "invalid.json"
                path.write_text(json.dumps(spec))
                self.assertEqual(self.call("submit", path, check=False).returncode, 2)

    def test_local_backend_and_independent_session_identity(self):
        self.env.update(CLAUDECODE="1", CLAUDE_CODE_SESSION_ID="parent-session",
                        CLAUDE_CODE_CHILD_SESSION="parent-child")
        task = self.submit()
        registered = json.loads((self.store / task / "spec.json").read_text())
        self.assertEqual(registered["compute_backend"], "local")
        state = self.run_task(task)
        self.assertEqual(state["compute_backend"], "local")

    def test_whole_module_creation_without_a_skeleton(self):
        (self.repo / "tests/test_generated.py").write_text(
            'import sys, unittest\nsys.path.insert(0, "src")\nfrom generated import twice\n'
            'class GeneratedTests(unittest.TestCase):\n'
            '    def test_contract(self):\n'
            '        self.assertEqual(twice(3), 6)\n'
            '        self.assertEqual(twice(-2), -4)\n')
        self.git("add", "tests/test_generated.py")
        self.git("commit", "-qm", "independent acceptance test, no implementation")
        self.assertFalse((self.repo / "src/generated.py").exists())
        task = self.submit("new_module", allowed_paths=["src/generated.py"],
                           references=["tests/test_generated.py"],
                           verify=["python3 -B -m unittest discover -s tests -p test_generated.py -v"])
        state = self.run_task(task)
        self.assertEqual(state["changed_files"], [{"path": "src/generated.py", "change": "added"}])
        self.assertEqual(state["verification_exit_codes"], [0])
        self.assertFalse((self.repo / "src/generated.py").exists())


if __name__ == "__main__":
    unittest.main()
