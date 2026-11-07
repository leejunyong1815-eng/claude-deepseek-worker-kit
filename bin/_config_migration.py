"""Import legacy settings into named servers/profiles without changing the source."""
import json
import os
import tempfile
from pathlib import Path
import re
import shlex
from _backends import atomic, env_file, GENERAL, validate

def import_profiles(source, target, prefix='', in_place=False):
    source = Path(source).expanduser().resolve()
    target = Path(target).resolve()
    gateway = env_file(source / 'gateway.env')
    bindings = {}
    servers = {}
    pending = []
    count = 0
    for path in sorted(source.glob('env*')):
        if path.name != 'env' and (not path.name.startswith('env.')):
            continue
        values = env_file(path)
        if not values.get('LLM_MODEL'):
            continue
        suffix = path.name[4:] if path.name.startswith('env.') else ''
        name = '-'.join((x for x in (prefix, suffix) if x))
        connection = gateway or values
        if in_place and connection.get('LLM_BASE_URL', '').rstrip('/') == 'http://133.186.146.224:8081':
            continue
        key = connection.get('LLM_API_KEY', '')
        auth = connection.get('LLM_AUTH_MODE', 'none' if key in ('', 'none', 'dummy') else 'api_key')
        group = (connection.get('LLM_BASE_URL', ''), auth, key)
        if group not in servers:
            backend = '-'.join((x for x in ('imported', prefix, suffix or 'main') if x))
            backend = re.sub('[^A-Za-z0-9_-]', '-', backend)[:64]
            servers[group] = (backend, dict(url=group[0], auth=auth, key=key, max_parallel=2, models=[]))
        backend, data = servers[group]
        role = 'compute-runner' if values.get('WORKER_ROLE') == 'compute-runner' or suffix == 'qwen' else None
        model = dict(id=values['LLM_MODEL'], context=int(values.get('LLM_CONTEXT_WINDOW', '262144')), roles=[role] if role else GENERAL)
        existing = next((m for m in data['models'] if m['id'] == model['id']), None)
        if existing:
            existing['roles'] = list(dict.fromkeys(existing['roles'] + model['roles']))
        else:
            data['models'].append(model)
        if not in_place:
            dest = target / ('env' + ('.' + name if name else ''))
            copied = dict(values, LLM_BACKEND=backend, WORKER_NAME='llm-worker-' + (name or 'default'))
            content = '# Imported private profile; do not commit.\n' + ''.join(('export ' + k + '=' + shlex.quote(v) + '\n' for k, v in copied.items()))
            if dest.exists() and dest.read_text() != content:
                raise ValueError('import would overwrite an existing profile: ' + name)
            pending.append((dest, content))
        bindings[name] = backend
        count += 1
    for _, (name, data) in servers.items():
        data = validate(data)
        path = target / 'backends' / (name + '.json')
        if path.exists() and json.loads(path.read_text()) != data:
            raise ValueError('import backend name already exists: ' + name)
        atomic(path, data)
    for dest, content in pending:
        fd, temp = tempfile.mkstemp(dir=target)
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(content)
            os.replace(temp, dest)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
    if in_place and bindings:
        path = target / 'profile-backends.json'
        old = json.loads(path.read_text()) if path.is_file() else {}
        for key, value in bindings.items():
            if key in old and old[key] != value:
                raise ValueError('profile already has a backend binding')
        atomic(path, dict(old, **bindings))
    return count
