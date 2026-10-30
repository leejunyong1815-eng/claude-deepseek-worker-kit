"""Offline installer; credentials stay in a private local shell environment file."""
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
from string import Template

KIT = Path(__file__).resolve().parents[1]
BACKEND_DEFAULTS = json.loads((KIT / "config/backend.defaults.json").read_text())
ROLES = {"plan": "planner", "research": "researcher", "impl": "implementer",
         "test": "test-author", "run": "runner", "analysis": "analyst", "review": "reviewer"}


def load(path):
    values = {}
    for line in path.read_text().splitlines():
        line = line.removeprefix("export ").strip()
        if not line or line.startswith("#"):
            continue
        name, sep, value = line.partition("=")
        if sep and re.fullmatch(r"[A-Z_]+", name):
            tokens = shlex.split(value, comments=True)
            if len(tokens) > 1:
                raise ValueError("unsupported setting syntax: " + name)
            values[name] = tokens[0] if tokens else ""
    return values


def write(path, values):
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=".env-")
    try:
        with os.fdopen(fd, "w") as out:
            out.write("# Private lab backend configuration. Do not commit or share.\n")
            for name, value in values.items():
                out.write(f"export {name}={shlex.quote(value)}\n")
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def render(conf):
    for path in sorted(conf.glob("env*")):
        if path.name != "env" and not path.name.startswith("env."):
            continue
        values = load(path)
        values.setdefault("WORKER_NAME", "deepseek-worker")
        values.setdefault("LLM_MODEL", "unconfigured lab model")
        values["CONTEXT_LINE"] = "Use the configured context budget; keep evidence concise."
        values["ROLE_SECTION"] = ""  # selected at launch so task roles can override profiles
        text = Template((KIT / "prompts/worker.md.tmpl").read_text()).safe_substitute(values)
        (conf / ("worker" + path.name[3:] + ".md")).write_text(text)
    roles = conf / "roles"
    roles.mkdir(exist_ok=True)
    for src in (KIT / "prompts").glob("role-*.md.tmpl"):
        shutil.copyfile(src, roles / src.name.removesuffix(".tmpl"))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--prefix", type=Path, default=Path(os.environ.get("PREFIX", "~/.local/deepseek-worker/bin")))
    p.add_argument("--non-interactive", action="store_true")
    p.add_argument("--install-only", action="store_true", help="install tools/templates without backend credentials")
    p.add_argument("--update", action="store_true", help="preserve settings; back up and regenerate prompts offline")
    p.add_argument("--render", action="store_true")
    p.add_argument("--profile", default="")
    probe = p.add_mutually_exclusive_group()
    probe.add_argument("--probe", action="store_true", help="explicitly send small API compatibility requests")
    probe.add_argument("--skip-probe", action="store_true", help="compatibility alias; no probe is the default")
    args = p.parse_args()
    conf = Path(os.environ.get("DEEPSEEK_WORKER_CONF_DIR", "~/.config/deepseek-worker")).expanduser()
    if args.profile and not re.fullmatch(r"[A-Za-z0-9_-]+", args.profile):
        p.error("invalid profile")
    if sum((args.install_only, args.update, args.render)) > 1 or (args.update and args.profile):
        p.error("--install-only, --update and --render are exclusive; --update cannot select a profile")
    if (args.update or args.render) and not (conf / "env").is_file():
        p.error("no default configuration; install/configure the lab backend first")
    if args.probe and (args.install_only or args.update or args.render):
        p.error("--probe is only available during backend configuration")
    values = None
    target = conf / ("env" + ("." + args.profile if args.profile else ""))
    if not (args.install_only or args.update or args.render):
        inherited = load(conf / "env") if (conf / "env").is_file() else {}
        if target.is_file() and os.environ.get("FORCE_ENV") != "1":
            values = load(target)
            print("Existing configuration preserved (FORCE_ENV=1 to replace explicitly).")
        else:
            fields = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "LLM_CONTEXT_WINDOW")
            values = {k: os.environ.get(k, inherited.get(k, BACKEND_DEFAULTS.get(k, ""))) for k in fields}
            if not args.non_interactive:
                for name in fields:
                    answer = (getpass.getpass("Lab API key (hidden; Enter keeps existing): ") if name == "LLM_API_KEY"
                              else input(f"{name} [{values[name]}]: "))
                    values[name] = answer or values[name]
            for name in fields:
                value = values[name]
                if not value or "CHANGE_ME" in value or value in {"none", "dummy"}:
                    p.error(f"{name} is required; obtain the lab server settings (no official API default)")
            from urllib.parse import urlsplit
            url = urlsplit(values["LLM_BASE_URL"].rstrip("/"))
            if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment:
                p.error("LLM_BASE_URL must be an http(s) endpoint without credentials/query/fragment")
            if url.path.rstrip("/").endswith("/v1"):
                p.error("remove the trailing /v1; Claude Code appends /v1/messages")
            if not values["LLM_CONTEXT_WINDOW"].isdigit() or int(values["LLM_CONTEXT_WINDOW"]) <= 0:
                p.error("LLM_CONTEXT_WINDOW must be the lab server's positive context limit")
            values["LLM_BASE_URL"] = values["LLM_BASE_URL"].rstrip("/")
            effort = os.environ.get("LLM_EFFORT", inherited.get("LLM_EFFORT", "max"))
            if effort not in {"low", "high", "max"}:
                p.error("LLM_EFFORT must be low, high or max")
            values.update(LLM_EFFORT=effort, LLM_DISABLE_BETAS="1", LLM_DISABLE_PROMPT_CACHING="0",
                          WORKER_NAME="deepseek-worker" + ("-" + args.profile if args.profile else ""),
                          WORKER_ROLE=ROLES.get(args.profile, ""), COMPUTE_HOST="")
    conf.mkdir(parents=True, exist_ok=True, mode=0o700)
    conf.chmod(0o700)
    if not args.render:
        prefix = args.prefix.expanduser()
        prefix.mkdir(parents=True, exist_ok=True)
        for src in (KIT / "bin").iterdir():
            if src.is_file():
                shutil.copyfile(src, prefix / src.name)
                (prefix / src.name).chmod(0o755)
        (conf / "kit_dir").write_text(str(KIT) + "\n")
        print(f"Installed commands: {prefix}")
    if args.install_only:
        print("Backend unconfigured. Configure later with ./install.sh; no API requests were sent.")
        return
    if args.update:
        backup = Path(tempfile.mkdtemp(prefix="prompt-backup.", dir=conf))
        for src in conf.glob("worker*.md"):
            shutil.copy2(src, backup / src.name)
        if (conf / "roles").is_dir():
            shutil.copytree(conf / "roles", backup / "roles")
        print(f"Prompt backup: {backup}")
    if values is not None and (not target.is_file() or os.environ.get("FORCE_ENV") == "1"):
        write(target, values)
    render(conf)
    print("Prompts rendered. Local compute / WSL; requested effort=max unless configured otherwise.")
    if args.probe:
        command = [str(args.prefix.expanduser() / "deepseek-probe")]
        if args.profile:
            command += ["-P", args.profile]
        subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
