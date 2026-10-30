"""Offline update tests: history matching, custom files and existing profiles."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

KIT = Path(__file__).resolve().parents[1]


class ProjectUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.kit = self.root / "kit"
        self.source = self.kit / "templates/project"
        files = {"AGENTS.md": "rules v1\n", "KICKOFF_PROMPT.md": "kickoff\n",
                 "agents/ROLE.md": "role v1\n", ".claude/settings.json": '{"hooks": {}}\n'}
        for name, body in files.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body)
        self.git(self.kit, "init", "-q")
        self.git(self.kit, "add", "templates")
        self.commit(self.kit)
        self.project = self.root / "project"
        shutil.copytree(self.source, self.project)
        self.git(self.project, "init", "-q")
        self.git(self.project, "add", ".")
        self.commit(self.project)
        (self.source / "AGENTS.md").write_text("rules v2\n")
        (self.source / "agents/ROLE.md").write_text("role v2\n")
        (self.source / "agents/NEW.md").write_text("new role\n")
        self.state = self.root / "state"
        self.env = dict(os.environ, DEEPSEEK_WORKER_KIT=str(self.kit))

    def git(self, repo, *args):
        env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        return subprocess.check_output(["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
                                        "-C", str(repo), *args], env=env, stderr=subprocess.PIPE)

    def commit(self, repo):
        self.git(repo, "-c", "user.name=Update tests", "-c", "user.email=tests@local", "commit", "-qm", "fixture")

    def call(self, *args, code=0, env=None):
        p = subprocess.run([str(KIT / "bin/deepseek-project-update"), *args, str(self.project),
                            "--state-dir", str(self.state), "--json"], env=env or self.env,
                           capture_output=True, text=True, timeout=10)
        self.assertEqual(p.returncode, code, p.stderr + p.stdout)
        return json.loads(p.stdout)

    def snapshot(self):
        return {str(p.relative_to(self.project)): p.read_bytes() for p in self.project.rglob("*")
                if p.is_file() and ".git" not in p.relative_to(self.project).parts}

    def test_read_only_check_and_safe_apply_preserve_git_state(self):
        (self.project / "app.py").write_text("staged\n")
        self.git(self.project, "add", "app.py")
        (self.project / "app.py").write_text("unstaged\n")
        (self.project / "personal.txt").write_text("untracked\n")
        index = (self.project / ".git/index").read_bytes()
        head = self.git(self.project, "rev-parse", "HEAD")
        before = self.snapshot()
        preview = self.call("--check")
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.state.exists())
        self.assertEqual({f["status"] for f in preview["files"]}, {"current", "add", "update"})
        report = self.call("--apply")
        backup = Path(report["backup_dir"])
        self.assertEqual((self.project / "AGENTS.md").read_text(), "rules v2\n")
        self.assertEqual((backup / "before/AGENTS.md").read_text(), "rules v1\n")
        self.assertEqual((self.project / "agents/NEW.md").read_text(), "new role\n")
        self.assertEqual((self.project / "app.py").read_text(), "unstaged\n")
        self.assertEqual((self.project / "personal.txt").read_text(), "untracked\n")
        self.assertEqual((self.project / ".git/index").read_bytes(), index)
        self.assertEqual(self.git(self.project, "rev-parse", "HEAD"), head)
        self.assertEqual(json.loads((backup / "report.json").read_text())["project"], str(self.project))
        repeat = self.call("--apply")
        self.assertIsNone(repeat["backup_dir"])
        self.assertTrue(all(f["status"] == "current" for f in repeat["files"]))

    def test_custom_rules_and_settings_are_preserved(self):
        (self.project / "AGENTS.md").write_text("rules v1\nmy custom rules\n")
        custom = '{"permissions":{"allow":["Read"]}}\n'
        (self.project / ".claude/settings.json").write_text(custom)
        preview = self.call("--check", code=1)
        self.assertEqual(sum(f["status"] == "conflict" for f in preview["files"]), 2)
        report = self.call("--apply", code=1)
        self.assertEqual((self.project / "AGENTS.md").read_text(), "rules v1\nmy custom rules\n")
        self.assertEqual((self.project / ".claude/settings.json").read_text(), custom)
        self.assertEqual((Path(report["backup_dir"]) / "incoming/AGENTS.md").read_text(), "rules v2\n")
        self.assertEqual((self.project / "agents/ROLE.md").read_text(), "role v2\n")

    def test_missing_history_proposes_instead_of_overwriting(self):
        archive = self.root / "archive"
        shutil.copytree(self.kit, archive, ignore=shutil.ignore_patterns(".git"))
        env = dict(self.env, DEEPSEEK_WORKER_KIT=str(archive))
        report = self.call("--apply", code=1, env=env)
        self.assertEqual((self.project / "AGENTS.md").read_text(), "rules v1\n")
        self.assertTrue((Path(report["backup_dir"]) / "incoming/AGENTS.md").is_file())
        self.assertTrue((self.project / "agents/NEW.md").is_file())

    def test_symlink_parent_is_blocked(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "ROLE.md").write_text("private external file\n")
        (self.project / "agents/ROLE.md").unlink()
        (self.project / "agents").rmdir()
        (self.project / "agents").symlink_to(outside, target_is_directory=True)
        report = self.call("--apply", code=1)
        self.assertEqual((outside / "ROLE.md").read_text(), "private external file\n")
        self.assertFalse((outside / "NEW.md").exists())
        self.assertEqual(sum(f["status"] == "blocked" for f in report["files"]), 2)

    def test_backups_inside_project_are_rejected(self):
        before = self.snapshot()
        self.state = self.project / "backup"
        process = subprocess.run([str(KIT / "bin/deepseek-project-update"), "--apply", str(self.project),
                                  "--state-dir", str(self.state)], env=self.env, capture_output=True)
        self.assertEqual(process.returncode, 2)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.state.exists())


class InstallUpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.conf, self.prefix, mock = self.root / "conf", self.root / "bin", self.root / "mock"
        self.conf.mkdir(); mock.mkdir()
        (mock / "claude").write_text('#!/bin/sh\n[ "$1" = --version ] && { echo "2.1.314 mock"; exit 0; }\nexit 99\n')
        (mock / "curl").write_text('#!/bin/sh\ntouch "$UPDATE_NETWORK_MARKER"\nexit 99\n')
        for p in mock.iterdir():
            p.chmod(0o755)
        self.env = dict(os.environ, PATH=str(mock) + os.pathsep + os.environ["PATH"],
                        DEEPSEEK_WORKER_CONF_DIR=str(self.conf), UPDATE_NETWORK_MARKER=str(self.root / "network"),
                        FORCE_ENV="1", LLM_MODEL="must-not-replace-existing-model")
        for suffix, model in (("", "base-model"), (".impl", "impl-model")):
            data = ('export LLM_BASE_URL="http://unused.invalid"\nexport LLM_API_KEY="fake-update-test-key"\n'
                    f'export LLM_MODEL="{model}"\nexport LLM_CONTEXT_WINDOW="12345"\n'
                    'export COMPUTE_HOST=""\nexport COMPUTE_WORK_DIR="work"\nexport COMPUTE_DESC=""\n'
                    f'export WORKER_NAME="worker{suffix}"\nexport WORKER_ROLE="{"impl" if suffix else ""}"\n')
            (self.conf / ("env" + suffix)).write_text(data)
            (self.conf / ("env" + suffix)).chmod(0o600)
            (self.conf / ("worker" + suffix + ".md")).write_text("old custom prompt " + suffix)

    def call(self, *args):
        return subprocess.run([str(KIT / "install.sh"), *args, "--prefix", str(self.prefix)],
                              env=self.env, capture_output=True, text=True, timeout=12)

    def test_update_preserves_config_renders_all_profiles_and_backs_up(self):
        before = {p.name: p.read_bytes() for p in self.conf.glob("env*")}
        result = self.call("--update")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual({p.name: p.read_bytes() for p in self.conf.glob("env*")}, before)
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in self.conf.glob("env*")))
        self.assertIn("base-model", (self.conf / "worker.md").read_text())
        self.assertIn("impl-model", (self.conf / "worker.impl.md").read_text())
        self.assertIn("Implementer discipline", (self.conf / "roles/role-implementer.md").read_text())
        backups = list(self.conf.glob("prompt-backup.*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "worker.impl.md").read_text(), "old custom prompt .impl")
        self.assertFalse((self.root / "network").exists())
        self.assertTrue((self.prefix / "deepseek-project-update").is_file())

    def test_invalid_combination_does_not_install(self):
        result = self.call("--update", "--profile", "impl")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.prefix.exists())
        self.assertFalse((self.root / "network").exists())

    def test_missing_default_config_does_not_install(self):
        (self.conf / "env").unlink()
        result = self.call("--update")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(self.prefix.exists())
        self.assertFalse((self.root / "network").exists())


if __name__ == "__main__":
    unittest.main()
