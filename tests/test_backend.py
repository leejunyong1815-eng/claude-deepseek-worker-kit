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
print(json.dumps({'args': sys.argv[1:], 'env': {k:v for k,v in os.environ.items() if k.startswith(('ANTHROPIC_', 'CLAUDE_CODE_')) or k in ('MAX_THINKING_TOKENS','LLM_EFFORT','DEEPSEEK_WORKER_EFFORT','DEEPSEEK_MAIN_MANAGED_DELEGATION','CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS')}}))
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
        self.env['LLM_AUTH_MODE'] = 'api_key'
        self.install('--non-interactive', code=2)
        self.assertFalse((self.conf / 'env').exists())

    def test_lab_defaults_require_only_a_private_key(self):
        self.env['LLM_API_KEY'] = 'offline-default-key'
        self.install('--non-interactive')
        data = json.loads(subprocess.check_output([str(self.prefix / 'deepseek-worker'), '-p', 'hi'],
                                                  env=self.env, text=True))
        self.assertEqual(data['env']['ANTHROPIC_BASE_URL'], 'http://1.233.219.161:4000')
        self.assertEqual(data['env']['ANTHROPIC_MODEL'], 'deepseek-v4.1-flash')
        self.assertEqual(data['env']['CLAUDE_CODE_MAX_CONTEXT_TOKENS'], '262144')
        self.assertEqual(data['env']['ANTHROPIC_AUTH_TOKEN'], 'offline-default-key')

    def test_defaults_file_never_provides_credentials(self):
        defaults = json.loads((KIT / 'config/backend.defaults.json').read_text())
        self.assertEqual(set(defaults), {'LLM_BASE_URL', 'LLM_MODEL', 'LLM_CONTEXT_WINDOW', 'LLM_AUTH_MODE', 'QWEN_MODEL'})
        self.env['LLM_AUTH_MODE'] = 'api_key'
        result = self.install('--non-interactive', code=2)
        self.assertIn('LLM_API_KEY is required', result.stderr)

    def test_keyless_proxy_and_qwen_profile_are_explicit_and_separate(self):
        self.install('--non-interactive')
        self.install('--profile', 'qwen', '--non-interactive')
        base = json.loads(subprocess.check_output([str(self.prefix/'deepseek-worker'), '-p', 'hi'], env=self.env, text=True))
        qwen = json.loads(subprocess.check_output([str(self.prefix/'qwen-worker'), '-p', 'hi'], env=self.env, text=True))
        self.assertEqual(base['env']['ANTHROPIC_MODEL'], 'deepseek-v4.1-flash')
        self.assertEqual(qwen['env']['ANTHROPIC_MODEL'], 'qwen3.8-flash-next')
        self.assertEqual(base['env']['ANTHROPIC_AUTH_TOKEN'], 'litellm-no-auth')
        self.assertEqual((self.conf/'gateway.env').stat().st_mode & 0o777,0o600)
        self.assertIn('Compute job operator (Qwen)', qwen['args'][qwen['args'].index('--append-system-prompt')+1])

    def test_configuration_is_private_offline_and_all_tiers_use_exact_alias(self):
        self.install('--non-interactive', config=True)
        self.assertEqual((self.conf / 'env').stat().st_mode & 0o777, 0o600)
        p = subprocess.run([str(self.prefix / 'deepseek-worker'), '-p', 'hi'], env=self.env,
                           text=True, capture_output=True, check=True)
        data = json.loads(p.stdout)
        self.assertNotIn('--effort', data['args'])
        self.assertNotIn('CLAUDE_CODE_EFFORT_LEVEL', data['env'])
        self.assertEqual(data['env']['ANTHROPIC_BASE_URL'], 'https://lab.invalid/anthropic')
        for tier in ('OPUS', 'SONNET', 'HAIKU', 'FABLE'):
            self.assertEqual(data['env'][f'ANTHROPIC_DEFAULT_{tier}_MODEL'], 'lab-flash-alias')
        self.assertIn('Implementer discipline', data['args'][data['args'].index('--append-system-prompt') + 1])
        self.assertEqual(data['env']['CLAUDE_CODE_SUBAGENT_MODEL_FORCE'],'1')

    def test_role_override_does_not_retain_implementer_instructions(self):
        self.install('--non-interactive', config=True)
        self.install('--profile', 'impl', '--non-interactive')
        env = dict(self.env, DEEPSEEK_WORKER_ROLE='reviewer', DEEPSEEK_WORKER_EFFORT='high')
        result = subprocess.check_output([str(self.prefix / 'deepseek-worker'), '-P', 'impl', '-p', 'hi'], env=env, text=True)
        data = json.loads(result)
        prompt = data['args'][data['args'].index('--append-system-prompt') + 1]
        self.assertIn('Independent reviewer', prompt)
        self.assertNotIn('Implementer discipline', prompt)
        self.assertNotIn('CLAUDE_CODE_EFFORT_LEVEL', data['env'])
        self.assertNotIn('--effort', data['args'])

    def test_orchestrator_does_not_inherit_worker_model_or_reasoning_settings(self):
        self.install('--install-only')
        env = dict(self.env, ANTHROPIC_BASE_URL='https://lab.invalid', ANTHROPIC_MODEL='deepseek',
                   ANTHROPIC_DEFAULT_FABLE_MODEL='deepseek', CLAUDE_CODE_EFFORT_LEVEL='max',
                   CLAUDE_CODE_MAX_CONTEXT_TOKENS='999', MAX_THINKING_TOKENS='0',
                   CLAUDE_CODE_SUBAGENT_MODEL_FORCE='1',CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL='wrong-model',
                   CLAUDE_CODE_MAX_OUTPUT_TOKENS='999')
        data = json.loads(subprocess.check_output([str(self.prefix / 'deepseek-main'), '-p', 'hi'], env=env, text=True))
        for name in ('ANTHROPIC_BASE_URL', 'ANTHROPIC_MODEL', 'ANTHROPIC_DEFAULT_FABLE_MODEL',
                     'CLAUDE_CODE_EFFORT_LEVEL', 'CLAUDE_CODE_MAX_CONTEXT_TOKENS', 'MAX_THINKING_TOKENS',
                     'CLAUDE_CODE_SUBAGENT_MODEL_FORCE','CLAUDE_CODE_WORKFLOW_SUBAGENT_MODEL','CLAUDE_CODE_MAX_OUTPUT_TOKENS'):
            self.assertNotIn(name, data['env'])

    def test_main_defaults_to_opus_blocks_native_delegation_and_merges_context(self):
        self.install('--install-only')
        data=json.loads(subprocess.check_output([str(self.prefix/'deepseek-main'),'--resume','existing',
              '--append-system-prompt','Demo context','--disallowedTools','WebFetch','-p','work'],env=self.env,text=True))
        args=data['args']
        self.assertEqual(args[args.index('--model')+1],'opus')
        self.assertEqual(args[args.index('--system-prompt-snapshot')+1],'off')
        start=args.index('--disallowedTools')+1
        self.assertTrue({'Agent','Task','Workflow','TeamCreate','Skill','WebFetch'} <= set(args[start:args.index('--system-prompt-snapshot')]))
        text=args[args.index('--append-system-prompt')+1]
        self.assertIn('deepseek-task submit',text)
        self.assertIn('Demo context',text)
        self.assertEqual(data['env']['CLAUDE_CODE_DISABLE_EXPLORE_PLAN_AGENTS'],'1')
        self.assertEqual(data['env']['CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS'],'1')
        self.assertIn('--resume',args)
        result=subprocess.run([str(self.prefix/'deepseek-main'),'--system-prompt-snapshot','on'],env=self.env,capture_output=True)
        self.assertEqual(result.returncode,2)

    def test_all_worker_profiles_use_one_gateway_even_with_stale_profile_urls(self):
        self.install('--non-interactive')
        self.install('--profile','qwen','--non-interactive')
        p=self.conf/'env.qwen'
        with p.open('a') as out:
            out.write('export LLM_BASE_URL=https://old-profile.invalid\nexport LLM_API_KEY=old-private-profile-key\nexport LLM_AUTH_MODE=api_key\n')
        env=dict(self.env, ANTHROPIC_BASE_URL='https://inherited.invalid',CLAUDE_CODE_DISABLE_EXPLORE_PLAN_AGENTS='1',
                 CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS='1',DEEPSEEK_MAIN_MANAGED_DELEGATION='1')
        data=json.loads(subprocess.check_output([str(self.prefix/'qwen-worker'),'-p','job'],env=env,text=True))
        self.assertEqual(data['env']['ANTHROPIC_BASE_URL'],'http://1.233.219.161:4000')
        self.assertEqual(data['env']['ANTHROPIC_AUTH_TOKEN'],'litellm-no-auth')
        self.assertEqual(data['env']['ANTHROPIC_MODEL'],'qwen3.8-flash-next')
        for k in ('CLAUDE_CODE_DISABLE_EXPLORE_PLAN_AGENTS','CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS','DEEPSEEK_MAIN_MANAGED_DELEGATION'):
            self.assertNotIn(k,data['env'])
        gateway=(self.conf/'gateway.env').read_bytes()
        self.install('--update')
        self.assertEqual((self.conf/'gateway.env').read_bytes(),gateway)
        self.assertIn('https://old-profile.invalid',p.read_text())

    def test_missing_shared_gateway_does_not_fall_back_to_profile_connection(self):
        self.install('--non-interactive')
        (self.conf/'gateway.env').unlink()
        p=subprocess.run([str(self.prefix/'deepseek-worker'),'-p','do not run'],env=self.env,capture_output=True,text=True)
        self.assertEqual(p.returncode,2)
        self.assertIn('shared gateway missing',p.stderr)
        self.assertFalse(p.stdout)

    def test_update_migrates_known_old_server_without_forwarding_its_key(self):
        self.install('--non-interactive')
        (self.conf/'gateway.env').unlink()
        config=(self.conf/'env').read_text().replace('http://1.233.219.161:4000','http://133.186.146.224:8081')
        config += 'export LLM_AUTH_MODE=api_key\nexport LLM_API_KEY=old-server-only-key\n'
        (self.conf/'env').write_text(config)
        self.install('--update')
        gateway=(self.conf/'gateway.env').read_text()
        self.assertIn('http://1.233.219.161:4000',gateway)
        self.assertNotIn('old-server-only-key',gateway)
        self.assertEqual((self.conf/'env').read_text(),config)

    def test_legacy_profiles_and_inherited_effort_do_not_reach_either_model(self):
        self.install('--non-interactive')
        self.install('--profile', 'qwen', '--non-interactive')
        for name in ('env','env.qwen'):
            with (self.conf/name).open('a') as f:
                f.write('export LLM_EFFORT=max\n')
        before={p.name:p.read_bytes() for p in self.conf.glob('env*')}
        self.install('--update')
        self.assertEqual(before,{p.name:p.read_bytes() for p in self.conf.glob('env*')})
        env=dict(self.env, LLM_EFFORT='max', DEEPSEEK_WORKER_EFFORT='high',
                 CLAUDE_CODE_EFFORT_LEVEL='low', MAX_THINKING_TOKENS='4096')
        for name in ('deepseek-worker','qwen-worker'):
            data=json.loads(subprocess.check_output([str(self.prefix/name),'-p','hi'],env=env,text=True))
            self.assertNotIn('--effort',data['args'])
            for key in ('LLM_EFFORT','DEEPSEEK_WORKER_EFFORT','CLAUDE_CODE_EFFORT_LEVEL','MAX_THINKING_TOKENS'):
                self.assertNotIn(key,data['env'])

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
        for body in (first, continuation, stream):
            self.assertNotIn('effort', body.get('output_config', {}))
        self.assertEqual(continuation['messages'][1]['content'], content)
        self.assertTrue(stream['stream'])
        self.assertNotIn('offline-only-key', str(first))

    def test_benchmark_only_sends_effort_when_that_diagnostic_is_explicit(self):
        import contextlib,io,runpy
        from unittest.mock import patch
        checker=runpy.run_path(str(KIT/'bench/litellm_check.py'))
        bodies=[]
        class Opener:
            def open(self,request,timeout):
                body=json.loads(request.data);bodies.append(body)
                value={'content':[{'type':'text','text':'LAB_EFFORT_OK'}]} if 'output_config' in body else {}
                return io.BytesIO(json.dumps(value).encode())
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'result.json'
            for extra in ([],['--check','messages_effort']):
                bodies.clear()
                argv=['litellm_check','--base-url','https://lab.invalid','--family','qwen3.8-flash-next','--output',str(output),*extra]
                with patch('urllib.request.build_opener',return_value=Opener()), patch('sys.argv',argv), \
                     patch.dict(os.environ,{'LLM_API_KEY':''}), contextlib.redirect_stdout(io.StringIO()):
                    checker['main']()
                if extra:
                    self.assertEqual([b['output_config']['effort'] for b in bodies],['max'])
                else:
                    self.assertTrue(bodies)
                    self.assertTrue(all('effort' not in b.get('output_config',{}) for b in bodies))
                    self.assertNotIn('messages_effort',[r['check'] for r in json.loads(output.read_text())['checks']])

    def test_probe_uses_shared_gateway_not_the_selected_profile_url(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'env.qwen').write_text('export LLM_BASE_URL=https://stale.invalid\nexport LLM_MODEL=qwen3.8-flash-next\nexport LLM_API_KEY=stale-key\n')
            (root/'gateway.env').write_text('export LLM_BASE_URL=http://1.233.219.161:4000\nexport LLM_AUTH_MODE=none\nexport LLM_API_KEY=\n')
            with patch.dict(os.environ,{'DEEPSEEK_WORKER_CONF_DIR':str(root)}):
                values=self.probe['config']('qwen')
            self.assertEqual(values['LLM_BASE_URL'],'http://1.233.219.161:4000')
            self.assertEqual(values['LLM_MODEL'],'qwen3.8-flash-next')
            self.assertEqual(values['LLM_API_KEY'],'')

    def test_probe_rejects_incomplete_shared_gateway_instead_of_using_profile_keys(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'env').write_text('export LLM_BASE_URL=https://stale.invalid\nexport LLM_MODEL=deepseek-v4.1-flash\nexport LLM_API_KEY=stale-key\n')
            gateway = root / 'gateway.env'
            for text in ('export LLM_AUTH_MODE=none\n',
                         'export LLM_BASE_URL=https://lab.invalid\nexport LLM_AUTH_MODE=api_key\n'):
                gateway.write_text(text)
                with self.subTest(text=text), patch.dict(os.environ, {'DEEPSEEK_WORKER_CONF_DIR': str(root)}):
                    with self.assertRaises(ValueError):
                        self.probe['config']('')

    def test_probe_rejects_missing_tool_call(self):
        with self.assertRaisesRegex(ValueError, 'no tool_use'):
            self.execute([{'type': 'message', 'content': [{'type': 'text', 'text': 'done'}]}])

    def test_models_only_never_sends_generation_request(self):
        self.assertEqual(self.execute([{'data': [{'id': 'exact-lab-id'}]}], models=True), 0)
        self.assertEqual(len(self.requests), 1)
        self.assertIsNone(self.requests[0].data)


if __name__ == '__main__':
    unittest.main()
