"""Permission policy contract and real wrapper wiring; no model/server needed."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

KIT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('worker_permissions',KIT/'bin/_deepseek_permissions.py')
permissions=importlib.util.module_from_spec(spec)
# Import after the delegated implementation is copied into the kit.
spec.loader.exec_module(permissions)


class PermissionRules(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.wt=self.root/'assigned worktree'
        self.repo=self.root/'original'

    def normalize(self,**values):
        return permissions.normalize_permissions(values,self.root)

    def settings(self,policy=None):
        return permissions.build_settings(policy or self.normalize(),self.wt,self.repo,['tests/','config/','.git','.claude/','.task-inputs/','scripts/verify.sh'])

    def test_default_workspace_has_full_standard_tools_without_bypass(self):
        policy=self.normalize()
        self.assertEqual(policy['profile'],'workspace')
        settings=self.settings(policy)
        self.assertEqual(settings['crossSessionInbound'],'accept')
        self.assertEqual(settings['permissions']['defaultMode'],'dontAsk')
        allow=settings['permissions']['allow']
        for tool in ('Bash','WebFetch','WebSearch','Agent','Task','Skill'):
            self.assertIn(tool,allow)
        self.assertTrue(any(x.startswith('Read(//') and '/assigned worktree/' in x for x in allow))
        self.assertTrue(any(x.startswith('Edit(//') and '/assigned worktree/' in x for x in allow))
        self.assertNotIn('Edit',allow)
        self.assertNotIn('Write',allow)
        self.assertFalse(any(x.startswith(('Write(','NotebookEdit(','Glob(')) for x in allow))
        self.assertNotIn('bypassPermissions',json.dumps(settings))
        for path in ('tests','config','.claude','.git','.task-inputs','scripts/verify.sh'):
            self.assertTrue(any(x.startswith('Edit(') and '/assigned worktree/'+path in x for x in settings['permissions']['deny']),path)
        self.assertTrue(any('/original/' in x for x in settings['permissions']['deny']))

    def test_external_read_only_and_scratch_paths_do_not_grant_dataset_edits(self):
        policy=self.normalize(read_paths=['/mnt/d/Gateact'],scratch_paths=['/tmp/gre_*'])
        settings=self.settings(policy)['permissions']
        self.assertIn('Read(//mnt/d/Gateact/**)',settings['allow'])
        self.assertIn('Edit(//mnt/d/Gateact/**)',settings['deny'])
        self.assertNotIn('Edit(//mnt/d/Gateact/**)',settings['allow'])
        self.assertIn('Edit(//tmp/gre_*/**)',settings['allow'])
        self.assertEqual(policy['scratch_paths'],['/tmp/gre_*'])

    def test_inherit_and_custom_are_explicit_and_keep_custom_deny_ask(self):
        self.assertIsNone(self.settings(self.normalize(permission_profile='inherit')))
        path=self.root/'proposed.json'
        path.write_text(json.dumps({'permissions':{'allow':['Read(/notes/**)','Bash(python3 *)'],
            'ask':['WebFetch'],'deny':['Bash(pip *)','Bash(rm *)']},'env':{'not_copied':'value'},'hooks':{}}))
        policy=self.normalize(permission_profile='custom',permissions_file=str(path))
        path.write_text('{}')
        settings=self.settings(policy)
        self.assertNotIn('env',settings)
        self.assertNotIn('hooks',settings)
        self.assertNotIn('Bash',settings['permissions']['allow'])
        self.assertIn('Bash(python3 *)',settings['permissions']['allow'])
        self.assertIn('Bash(pip *)',settings['permissions']['deny'])
        self.assertIn('Bash(rm *)',settings['permissions']['deny'])
        self.assertIn('WebFetch',settings['permissions']['ask'])
        self.assertIn('Read(/'+str(self.wt)+'/notes/**)',settings['permissions']['allow'])

    def test_invalid_profiles_paths_and_rules_are_rejected(self):
        invalid=[{'permission_profile':'bypassPermissions'},{'permission_profile':'custom'},
          {'permission_profile':'inherit','read_paths':['/mnt/d/data']},
          {'scratch_paths':['/']},{'scratch_paths':['relative']},{'scratch_paths':['/tmp/../home']},
          {'read_paths':'/mnt/d/data'},{'scratch_paths':[3]}]
        for values in invalid:
            with self.subTest(values=values),self.assertRaises(ValueError):self.normalize(**values)
        path=self.root/'bad.json';path.write_text(json.dumps({'permissions':{'allow':'Bash'}}))
        with self.assertRaises(ValueError):self.normalize(permissions_file=str(path))

    def test_write_and_glob_path_rules_are_normalized_and_default_protection_is_kept(self):
        path=self.root/'proposed.json'
        path.write_text(json.dumps({'permissions':{'allow':['Write(/reports/**)','Glob(/data/**)']}}))
        settings=self.settings(self.normalize(permission_profile='custom',permissions_file=str(path)))
        self.assertIn('Edit(/'+str(self.wt)+'/reports/**)',settings['permissions']['allow'])
        self.assertIn('Read(/'+str(self.wt)+'/data/**)',settings['permissions']['allow'])
        base=permissions.build_settings(self.normalize(),self.wt,self.repo,[])
        self.assertTrue(any('/tests/' in x for x in base['permissions']['deny']))

    def test_read_only_git_inspection_is_not_caught_by_family_wide_denies(self):
        deny=self.settings()['permissions']['deny']
        self.assertNotIn('Bash(git branch:*)',deny)
        self.assertNotIn('Bash(git tag:*)',deny)
        self.assertNotIn('Bash(git worktree:*)',deny)
        self.assertIn('Bash(git commit:*)',deny)
        self.assertIn('Bash(git worktree remove:*)',deny)

    def test_literal_brackets_in_repository_paths_are_escaped(self):
        wt=self.root/'task[1]';repo=self.root/'source[2]'
        settings=permissions.build_settings(self.normalize(),wt,repo,[])['permissions']
        self.assertFalse(any('/task[1]/' in x for x in settings['allow']))
        self.assertTrue(any('/task\\[1\\]/' in x for x in settings['allow']))
        self.assertTrue(any('/source\\[2\\]/' in x for x in settings['deny']))


if __name__=='__main__':unittest.main()
