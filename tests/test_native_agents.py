"""Selective defaults and explicit native opt-out; no model or account calls."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

KIT = Path(__file__).resolve().parents[1]
MOCK = '''#!/usr/bin/env python3
import json, os, sys
keys = ('LLM_MAIN_NATIVE_AGENTS', 'LLM_MAIN_MANAGED_DELEGATION',
        'CLAUDE_CODE_DISABLE_EXPLORE_PLAN_AGENTS', 'CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS',
        'ANTHROPIC_BASE_URL', 'ANTHROPIC_AUTH_TOKEN', 'CLAUDE_CODE_SUBAGENT_MODEL_FORCE')
print(json.dumps(dict(args=sys.argv[1:], env={k: os.environ[k] for k in keys if k in os.environ})))
'''


class NativeAgents(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='native-policy-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(
            ('LLM_', 'CLAUDE_', 'ANTHROPIC_', 'ORCHESTRATOR_', 'GIT_', 'DEEPSEEK_'))}
        mock = self.root / 'mock'
        mock.mkdir()
        for name in ('claude', 'codex'):
            path = mock / name
            path.write_text(MOCK)
            path.chmod(0o755)
        self.env.update(HOME=str(self.root), PATH=str(mock) + os.pathsep + os.environ['PATH'],
                        LLM_WORKER_CONF_DIR=str(self.root / 'conf'), PYTHONDONTWRITEBYTECODE='1')
        result = subprocess.run([str(KIT / 'install.sh'), '--non-interactive', '--prefix', str(self.root / 'installed')],
                                env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def run_main(self, kind, *args, env=None, code=0):
        result = subprocess.run([str(self.root / 'installed' / (kind + '-main')), *args],
                                env=env or self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return json.loads(result.stdout) if code == 0 else result

    def prompt(self, kind, result):
        args = result['args']
        if kind == 'claude':
            return args[args.index('--append-system-prompt') + 1]
        return json.loads(next(x.split('=', 1)[1] for x in args if x.startswith('developer_instructions=')))

    def test_default_is_selective_even_with_inherited_off_marker(self):
        for kind in ('claude', 'codex'):
            result = self.run_main(kind, env=dict(self.env, LLM_MAIN_NATIVE_AGENTS='off'))
            self.assertEqual(result['env']['LLM_MAIN_NATIVE_AGENTS'], 'selective')
            self.assertIn('Native delegation mode: selective', self.prompt(kind, result))
            if kind == 'claude':
                args = result['args']
                denied = args[args.index('--disallowedTools') + 1:args.index('--system-prompt-snapshot')]
                self.assertFalse({'Agent', 'Task', 'Skill'} & set(denied))
                self.assertNotIn('CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS', result['env'])
            else:
                self.assertIn('features.multi_agent=true', result['args'])
                self.assertIn('agents.enabled=true', result['args'])

    def test_explicit_off_blocks_native_even_with_inherited_selective_marker(self):
        for kind in ('claude', 'codex'):
            result = self.run_main(kind, '--native-agents', 'off', env=dict(self.env, LLM_MAIN_NATIVE_AGENTS='selective'))
            self.assertEqual(result['env']['LLM_MAIN_NATIVE_AGENTS'], 'off')
            self.assertIn('Native delegation mode: off', self.prompt(kind, result))
            if kind == 'claude':
                args = result['args']
                denied = args[args.index('--disallowedTools') + 1:args.index('--system-prompt-snapshot')]
                self.assertTrue({'Agent', 'Task', 'Skill', 'Workflow', 'TeamCreate'} <= set(denied))
                self.assertEqual(result['env']['CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS'], '1')
            else:
                self.assertIn('features.multi_agent=false', result['args'])
                self.assertIn('agents.enabled=false', result['args'])

    def test_claude_selective_allows_native_without_worker_routing_or_permission_bypass(self):
        env = dict(self.env, CLAUDE_CODE_DISABLE_EXPLORE_PLAN_AGENTS='1',
                   CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS='1',
                   ANTHROPIC_BASE_URL='https://worker.invalid', ANTHROPIC_AUTH_TOKEN='fixture-key',
                   CLAUDE_CODE_SUBAGENT_MODEL_FORCE='1')
        result = self.run_main('claude', '--native-agents', 'selective', '--resume', 'existing', env=env)
        args = result['args']
        denied = args[args.index('--disallowedTools') + 1:args.index('--system-prompt-snapshot')]
        self.assertFalse({'Agent', 'Task', 'Skill'} & set(denied))
        self.assertTrue({'Workflow', 'TeamCreate', 'Bash(claude *)'} <= set(denied))
        self.assertEqual(result['env'], {'LLM_MAIN_NATIVE_AGENTS': 'selective', 'LLM_MAIN_MANAGED_DELEGATION': '1'})
        self.assertEqual(args[args.index('--model') + 1], 'opus')
        self.assertIn('--resume', args)
        self.assertNotIn('--dangerously-skip-permissions', args)
        self.assertNotIn('--effort', args)
        prompt = self.prompt('claude', result)
        for expected in ('Native delegation mode: selective', 'EGM', 'root-cause',
                         'worker-task submit', 'read-only', 'Do not classify every task as difficult'):
            self.assertIn(expected, prompt)
        self.assertNotIn('Native subagents and forked skills are disabled for this session', prompt)

    def test_codex_selective_preserves_account_model_and_resume_arguments(self):
        result = self.run_main('codex', '--native-agents=selective', 'resume', '--last', '-c', 'model="my-model"')
        self.assertIn('features.multi_agent=true', result['args'])
        self.assertIn('agents.enabled=true', result['args'])
        self.assertIn('model="my-model"', result['args'])
        self.assertIn('--last', result['args'])
        self.assertNotIn('--native-agents=selective', result['args'])
        self.assertIn("user's Codex account/configuration", self.prompt('codex', result))
        self.assertIn('Native delegation mode: selective', self.prompt('codex', result))
        self.assertEqual(result['env']['LLM_MAIN_NATIVE_AGENTS'], 'selective')

    def test_explicit_caller_tool_denies_are_preserved(self):
        result = self.run_main('claude', '--native-agents', 'selective',
                               '--disallowedTools', 'Agent', 'WebFetch', '-p', 'fixture')
        args = result['args']
        denied = args[args.index('--disallowedTools') + 1:args.index('--system-prompt-snapshot')]
        self.assertTrue({'Agent', 'WebFetch'} <= set(denied))

    def test_invalid_or_missing_mode_fails_before_native_cli(self):
        for kind in ('claude', 'codex'):
            for args in (['--native-agents'], ['--native-agents=all'], ['--native-agents', 'automatic']):
                result = self.run_main(kind, *args, code=2)
                self.assertFalse(result.stdout)
                self.assertIn('--native-agents', result.stderr)

    def test_prompt_delimiter_does_not_consume_literals_or_hide_codex_policy_flags(self):
        for kind in ('claude', 'codex'):
            result = self.run_main(kind, '--native-agents', 'selective', '--', '--native-agents', 'off')
            args = result['args']
            self.assertEqual(args[args.index('--') + 1:], ['--native-agents', 'off'])
            self.assertEqual(result['env']['LLM_MAIN_NATIVE_AGENTS'], 'selective')
            if kind == 'codex':
                self.assertLess(args.index('agents.enabled=true'), args.index('--'))

    def test_worker_does_not_inherit_main_native_mode(self):
        result = subprocess.run([str(self.root / 'installed/llm-worker'), '-p', 'fixture'],
                                env=dict(self.env, LLM_MAIN_NATIVE_AGENTS='selective', LLM_MAIN_MANAGED_DELEGATION='1'),
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        env = json.loads(result.stdout)['env']
        self.assertNotIn('LLM_MAIN_NATIVE_AGENTS', env)
        self.assertNotIn('LLM_MAIN_MANAGED_DELEGATION', env)
