"""Permission policy for managed DeepSeek workers (Python stdlib only).

A managed task runs ``claude -p`` with ``--settings <file>``.  In print mode
nobody can approve a tool prompt, so every tool a worker needs must be granted
up front; otherwise the worker is silently reduced to conversation and cannot
write reports or run tests.  This module turns task JSON into a small frozen
policy and that policy into a settings document:

    normalize_permissions(raw, spec_dir)  -> policy dict (JSON serialisable)
    build_settings(policy, worktree, repository, protected_paths) -> settings

Design notes
------------
* Read paths are registered, not required to exist: a data disk may be mounted
  after the task is submitted.  Relative read paths are resolved once against
  the task spec directory; every other path must already be absolute.
* File access uses absolute ``//`` path patterns and scoped ``Edit(...)``
  rules, so the CLI never needs a bare ``Edit``/``Write`` grant (``Write(path)``
  rules never match).  The assigned worktree is writable, each read path is
  read-only, and scratch patterns are read/write.
* The original checkout, worktree ``.git``, protected paths and the kit's own
  control directories stay denied for native edits even when the caller omits
  them.
* Git mutations, ``ssh`` and ``rsync`` are denied as shell command patterns.

Security
--------
The general ``Bash`` grant is arbitrary user code.  It is what lets a worker
run Python, Node or project scripts, and it is *not* a filesystem sandbox:
anything Bash starts can read or write whatever the OS user can, including
paths denied above for the file tools.  Command deny patterns are prefix
checks on the requested command line, not an OS policy, so they do not prevent
indirect effects such as ``python -c`` rewriting a protected file or a script
invoking git.  Real containment has to come from the runner, the OS user and
the external verification of changed files, not from these rules.
"""
import json
import os
import posixpath
import re
from pathlib import Path


PROFILES = ("workspace", "custom", "inherit")
DEFAULT_PROFILE = "workspace"
DEFAULT_PROTECTED = (".claude/", "tests/", "config/", ".task-inputs/")
GIT_MUTATING = ("add", "commit", "checkout", "switch", "reset", "restore", "clean",
                "stash", "merge", "rebase", "push", "update-ref")
LOCAL_TOOLS = ("Bash", "WebFetch", "WebSearch", "Agent", "Task", "TaskOutput",
               "TaskStop", "Skill", "TodoWrite", "ToolSearch", "LSP", "Grep", "Glob")
SHELL_DENY = tuple("Bash(git %s:*)" % command for command in GIT_MUTATING) + (
    "Bash(ssh:*)", "Bash(rsync:*)") + tuple(
        "Bash(git worktree %s:*)" % command
        for command in ("add", "remove", "move", "prune", "repair", "lock", "unlock")) + tuple(
        "Bash(git branch %s:*)" % flag for flag in ("-d", "-D", "-m", "-M", "-c", "-C", "--delete", "--move", "--copy"))
# Do not deny the whole branch/tag/worktree families: branch --show-current,
# tag --list and worktree list are legitimate read-only inspection commands.
RULE = re.compile(r"(Read|Edit|Write|MultiEdit|NotebookEdit|Glob)\((.*)\)", re.S)


def _dedupe(values):
    return list(dict.fromkeys(values))


def _is_text(value):
    return isinstance(value, str) and bool(value.strip()) and not any(ord(c) < 32 for c in value)


def _check_text(value, label):
    if not _is_text(value):
        raise ValueError(label + " must be a nonempty single-line string")
    if value != value.strip():
        raise ValueError(label + " must not have surrounding whitespace: " + repr(value))
    if "\\" in value:
        raise ValueError(label + " must use forward slashes: " + value)
    if "~" in value:
        raise ValueError(label + " must not use '~': " + value)
    if ".." in value.split("/"):
        raise ValueError(label + " must not traverse upwards: " + value)
    return value


def _plain_absolute(value, label):
    if value.startswith("//"):
        raise ValueError(label + " must be a plain absolute path: " + value)
    value = posixpath.normpath(value).rstrip("/")
    if not value:
        raise ValueError(label + " must not be the filesystem root")
    return value


def _read_path(value, spec_dir, label):
    value = _check_text(value, label)
    if value.startswith("/"):
        return _plain_absolute(value, label)
    candidate = spec_dir / value
    # Relative entries are resolved now; absolute entries may be mounted later.
    if not candidate.exists():
        raise ValueError(label + " relative path does not exist: " + value)
    return str(candidate.resolve())


def _scratch_path(value, label):
    value = _check_text(value, label)
    if not value.startswith("/"):
        raise ValueError(label + " must be an absolute path or pattern: " + value)
    value = _plain_absolute(value, label)
    # Keep wildcards, but a pattern rooted at / (or / * / **) is the whole disk.
    core = value
    if core.endswith("/**"):
        core = core[:-3]
    if not core.strip("/") or set(core.strip("/")) <= set("*?"):
        raise ValueError(label + " must not target the filesystem root: " + value)
    return value


def _entry_list(raw, name):
    value = raw.get(name, [])
    if not isinstance(value, list):
        raise ValueError(name + " must be a list of paths")
    for item in value:
        if not isinstance(item, str):
            raise ValueError(name + " entries must be strings")
    return value


def _rule_list(value, name):
    if not isinstance(value, list):
        raise ValueError(name + " must be a list of permission rules")
    for rule in value:
        if not _is_text(rule):
            raise ValueError(name + " entries must be nonempty single-line strings")
    return list(value)


def _load_rules(value, spec_dir):
    value = _check_text(value, "permissions_file")
    path = Path(value) if value.startswith("/") else spec_dir / value
    if not path.is_file():
        raise ValueError("permissions_file does not exist: " + value)
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ValueError("invalid permissions_file JSON: " + str(exc))
    if not isinstance(data, dict):
        raise ValueError("permissions_file must contain a JSON object")
    # Accept {"permissions": {...}} or a direct permissions object; copy only
    # the rule lists, never hooks/model/env/auth/defaultMode and friends.
    permissions = data.get("permissions", data)
    if not isinstance(permissions, dict):
        raise ValueError("permissions_file permissions must be an object")
    return {key: _rule_list(permissions.get(key, []), "permissions_file " + key)
            for key in ("allow", "ask", "deny")}


def normalize_permissions(raw, spec_dir):
    """Freeze the permission-related task fields into a JSON-serialisable dict."""
    if not isinstance(raw, dict):
        raise ValueError("task spec must be a JSON object")
    spec_dir = Path(spec_dir)
    profile = raw.get("permission_profile", DEFAULT_PROFILE)
    if not isinstance(profile, str) or profile not in PROFILES:
        raise ValueError("permission_profile must be one of: " + ", ".join(PROFILES))
    read_paths = _dedupe([_read_path(item, spec_dir, "read_paths[%d]" % index)
                          for index, item in enumerate(_entry_list(raw, "read_paths"))])
    scratch_paths = _dedupe([_scratch_path(item, "scratch_paths[%d]" % index)
                             for index, item in enumerate(_entry_list(raw, "scratch_paths"))])
    permissions_file = raw.get("permissions_file")
    if profile == "inherit":
        if read_paths or scratch_paths or permissions_file is not None:
            raise ValueError("permission_profile=inherit accepts no read_paths, "
                             "scratch_paths or permissions_file")
        return {"profile": "inherit", "read_paths": [], "scratch_paths": [],
                "rules": {"allow": [], "ask": [], "deny": []}}
    if permissions_file is None:
        if profile == "custom":
            raise ValueError("permission_profile=custom requires permissions_file")
        rules = {"allow": [], "ask": [], "deny": []}
    else:
        rules = _load_rules(permissions_file, spec_dir)
    return {"profile": profile, "read_paths": read_paths, "scratch_paths": scratch_paths,
            "rules": {key: _dedupe(value) for key, value in rules.items()}}


def _absolute_root(value, name):
    value = str(value)
    if not _is_text(value) or "\\" in value:
        raise ValueError(name + " must be a plain absolute path")
    if not value.startswith("/"):
        raise ValueError(name + " must be absolute: " + value)
    value = posixpath.normpath(value).rstrip("/")
    if not value:
        raise ValueError(name + " must not be the filesystem root")
    return value


def _escape(text):
    """Escape gitignore wildcard syntax in a literal path prefix."""
    return "".join("\\" + char if char in "\\*?[]" else char for char in text)


def _absolute_pattern(prefix, suffix=""):
    body = _escape(prefix).rstrip("/")
    if suffix:
        body += "/" + suffix.lstrip("/")
    return "//" + body.lstrip("/")


def _is_directory(path):
    # A path that does not exist yet (e.g. a disk mounted later) is treated as
    # a directory so its contents are covered too.
    return not os.path.isfile(path)


def _literal_rules(tool, path, directory=None):
    base = _absolute_pattern(path)
    if directory is None:
        directory = _is_directory(path)
    return ["%s(%s)" % (tool, base)] + (["%s(%s/**)" % (tool, base)] if directory else [])


def _pattern_rules(tool, pattern):
    core = pattern.rstrip("/")
    if core.endswith("/**"):
        core = core[:-3].rstrip("/")
    base = "//" + core.lstrip("/")
    return ["%s(%s)" % (tool, base), "%s(%s/**)" % (tool, base)]


def _rebase_rule(rule, worktree):
    """Rebase a settings-relative Read/Edit rule onto the assigned worktree.

    The --settings file lives outside the worktree, so a single leading slash
    would resolve against the wrong directory.  Absolute ``//...`` and ``~/...``
    patterns are already unambiguous and stay untouched.
    """
    match = RULE.fullmatch(rule)
    if not match:
        return rule
    tool, pattern = match.groups()
    tool = {"Write": "Edit", "MultiEdit": "Edit", "NotebookEdit": "Edit", "Glob": "Read"}.get(tool, tool)
    if not pattern.startswith("/") or pattern.startswith("//"):
        return "%s(%s)" % (tool, pattern)
    if ".." in pattern.split("/"):
        raise ValueError("permission rule escapes the worktree: " + rule)
    return "%s(%s)" % (tool, _absolute_pattern(worktree, pattern.lstrip("/")))


def _policy_paths(policy, key):
    value = policy.get(key, [])
    if not isinstance(value, list):
        raise ValueError(key + " must be a list")
    for item in value:
        if not _is_text(item):
            raise ValueError(key + " entries must be nonempty single-line strings")
        if not item.startswith("/") or item.startswith("//"):
            raise ValueError(key + " entries must be plain absolute paths: " + item)
        if "\\" in item or "~" in item or ".." in item.split("/"):
            raise ValueError(key + " entry is not a safe path: " + item)
    return value


def _protected_rules(worktree, entry):
    if not _is_text(entry) or "\\" in entry or "~" in entry:
        raise ValueError("protected path is not safe: " + repr(entry))
    segments = [part for part in entry.split("/") if part]
    if not segments or ".." in segments:
        raise ValueError("protected path is not safe: " + entry)
    suffix = "/".join(segments)
    base = _absolute_pattern(worktree if not entry.startswith("/") else "/", suffix)
    return ["Edit(%s)" % base, "Edit(%s/**)" % base]


def build_settings(policy, worktree, repository, protected_paths):
    """Return the --settings document for a normalized policy (None for inherit)."""
    if not isinstance(policy, dict):
        raise ValueError("permission policy must be a JSON object")
    profile = policy.get("profile")
    if not isinstance(profile, str) or profile not in PROFILES:
        raise ValueError("invalid permission profile")
    if profile == "inherit":
        return None
    worktree = _absolute_root(worktree, "worktree")
    repository = _absolute_root(repository, "repository")
    if protected_paths is None:
        protected_paths = []
    if not isinstance(protected_paths, (list, tuple)):
        raise ValueError("protected_paths must be a list")

    supplied = policy.get("rules", {})
    if not isinstance(supplied, dict):
        raise ValueError("policy rules must be an object")
    allow_user = [_rebase_rule(rule, worktree) for rule in
                  _rule_list(supplied.get("allow", []), "allow")]
    ask = [_rebase_rule(rule, worktree) for rule in
           _rule_list(supplied.get("ask", []), "ask")]
    deny_user = [_rebase_rule(rule, worktree) for rule in
                 _rule_list(supplied.get("deny", []), "deny")]
    read_paths = _policy_paths(policy, "read_paths")
    scratch_paths = _policy_paths(policy, "scratch_paths")

    read_rules, edit_rules = [], []
    if profile == "workspace":
        read_rules += _literal_rules("Read", worktree, True)
        edit_rules += _literal_rules("Edit", worktree, True)
    for path in read_paths:
        read_rules += _literal_rules("Read", path)
    for pattern in scratch_paths:
        read_rules += _pattern_rules("Read", pattern)
        edit_rules += _pattern_rules("Edit", pattern)

    allow = list(allow_user)
    if profile == "workspace":
        # Grep/Glob plus the non-filesystem tools; file writes only travel
        # through the scoped Edit rules above (Write(path) never matches).
        allow += list(LOCAL_TOOLS)
    allow += read_rules + edit_rules

    deny = list(deny_user)
    deny += _literal_rules("Edit", repository, True)
    deny += _literal_rules("Edit", posixpath.join(worktree, ".git"), True)
    for name in DEFAULT_PROTECTED:
        deny += _literal_rules("Edit", posixpath.join(worktree, name.rstrip("/")), True)
    for entry in protected_paths:
        deny += _protected_rules(worktree, entry)
    for path in read_paths:
        # A read path is a reference: readable, never writable via file tools.
        deny += _literal_rules("Edit", path)
    deny += list(SHELL_DENY)

    return {"crossSessionInbound": "accept",
            "permissions": {"defaultMode": "dontAsk",
                            "allow": _dedupe(allow),
                            "ask": _dedupe(ask),
                            "deny": _dedupe(deny)}}
