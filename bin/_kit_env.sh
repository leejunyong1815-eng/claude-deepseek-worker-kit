# Shared environment compatibility. No credentials or user configuration are evaluated here.
for _kit_suffix in WORKER_CONF_DIR WORKER_PROFILE WORKER_NAME WORKER_ROLE WORKER_KIT TASK_HOME PROJECT_UPDATE_HOME DUO_SESSION TASK_MANAGED WORKER_SETTINGS; do
    _kit_target="LLM_$_kit_suffix"
    if [ -z "${!_kit_target+x}" ]; then
        for _kit_old in "DEEPSEEK_$_kit_suffix" "CLAUDE_$_kit_suffix"; do
            if [ -n "${!_kit_old+x}" ]; then printf -v "$_kit_target" '%s' "${!_kit_old}"; export "$_kit_target"; break; fi
        done
    fi
done
if [ -z "${LLM_TASK_HOME+x}" ] && [ -n "${WORKER_TASK_HOME+x}" ]; then export LLM_TASK_HOME="$WORKER_TASK_HOME"; fi
if [ -z "${LLM_WORKER_CONF_DIR+x}" ]; then
    LLM_WORKER_CONF_DIR="$HOME/.config/local-worker"
    for _kit_conf in "$HOME/.config/local-worker" "$HOME/.config/claude-worker" "$HOME/.config/deepseek-worker"; do
        if [ -f "$_kit_conf/env" ]; then LLM_WORKER_CONF_DIR="$_kit_conf"; break; fi
    done
    export LLM_WORKER_CONF_DIR
fi
unset _kit_suffix _kit_target _kit_old _kit_conf
