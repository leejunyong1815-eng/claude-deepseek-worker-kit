# 기존 원격 전송 명령

`remote-info`, `remote-sync`, `remote-run`, `remote-submit`, `remote-fetch`는 기존 SSH·rsync 도우미다.
대기·GPU 배정·시간 제한·원격 취소·독립 검증이 필요한 실행은 [Compute Job](COMPUTE_JOBS.md)을 사용한다.
도우미로 직접 시작한 잡을 관리 태스크 취소가 종료해 주지는 않는다.

## 설정

기본값은 `$LLM_WORKER_CONF_DIR/env`, 프로필은 `env.<프로필>`에서 읽는다.
`llm-worker -P impl`과 관리 태스크는 하위 도구에 같은 프로필을 전달한다.
직접 실행할 때는 `LLM_WORKER_PROFILE=impl remote-sync`처럼 선택한다.
프로필을 지정하지 않으면 설정 파일 없이 실행 환경의 COMPUTE_HOST만으로도 사용할 수 있다.

```bash
# env 또는 env.impl에 추가할 공개 연결 설정. SSH 키는 넣지 않는다.
export COMPUTE_HOST=lab-compute
export COMPUTE_WORK_DIR=claude-work
export COMPUTE_SSH_CONFIG="$HOME/.ssh/lab_config"
```

실행 환경에서 명시한 `COMPUTE_HOST`, `COMPUTE_WORK_DIR`, `COMPUTE_SSH_CONFIG`가 파일보다 우선한다.
명시적으로 비운 HOST는 오류이며 파일 값으로 다시 채우지 않는다. SSH_CONFIG를 비우면 SSH 기본 설정을 사용한다.
SSH_CONFIG가 있으면 SSH와 rsync의 전송 SSH 모두에 `-F`를 전달한다. BatchMode와 기존 호스트 키 확인을 유지한다.
호스트는 SSH 별칭 또는 user@host이며, 작업 디렉터리는 원격 홈 기준 상대 경로나 절대 경로다. `~`, `..`, `/` 단독은 받지 않는다.

```bash
COMPUTE_HOST=other-lab COMPUTE_SSH_CONFIG="$HOME/.ssh/other config" \
  remote-run 'python3 experiment.py --output outputs/result.json'
```

## 복사본과 결과

원격 경로는 `<COMPUTE_WORK_DIR>/<checkout 이름>-<절대 경로 해시>`다. 같은 이름의 저장소나
관리 모드의 `.../attempts/0001/worktree`들도 서로 다른 원격 경로를 사용한다. 시도가 달라져도 분리된다.
매번 선택한 경로를 출력하며, `remote-submit`의 tmux 잡 이름에도 같은 namespace를 붙인다.
잡의 표시 이름이 같아도 다른 worktree의 tmux 잡과 충돌하지 않는다.

`remote-sync`는 `.git` 파일·디렉터리를 전송하지 않으며 `outputs/`는 별도로 회수한다.
`rsync --delete`를 사용하지 않는다. 원격에만 있는 파일과 이전 시도는 보존한다.
따라서 로컬에서 지운 파일이 원격에 남을 수 있으며, 도우미의 원격 복사본을 정확한 소스 스냅샷이라고 간주하면 안 된다.
이전 버전의 `<COMPUTE_WORK_DIR>/<프로젝트 이름>` 경로는 자동 이동·삭제·재사용하지 않는다.

`remote-run`은 동기화 후 명령을 실행하고, 실패해도 outputs 회수를 시도한 뒤 원격 명령 종료 코드를 반환한다.
결과 회수 실패는 이 종료 코드를 바꾸지 않으므로 필요한 산출물은 별도로 확인한다.
`remote-submit`은 원격 tmux에서 시작하며 `remote-fetch`가 같은 checkout의 outputs를 내려받는다.
관리 태스크에서 결과를 회수한다면 명세의 allowed_paths에 필요한 outputs 경로를 포함한다.
한 checkout의 같은 잡 이름을 동시에 제출하거나 같은 원격 복사본을 동시에 편집하는 용도로 쓰지 않는다.
서로 다른 프로필도 같은 호스트·작업 경로·checkout을 선택하면 같은 복사본을 사용한다.

이 도우미는 보안 샌드박스나 원격 스케줄러가 아니다. 실행 범위·리소스 예산·산출물·검증 기준은 태스크에 명시한다.
임의 원격 명령의 동작은 로컬 diff 검사로 보증할 수 없다.
