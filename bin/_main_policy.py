"""Shared launcher policy; native reasoning defaults to selective delegation."""
from pathlib import Path

NATIVE_MODES = ('off', 'selective')
NATIVE_DEFAULT = 'selective'


def native_args(args, default=NATIVE_DEFAULT):
    """Consume kit options before --, preserving native CLI arguments and order."""
    mode, forward = default, []
    args = iter(args)
    for arg in args:
        if arg == '--':
            forward += [arg, *args]
            break
        if arg == '--native-agents':
            mode = next(args, '')
        elif arg.startswith('--native-agents='):
            mode = arg.split('=', 1)[1]
        else:
            forward.append(arg)
            continue
        if mode not in NATIVE_MODES:
            raise ValueError('--native-agents must be off or selective')
    return mode, forward


def render(kit, mode, kind='claude'):
    if mode not in NATIVE_MODES:
        raise ValueError('--native-agents must be off or selective')
    policy = (Path(kit) / 'prompts/orchestrator.md').read_text()
    if kind == 'codex':
        policy = policy.replace("Your main model uses the user's Claude account.",
                                "Your main model uses the user's Codex account/configuration.")
    policy += '\nNative delegation mode: ' + mode + '\n'
    if mode == 'selective':
        policy += (Path(kit) / 'prompts/native-agents.md').read_text()
    else:
        policy += ('Native subagents and forked skills are disabled for this session. '
                   'Use registered LLM workers for delegation; do not launch another main from Bash.\n')
    return policy


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kit', type=Path, required=True)
    parser.add_argument('--kind', choices=('claude', 'codex'), default='claude')
    parser.add_argument('--native-agents', choices=NATIVE_MODES, default=NATIVE_DEFAULT)
    args = parser.parse_args()
    try:
        print(render(args.kit, args.native_agents, args.kind))
    except OSError as exc:
        parser.exit(2, 'main policy unavailable; run install.sh --update: ' + str(exc) + '\n')
