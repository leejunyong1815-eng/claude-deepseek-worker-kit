# 두 키트 통합

정식 프로젝트 이름은 Local Worker Kit이며 현재 저장소 URL은 claude-local-worker-kit이다.
DeepSeek 버전은 같은 소스의 호환 배포본으로 유지하며 서버/모델 때문에 별도 구현을 관리하지 않는다.

| 이전 명령 | 통합 명령 |
|---|---|
| claude-main / deepseek-main | claude-main |
| claude-worker / deepseek-worker | llm-worker (claude-worker도 지원) |
| worker-task / deepseek-task | worker-task 또는 llm-task |
| project-init/update / deepseek-project-init/update | project-init/update |
| llm-probe / deepseek-probe | llm-probe |
| deepseek-doctor | worker-doctor |
| claude-duo / deepseek-duo | claude-duo; 수동 메시징은 --manual |

새 기능은 codex-main/duo, 서버·모델 레지스트리(llm-backend), 소유 풀과 headless/panes 모드다.
기존 DEEPSEEK_*/CLAUDE_* 환경변수는 LLM_*의 호환 입력으로 읽는다. 명시적 LLM_*가 우선한다.
WORKER_TASK_HOME도 지원한다. 새 설정/상태는 ~/.config/local-worker와 ~/.local/state/local-worker에 둔다.
기존 폴더를 자동 이동/삭제하지 않으며, 기존 설정만 있는 환경은 그 경로를 읽는다.
기존 DeepSeek 설치 경로가 있으면 --update는 그 실행 파일 경로를 사용할 수 있다. 설치 출력의 실제 경로를 확인한다.

## 설정을 한곳으로 모으기

새 통합 설정 경로를 명시하고 두 설정을 가져온다. 원본 키와 파일은 바꾸지 않는다.

```bash
LLM_WORKER_CONF_DIR="$HOME/.config/local-worker" ./install.sh --non-interactive \
  --import-config "$HOME/.config/claude-worker" \
  --import-config "$HOME/.config/deepseek-worker" --setup-path
. "$HOME/.config/local-worker/shell.sh"
llm-backend list
```

원본 서버 연결은 imported-* 서버로, 모델은 해당 서버의 모델 목록으로 합친다.
프로필 이름은 claude / claude-impl / deepseek / deepseek-qwen처럼 원본 폴더 이름을 접두사로 붙인다.
같은 연결의 여러 모델은 서버 하나에 넣는다. 기존 gateway.env가 있는 설정은 그 연결을 우선하며
이전 프로필에 남은 오래된 URL·키를 다시 활성화하지 않는다. 대상 이름이 이미 있으면 다른 내용을 덮어쓰지 않는다.
키가 들어 있는 등록 파일은 private JSON(0600)이며 Git에 넣지 않는다.

이전 Claude 설정에 gateway.env가 없으면 --update에서 프로필별 연결을 등록해 보존한다.
이전 DeepSeek의 알려진 133.186.146.224:8081 주소는 기존 마이그레이션 규칙에 따라 새 기본값으로 전환한다.

## 기존 작업과 대화

태스크 상태와 worktree는 그대로 남는다. 필요하면 worker-task --state-dir <이전 상태 폴더> status <id>로 조회한다.
원본 명세를 수정하거나 이전 코드를 새 시도에 자동 복사하지 않는다. 재시도는 --retry로 새 시도를 만든다.
기존 성공 산출물을 변경하면 검증은 무효다. 확인되지 않은 이전 실행은 자동 재실행하지 않는다.

프로젝트 규칙은 project-update --check/--apply로 비교한다. 수정된 파일은 보존하고 incoming 제안을 병합한다.
claude-duo -- --resume 또는 codex-duo -- resume --last로 대화를 재개하면 현재 풀의 ID와 지침을 사용한다.
진행 중인 예전 프로세스에는 변경이 소급 적용되지 않는다.
