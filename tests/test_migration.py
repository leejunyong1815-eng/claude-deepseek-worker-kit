"""Compatibility and private configuration imports across the two former kits."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import time
import unittest
from unittest.mock import patch
import test_pool
KIT = Path(__file__).resolve().parents[1]

class Migration(unittest.TestCase):

    def setUp(self):
        self.f = test_pool.Pools('test_default_backend_selection_and_unknown_model_fail_closed')
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def test_import_two_legacy_configs_preserves_sources_and_groups_models(self):
        f = self.f
        a = f.root / 'claude-worker'
        b = f.root / 'deepseek-worker'
        a.mkdir()
        b.mkdir()
        (a / 'env').write_text('export LLM_BASE_URL=https://one.invalid\nexport LLM_API_KEY=legacy-private-one-12345\nexport LLM_MODEL=one\nexport LLM_CONTEXT_WINDOW=32000\n')
        (a / 'env.impl').write_text((a / 'env').read_text().replace('LLM_MODEL=one', 'LLM_MODEL=implementation-one'))
        (b / 'env').write_text('export LLM_BASE_URL=https://stale.invalid\nexport LLM_API_KEY=stale-private-key-12345\nexport LLM_MODEL=two\nexport LLM_CONTEXT_WINDOW=32000\n')
        (b / 'env.qwen').write_text((b / 'env').read_text().replace('LLM_MODEL=two', 'LLM_MODEL=operator-two'))
        (b / 'gateway.env').write_text('export LLM_BASE_URL=https://two.invalid\nexport LLM_AUTH_MODE=api_key\nexport LLM_API_KEY=legacy-private-two-12345\n')
        before = {str(p): p.read_bytes() for parent in (a, b) for p in parent.iterdir()}
        f.call(KIT / 'install.sh', '--non-interactive', '--import-config', a, '--import-config', b, '--prefix', f.root / 'installed')
        self.assertTrue(all((Path(p).read_bytes() == raw for p, raw in before.items())))
        listed = json.loads(f.call(KIT / 'bin/llm-backend', 'list').stdout)
        imported = [x for x in listed if x['name'].startswith('imported-')]
        self.assertEqual({x['url'] for x in imported}, {'https://one.invalid', 'https://two.invalid'})
        self.assertEqual(sum((len(x['models']) for x in imported)), 4)
        self.assertNotIn('legacy-private', json.dumps(listed))
        spec = f.root / 'import-task.json'
        spec.write_text(json.dumps(dict(purpose='imported model', repository=str(f.repo), profile='claude-impl', instructions='{}', allowed_paths=['reports/'], verify=['test "$(cat reports/model.txt)" = implementation-one'])))
        tid = f.call(KIT / 'bin/worker-task', 'submit', spec).stdout.strip()
        record = json.loads(f.call(KIT / 'bin/worker-task', 'run', tid).stdout)
        self.assertEqual(record['model'], 'implementation-one')
        self.assertNotIn('legacy-private', Path(record['logs']['worker_stderr']).read_text())

    def test_in_place_legacy_update_keeps_per_profile_server_and_original_env_bytes(self):
        f = self.f
        conf = f.root / 'conf'
        (conf / 'gateway.env').unlink()
        (conf / 'env').write_text('export LLM_BASE_URL=https://first.invalid\nexport LLM_API_KEY=legacy-private-first-12345\nexport LLM_MODEL=first\nexport LLM_CONTEXT_WINDOW=32000\n')
        (conf / 'env.other').write_text((conf / 'env').read_text().replace('first', 'second'))
        before = {p.name: p.read_bytes() for p in conf.glob('env*')}
        f.call(KIT / 'install.sh', '--update', '--prefix', f.root / 'installed')
        self.assertEqual(before, {p.name: p.read_bytes() for p in conf.glob('env*')})
        from _backends import choose
        with patch.dict(os.environ, f.env, clear=True):
            self.assertEqual(choose(profile='other')[1]['url'], 'https://second.invalid')
            self.assertEqual(choose()[1]['url'], 'https://first.invalid')
        f.add('new', 'new-model')
        f.call(KIT / 'bin/llm-backend', 'default', 'new')
        with patch.dict(os.environ, f.env, clear=True):
            self.assertEqual(choose()[0], 'new')

    def test_original_task_without_new_fields_can_run_without_rewriting_its_spec(self):
        f = self.f
        spec = f.root / 'legacy-task.json'
        spec.write_text(json.dumps(dict(purpose='legacy', repository=str(f.repo), instructions='{}', allowed_paths=['reports/'], verify=['test -s reports/model.txt'])))
        tid = f.call(KIT / 'bin/worker-task', 'submit', spec).stdout.strip()
        folder = f.root / 'state/local-worker/tasks' / tid
        data = json.loads((folder / 'spec.json').read_text())
        for key in ('role', 'worker_permissions', 'backend', 'model', 'worker_id', 'max_turns', 'inputs', 'compute_job', 'effort'):
            data.pop(key, None)
        (folder / 'spec.json').write_text(json.dumps(data))
        with patch.dict(os.environ, f.env, clear=True):
            digest = runpy.run_path(str(KIT / 'bin/worker-task'))['digest']
        state = json.loads((folder / 'state.json').read_text())
        state['spec_digest'] = digest(data)
        (folder / 'state.json').write_text(json.dumps(state))
        before = (folder / 'spec.json').read_bytes()
        record = json.loads(f.call(KIT / 'bin/worker-task', 'run', tid).stdout)
        self.assertEqual(record['state'], 'succeeded')
        self.assertEqual((folder / 'spec.json').read_bytes(), before)

    def test_backend_admission_survives_pool_worker_crash(self):
        f = self.f
        f.call(KIT / 'bin/llm-backend', 'add', 'limited', '--url', 'https://limited.invalid', '--model', 'limited', '--max-parallel', '1')
        first, one = f.pool(['limited'], count='1')
        second, two = f.pool(['limited'], count='1')
        worker = f.serve(first, one['workers'][0])
        a, ea = f.submit(first, sleep=1)
        end = time.monotonic() + 5
        while time.monotonic() < end:
            state = json.loads((first / 'tasks' / a / 'state.json').read_text())
            if state.get('worktree') and (Path(state['worktree']) / 'reports/model.txt').is_file():
                break
            time.sleep(0.02)
        worker.kill()
        worker.communicate(timeout=3)
        f.serve(second, two['workers'][0])
        b, eb = f.submit(second)
        time.sleep(0.15)
        self.assertEqual(json.loads((second / 'tasks' / b / 'state.json').read_text())['state'], 'queued')
        self.assertEqual(f.result(a, ea)['state'], 'succeeded')
        self.assertEqual(f.result(b, eb)['state'], 'succeeded')
    def test_uninstall_preserves_native_clis_private_registry_and_other_files(self):
        f=self.f;f.add('keep','keep-model');prefix=f.root/'installed'
        for name in ('codex','claude','unrelated-tool'):(prefix/name).write_text('preserve')
        f.call(KIT/'uninstall.sh','--prefix',prefix)
        self.assertFalse((prefix/'codex-duo').exists())
        for name in ('codex','claude','unrelated-tool'):self.assertEqual((prefix/name).read_text(),'preserve')
        self.assertTrue((f.root/'conf/backends/keep.json').is_file())

if __name__ == '__main__':
    unittest.main()
