"""No network/model needed: configuration, namespaces and reasoning routing."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

KIT = Path(__file__).resolve().parents[1]


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.conf = self.root / 'conf'
        self.prefix = self.root / 'bin'
        mock = self.root / 'mock'
        mock.mkdir()
        (mock / 'claude').write_text('''#!/usr/bin/env python3
import json,os,sys
print(json.dumps({'args': sys.argv[1:], 'env': {k:v for k,v in os.environ.items() if k.startswith(('ANTHROPIC_', 'CLAUDE_CODE_')) or k == 'MAX_THINKING_TOKENS'}}))
''')
        (mock / 'curl').write_text('#!/bin/sh\ntouch "$NETWORK_MARKER"\nexit 99\n')
        for p in mock.iterdir():
            p.chmod(0o755)
        self.env = {k:v for k,v in os.environ.items() if not k.startswith(('LLM_', 'DEEPSEEK_', 'ANTHROPIC_'))}
        self.env.update(PATH=str(mock) + os.pathsep + os.environ['PATH'], DEEPSEEK_WORKER_CONF_DIR=str(self.conf),
                        NETWORK_MARKER=str(self.root / 'network'))

    def install(self, *args, code=0, config=False):
        env = dict(self.env)
        if config:
            env.update(LLM_BASE_URL='https://lab.invalid/anthropic', LLM_API_KEY="offline-key-quote'with$chars",
                       LLM_MODEL='lab-flash-alias', LLM_CONTEXT_WINDOW='65536')
        p = subprocess.run([str(KIT / 'install.sh'), '--prefix', str(self.prefix), *args],
                           env=env, text=True, capture_output=True, timeout=10)
        self.assertEqual(p.returncode, code, p.stdout + p.stderr)
        self.assertNotIn("offline-key-quote", p.stdout + p.stderr)
        self.assertFalse((self.root / 'network').exists())
        return p

    def test_install_only_without_server_and_fail_closed_execution(self):
        self.install('--install-only')
        self.assertFalse((self.conf / 'env').exists())
        self.assertFalse((self.prefix / 'claude-worker').exists())
        self.assertTrue((self.prefix / 'deepseek-task').is_file())
        p = subprocess.run([str(self.prefix / 'deepseek-worker'), '-p', 'hi'], env=self.env, capture_output=True)
        self.assertEqual(p.returncode, 2)
        self.install('--non-interactive', code=2)
        self.assertFalse((self.conf / 'env').exists())

    def test_lab_defaults_require_only_a_private_key(self):
        self.env['LLM_API_KEY'] = 'offline-default-key'
        self.install('--non-interactive')
        data = json.loads(subprocess.check_output([str(self.prefix / 'deepseek-worker'), '-p', 'hi'],
                                                  env=self.env, text=True))
        self.assertEqual(data['env']['ANTHROPIC_BASE_URL'], 'http://133.186.146.224:8081')
        self.assertEqual(data['env']['ANTHROPIC_MODEL'], 'DeepSeek-V4.1-Flash')
        self.assertEqual(data['env']['CLAUDE_CODE_MAX_CONTEXT_TOKENS'], '1048576')
        self.assertEqual(data['env']['ANTHROPIC_AUTH_TOKEN'], 'offline-default-key')

    def test_defaults_file_never_provides_credentials(self):
        defaults = json.loads((KIT / 'config/backend.defaults.json').read_text())
        self.assertEqual(set(defaults), {'LLM_BASE_URL', 'LLM_MODEL', 'LLM_CONTEXT_WINDOW'})
        result = self.install('--non-interactive', code=2)
        self.assertIn('LLM_API_KEY is required', result.stderr)

    def test_configuration_is_private_offline_and_all_tiers_use_exact_alias(self):
        self.install('--non-interactive', config=True)
        self.assertEqual((self.conf / 'env').stat().st_mode & 0o777, 0o600)
        p = subprocess.run([str(self.prefix / 'deepseek-worker'), '-p', 'hi'], env=self.env,
                           text=True, capture_output=True, check=True)
        data = json.loads(p.stdout)
        self.assertEqual(data['args'][data['args'].index('--effort') + 1], 'max')
        self.assertEqual(data['env']['ANTHROPIC_BASE_URL'], 'https://lab.invalid/anthropic')
        for tier in ('OPUS', 'SONNET', 'HAIKU', 'FABLE'):
            self.assertEqual(data['env'][f'ANTHROPIC_DEFAULT_{tier}_MODEL'], 'lab-flash-alias')
        self.assertIn('Implementer discipline', data['args'][data['args'].index('--append-system-prompt') + 1])

    def test_role_override_does_not_retain_implementer_instructions(self):
        self.install('--non-interactive', config=True)
        self.install('--profile', 'impl', '--non-interactive')
        env = dict(self.env, DEEPSEEK_WORKER_ROLE='reviewer', DEEPSEEK_WORKER_EFFORT='high')
        result = subprocess.check_output([str(self.prefix / 'deepseek-worker'), '-P', 'impl', '-p', 'hi'], env=env, text=True)
        data = json.loads(result)
        prompt = data['args'][data['args'].index('--append-system-prompt') + 1]
        self.assertIn('Independent reviewer', prompt)
        self.assertNotIn('Implementer discipline', prompt)
        self.assertEqual(data['env']['CLAUDE_CODE_EFFORT_LEVEL'], 'high')

    def test_orchestrator_does_not_inherit_worker_model_or_reasoning_settings(self):
        self.install('--install-only')
        env = dict(self.env, ANTHROPIC_BASE_URL='https://lab.invalid', ANTHROPIC_MODEL='deepseek',
                   ANTHROPIC_DEFAULT_FABLE_MODEL='deepseek', CLAUDE_CODE_EFFORT_LEVEL='max',
                   CLAUDE_CODE_MAX_CONTEXT_TOKENS='999', MAX_THINKING_TOKENS='0')
        data = json.loads(subprocess.check_output([str(self.prefix / 'deepseek-main'), '-p', 'hi'], env=env, text=True))
        for name in ('ANTHROPIC_BASE_URL', 'ANTHROPIC_MODEL', 'ANTHROPIC_DEFAULT_FABLE_MODEL',
                     'CLAUDE_CODE_EFFORT_LEVEL', 'CLAUDE_CODE_MAX_CONTEXT_TOKENS', 'MAX_THINKING_TOKENS'):
            self.assertNotIn(name, data['env'])

    def test_managed_effort_override_and_profile_traversal_refused(self):
        self.install('--non-interactive', config=True)
        for args in (['-P', '../other'], ['--effort', 'low']):
            result = subprocess.run([str(self.prefix / 'deepseek-worker'), *args],
                                    env=dict(self.env, DEEPSEEK_TASK_MANAGED='1'), capture_output=True)
            self.assertEqual(result.returncode, 2)

class ProbeTests(unittest.TestCase):
    def setUp(self):
        import runpy
        self.probe = runpy.run_path(str(KIT / 'bin/deepseek-probe'))

    def execute(self, responses, models=False):
        import io
        from unittest.mock import patch
        self.requests = []
        class Opener:
            def open(inner, request, timeout):
                self.requests.append(request)
                body = responses.pop(0)
                return io.BytesIO(body.encode() if isinstance(body, str) else json.dumps(body).encode())
        from contextlib import redirect_stdout
        settings = dict(LLM_BASE_URL='https://lab.invalid/anthropic', LLM_API_KEY='offline-only-key',
                        LLM_MODEL='exact-lab-id', LLM_EFFORT='max')
        with patch.dict(self.probe['main'].__globals__, config=lambda _: settings), \
             patch('urllib.request.build_opener', return_value=Opener()), \
             patch('sys.argv', ['deepseek-probe'] + (['--models'] if models else [])), redirect_stdout(io.StringIO()):
            return self.probe['main']()

    def test_probe_preserves_thinking_and_tool_content_for_continuation(self):
        content = [{'type': 'thinking', 'thinking': 'fixture thinking', 'signature': 'fixture'},
                   {'type': 'tool_use', 'id': 'call-1', 'name': 'get_time', 'input': {'tz': 'Asia/Seoul'}}]
        result = self.execute([{'type': 'message', 'content': content},
                               {'type': 'message', 'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': '12:00'}]},
                               'event: message_start\n\nevent: message_stop\n'])
        self.assertEqual(result, 0)
        first, continuation, stream = [json.loads(r.data) for r in self.requests]
        self.assertEqual(first['model'], 'exact-lab-id')
        self.assertEqual(first['output_config']['effort'], 'max')
        self.assertEqual(continuation['messages'][1]['content'], content)
        self.assertTrue(stream['stream'])
        self.assertNotIn('offline-only-key', str(first))

    def test_probe_rejects_missing_tool_call(self):
        with self.assertRaisesRegex(ValueError, 'no tool_use'):
            self.execute([{'type': 'message', 'content': [{'type': 'text', 'text': 'done'}]}])

    def test_models_only_never_sends_generation_request(self):
        self.assertEqual(self.execute([{'data': [{'id': 'exact-lab-id'}]}], models=True), 0)
        self.assertEqual(len(self.requests), 1)
        self.assertIsNone(self.requests[0].data)


if __name__ == '__main__':
    unittest.main()
