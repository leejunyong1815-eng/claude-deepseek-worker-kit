"""Fresh Linux/WSL-style HOME, independent clone, installed entrypoints; no network."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

KIT = Path(__file__).resolve().parents[1]
MOCK_CLAUDE = '''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
if '--version' in sys.argv:
    print('2.1.314 (offline fixture)'); sys.exit(0)
if '--help' in sys.argv:
    print('--effort LEVEL --name NAME'); sys.exit(0)
assert '--dangerously-skip-permissions' not in sys.argv
assert os.environ['ANTHROPIC_MODEL'] == 'DeepSeek-V4.1-Flash'
assert os.environ['CLAUDE_CODE_EFFORT_LEVEL'] == 'max'
assert os.environ['CLAUDE_CODE_MAX_CONTEXT_TOKENS'] == '1048576'
Path('src/result.txt').write_text('42')
print(json.dumps({'is_error':False, 'result':'fixture complete'}))
'''


class FreshInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='test-portable-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / 'another user'
        self.home.mkdir()
        self.clone = self.home / 'source code/custom checkout name'
        # The temporary source is committed only to test an independent local clone.
        seed = self.root / 'seed'
        shutil.copytree(KIT, seed, ignore=shutil.ignore_patterns('.git','__pycache__','.pytest_cache'))
        self.env = {'HOME':str(self.home), 'PATH':os.defpath, 'LANG':'C.UTF-8', 'PYTHONDONTWRITEBYTECODE':'1'}
        self.git(seed, 'init','-q','-b','main')
        self.git(seed,'add','--','.')
        self.git(seed,'-c','user.name=Portability fixture','-c','user.email=fixture@local',
                 '-c','commit.gpgsign=false','commit','-qm','fixture')
        self.clone.parent.mkdir()
        self.git(self.root, 'clone','-q','--no-hardlinks',str(seed),str(self.clone))
        self.bin = self.home / '.local/deepseek-worker/bin'
        self.conf = self.home / '.config/deepseek-worker'
        self.fakebin = self.home / '.local/bin'
        self.fakebin.mkdir(parents=True)
        self.claude = self.fakebin / 'claude'
        self.claude.write_text(MOCK_CLAUDE)
        self.claude.chmod(0o755)
        self.env['PATH'] = str(self.fakebin) + os.pathsep + os.defpath
        self.shell = self.conf / 'shell.sh'

    def git(self, cwd, *args):
        return subprocess.check_output(['git','-C',str(cwd),*args],env=self.env,stderr=subprocess.PIPE)

    def call(self, *args, code=0, env=None, cwd=None):
        result = subprocess.run([str(a) for a in args],env=env or self.env,cwd=cwd or self.clone,
                                capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,code,result.stdout+result.stderr)
        return result

    def install(self, *args, key=True):
        env = dict(self.env)
        if key:env['LLM_API_KEY']='offline-portability-fixture-key'
        return self.call(self.clone/'install.sh','--non-interactive',*args,env=env)

    def sourced(self, command, code=0, cwd=None):
        return self.call('bash','--noprofile','--norc','-c',
                         '. "$1"; shift; "$@"','portable-shell',self.shell,*command,code=code,cwd=cwd)

    def test_fresh_clone_install_and_managed_task_from_installed_commands(self):
        self.call(self.clone/'install.sh','--check')
        self.assertFalse(self.conf.exists())
        self.install('--setup-path')
        doctor=self.sourced(['deepseek-doctor'])
        self.assertNotIn('offline-portability-fixture-key',doctor.stdout)
        project = self.home/'my project'
        project.mkdir()
        self.sourced(['deepseek-project-init',str(project)])
        self.assertTrue((project/'AGENTS.md').is_file())
        self.assertTrue((project/'.claude/settings.json').is_file())
        (project/'src').mkdir()
        (project/'src/input.txt').write_text('base')
        self.git(project,'init','-q','-b','main')
        self.git(project,'add','--','.')
        self.git(project,'-c','user.name=Fixture','-c','user.email=fixture@local',
                 '-c','commit.gpgsign=false','commit','-qm','input')
        task_spec = self.home/'task.json'
        task_spec.write_text(json.dumps(dict(purpose='portable run',repository=str(project),
            instructions='Create src/result.txt with 42',role='implementer',allowed_paths=['src/result.txt'],
            references=['src/input.txt'],verify=['test "$(cat src/result.txt)" = 42'],timeout=5,verify_timeout=3)))
        task = self.sourced(['deepseek-task','submit',str(task_spec)],cwd=project).stdout.strip()
        result = json.loads(self.sourced(['deepseek-task','run',task],cwd=project).stdout)
        self.assertEqual(result['state'],'succeeded')
        self.assertTrue(Path(result['worktree']).is_relative_to(self.home))
        self.assertFalse((project/'src/result.txt').exists())
        self.assertEqual(self.git(project,'status','--porcelain'),b'')
        self.assertTrue(str(self.clone) in (self.conf/'kit_dir').read_text())
        self.assertEqual((self.conf/'env').stat().st_mode & 0o777,0o600)

    def test_setup_path_is_idempotent_and_preserves_existing_bashrc_and_config(self):
        rc = self.home/'.bashrc'
        rc.write_text('# my settings\nexport PERSONAL_SETTING=keep\n')
        self.install('--setup-path')
        before_rc = rc.read_bytes()
        before_env = (self.conf/'env').read_bytes()
        self.install('--update','--setup-path',key=False)
        self.assertEqual(rc.read_bytes(),before_rc)
        self.assertTrue(rc.read_text().startswith('# my settings\n'))
        self.assertEqual((self.conf/'env').read_bytes(),before_env)
        data = self.call('bash','--noprofile','--norc','-c',
                         '. "$1"; . "$1"; python3 -c \'import json,os; print(json.dumps(os.environ["PATH"].split(":")))\'',
                         'portable-shell',self.shell)
        self.assertEqual(json.loads(data.stdout).count(str(self.bin)),1)

    def test_new_terminal_finds_native_claude_without_inheriting_installer_path(self):
        self.install('--setup-path')
        fresh_env=dict(self.env,PATH=os.defpath)
        self.call('bash','--noprofile','--norc','-c',
                  '. "$1"; command -v claude; deepseek-doctor',
                  'new-terminal',self.shell,env=fresh_env)

    def test_install_without_setup_path_leaves_shell_config_untouched(self):
        self.install()
        self.assertFalse((self.home/'.bashrc').exists())
        self.assertFalse(self.shell.exists())

    def test_custom_config_and_prefix_with_spaces_are_reloaded_in_new_shell(self):
        conf = self.home/'custom configuration'
        prefix = self.home/'custom tools/bin'
        env = dict(self.env,DEEPSEEK_WORKER_CONF_DIR=str(conf),LLM_API_KEY='offline-portability-fixture-key')
        self.call(self.clone/'install.sh','--non-interactive','--prefix',prefix,'--setup-path',env=env)
        result = self.call('bash','--noprofile','--norc','-c',
                          '. "$1"; command -v deepseek-task; printf "%s" "$DEEPSEEK_WORKER_CONF_DIR"',
                          'portable-shell',conf/'shell.sh')
        self.assertEqual(result.stdout.splitlines(),[str(prefix/'deepseek-task'),str(conf)])

    def test_doctor_fails_on_old_or_missing_cli_without_creating_settings(self):
        self.claude.unlink()
        self.call(self.clone/'install.sh','--check',code=1)
        self.assertFalse(self.conf.exists())
        self.claude.write_text('#!/bin/sh\necho 2.1.100\n')
        self.claude.chmod(0o755)
        self.call(self.clone/'install.sh','--check',code=1)
        self.assertFalse(self.conf.exists())

    def test_update_repairs_source_path_after_checkout_is_moved(self):
        self.install('--setup-path')
        original=(self.conf/'env').read_bytes()
        moved=self.home/'moved checkout'
        self.clone.rename(moved)
        self.clone=moved
        self.sourced(['deepseek-doctor'],code=1)
        self.install('--update',key=False)
        self.sourced(['deepseek-doctor'])
        self.assertEqual((self.conf/'env').read_bytes(),original)
        self.assertEqual((self.conf/'kit_dir').read_text().strip(),str(moved))

    def test_offline_install_only_needs_no_claude_or_key(self):
        self.claude.unlink()
        self.install('--install-only','--setup-path',key=False)
        self.assertTrue((self.bin/'deepseek-doctor').is_file())
        self.assertFalse((self.conf/'env').exists())
        result=self.sourced(['deepseek-worker','-p','hi'],code=2)
        self.assertIn('env',result.stderr)


if __name__=='__main__':unittest.main()
