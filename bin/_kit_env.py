"""Canonical settings with read-only compatibility for both former kits."""
import os
from pathlib import Path

def configure():
    for suffix in ('WORKER_CONF_DIR', 'WORKER_PROFILE', 'WORKER_NAME', 'WORKER_ROLE', 'WORKER_KIT', 'TASK_HOME', 'PROJECT_UPDATE_HOME', 'DUO_SESSION', 'TASK_MANAGED', 'WORKER_SETTINGS'):
        current = 'LLM_' + suffix
        if current not in os.environ:
            for old in ('DEEPSEEK_' + suffix, 'CLAUDE_' + suffix):
                if old in os.environ:
                    os.environ[current] = os.environ[old]
                    break
    if 'LLM_TASK_HOME' not in os.environ and 'WORKER_TASK_HOME' in os.environ:
        os.environ['LLM_TASK_HOME'] = os.environ['WORKER_TASK_HOME']
    if 'LLM_WORKER_CONF_DIR' not in os.environ:
        choices = [Path.home() / '.config' / name for name in ('local-worker', 'claude-worker', 'deepseek-worker')]
        os.environ['LLM_WORKER_CONF_DIR'] = str(next((p for p in choices if (p / 'env').is_file()), choices[0]))
configure()
