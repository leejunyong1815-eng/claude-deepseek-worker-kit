"""Private server/model registry. No inference, model fallback, or secret output."""
import contextlib
import fcntl
import json
import os
from pathlib import Path
import re
import shlex
import tempfile
from urllib.parse import urlsplit
from _kit_env import configure
configure()
NAME = re.compile('[A-Za-z0-9][A-Za-z0-9_-]{0,63}')
GENERAL = ['researcher', 'planner', 'implementer', 'test-author', 'runner', 'analyst', 'reviewer']
ROLES = GENERAL + ['compute-runner']

def conf_dir():
    return Path(os.environ['LLM_WORKER_CONF_DIR']).expanduser().resolve()

def valid_name(name):
    if not isinstance(name, str) or not NAME.fullmatch(name):
        raise ValueError('invalid backend name')
    return name

def env_file(path):
    result = {}
    if path.is_file():
        for line in path.read_text().splitlines():
            key, sep, raw = line.removeprefix('export ').partition('=')
            if sep and re.fullmatch('[A-Z_]+', key):
                parts = shlex.split(raw, comments=True)
                if len(parts) > 1:
                    raise ValueError('unsupported environment syntax: ' + key)
                result[key] = parts[0] if parts else ''
    return result

def validate(data):
    url = data.get('url', '').rstrip('/')
    u = urlsplit(url)
    if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password or u.query or u.fragment or u.path.endswith('/v1'):
        raise ValueError('use an http(s) Anthropic endpoint without credentials, query or trailing /v1')
    if data.get('auth') not in ('none', 'api_key') or (data['auth'] == 'api_key' and (not data.get('key'))):
        raise ValueError('authentication must be none or api_key with a private key')
    if type(data.get('max_parallel', 2)) is not int or not 1 <= data.get('max_parallel', 2) <= 32:
        raise ValueError('max_parallel must be in [1, 32]')
    models = data.get('models')
    if not isinstance(models, list) or not models:
        raise ValueError('register at least one model')
    seen = set()
    for model in models:
        mid = model.get('id') if isinstance(model, dict) else None
        if not isinstance(mid, str) or not mid.strip() or any((ord(c) < 32 for c in mid)) or (mid in seen):
            raise ValueError('models need unique nonempty IDs')
        seen.add(mid)
        if type(model.get('context')) is not int or model['context'] <= 0:
            raise ValueError('model context must be a positive integer')
        if not isinstance(model.get('roles'), list) or any((r not in ROLES for r in model['roles'])):
            raise ValueError('invalid model roles')
    return dict(data, url=url)

def load(name='default', profile=''):
    valid_name(name)
    conf = conf_dir()
    if name != 'default':
        data = json.loads((conf / 'backends' / (name + '.json')).read_text())
        return validate(data)
    settings = env_file(conf / ('env' + ('.' + profile if profile else '')))
    gateway = conf / 'gateway.env'
    if not gateway.is_file():
        raise ValueError('shared gateway missing; run install.sh --update')
    connection = env_file(gateway)
    model = settings.get('LLM_MODEL', 'deepseek-v4.1-flash')
    context = int(settings.get('LLM_CONTEXT_WINDOW', '262144'))
    models = [{'id': model, 'context': context, 'roles': GENERAL}]
    qwen = env_file(conf / 'env.qwen')
    qid = qwen.get('LLM_MODEL', 'qwen3.8-flash-next')
    if qid != model:
        models.append({'id': qid, 'context': int(qwen.get('LLM_CONTEXT_WINDOW', context)), 'roles': ['compute-runner']})
    else:
        models[0]['roles'] = ROLES
    return validate({'url': connection.get('LLM_BASE_URL', ''), 'auth': connection.get('LLM_AUTH_MODE', 'api_key'), 'key': connection.get('LLM_API_KEY', ''), 'models': models, 'max_parallel': 2})

def choose(profile='', backend=None, model=None, role=None):
    conf = conf_dir()
    settings = env_file(conf / ('env' + ('.' + profile if profile else '')))
    bindings = json.loads((conf / 'profile-backends.json').read_text()) if (conf / 'profile-backends.json').is_file() else {}
    active = (conf / 'default-backend').read_text().strip() if (conf / 'default-backend').is_file() else None
    selected = backend or settings.get('LLM_BACKEND') or (bindings.get(profile) if profile else None) or active or bindings.get('') or 'default'
    data = load(selected, profile)
    if model:
        candidates = [m for m in data['models'] if m['id'] == model]
    elif profile and settings.get('LLM_MODEL'):
        candidates = [m for m in data['models'] if m['id'] == settings['LLM_MODEL']]
    elif role:
        candidates = sorted((m for m in data['models'] if role in m['roles']), key=lambda m: len(m['roles']))
    else:
        candidates = data['models'][:1]
    if not candidates:
        raise ValueError('no registered model matches the requested model/profile/role')
    return (selected, data, candidates[0])

def public(name, data):
    return {'name': name, 'url': data['url'], 'auth': data['auth'], 'key_configured': bool(data.get('key')), 'max_parallel': data.get('max_parallel', 2), 'models': data['models']}

def catalog():
    result = []
    conf = conf_dir()
    names = (['default'] if (conf / 'gateway.env').is_file() else []) + [p.stem for p in sorted((conf / 'backends').glob('*.json'))]
    for name in names:
        result.append(public(name, load(name)))
    return result

@contextlib.contextmanager
def locked():
    conf = conf_dir()
    conf.mkdir(parents=True, exist_ok=True, mode=448)
    with (conf / '.backend.lock').open('a') as stream:
        os.chmod(stream.name, 384)
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield conf

def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=448)
    fd, tmp = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            json.dump(value, out, ensure_ascii=False, indent=2)
            out.write('\n')
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def shell(profile, backend, model):
    selected, data, item = choose(profile, backend or None, model or None)
    values = {'LLM_BASE_URL': data['url'], 'LLM_AUTH_MODE': data['auth'], 'LLM_API_KEY': data.get('key', ''), 'LLM_MODEL': item['id'], 'LLM_CONTEXT_WINDOW': str(item['context']), 'LLM_ACTIVE_BACKEND': selected}
    return '\n'.join(('export ' + k + '=' + shlex.quote(v) for k, v in values.items()))
if __name__ == '__main__':
    import sys
    try:
        print(shell(*sys.argv[1:]))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        if str(exc).startswith('shared gateway missing'):
            print(str(exc), file=sys.stderr)
            sys.exit(2)
        print('backend configuration invalid or missing; run llm-backend list', file=sys.stderr)
        sys.exit(2)
