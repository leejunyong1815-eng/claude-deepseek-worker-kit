# 기존 설치·프로젝트 갱신

요약 절차는 [README 업데이트 안내](../README.md#업데이트)에 있다.
실행 중 작업은 먼저 종료하거나 끝날 때까지 기다린다. 업데이트는 모델 호출이나 작업 종료를 자동 수행하지 않는다.

## 실행기와 프로필 프롬프트

키트 소스를 `git pull --ff-only`로 갱신하고 `./install.sh --update`를 실행한다.
로컬 변경이 pull을 막으면 자동으로 stash·reset하지 않고 사용자가 변경을 검토한다.

`--update`의 범위는 다음과 같다.

- `~/.local/bin`(또는 `--prefix`)의 키트 실행기 교체
- 설정 디렉터리의 `kit_dir`를 현재 키트 경로로 갱신
- 기존 `worker.md`·`worker.<프로필>.md`와 `roles/`를 `prompt-backup.*`에 백업
- 기본·추가 프로필의 생성 프롬프트 재렌더링과 역할 프롬프트 갱신
- 공통 연결 파일 `gateway.env`가 없으면 최초 생성 (권한 `0600`)

`env`, `env.<프로필>`, 프로젝트 파일, API 키, 모델·컨텍스트 설정은 변경하지 않는다.
기존 `gateway.env`도 유지한다. 처음 생성할 때 기본 env의 연결을 사용하며, 알려진 이전 주소
`http://133.186.146.224:8081`만 현재 기본 `http://1.233.219.161:4000`으로 옮긴다.
이 경우 이전 서버의 키를 새 게이트웨이에 복사하지 않는다. 다른 사용자 지정 URL은 유지한다.
서버를 별도로 지정하지 않은 호환 연결은 이 공통 파일을 사용한다. 등록된 backend를 선택하면 해당 서버 설정을 사용한다.
이전 Claude 설정에 공통 파일이 없었다면 프로필별 서버를 먼저 등록해 보존한다. 통합 가져오기는 MIGRATION.md를 따른다.
서버 조회·프로브·모델 호출·새 프로필 생성도 하지 않는다. 설정 갱신에는 실제 Claude CLI나 서버가 필요하지 않다.
`./install.sh --check` 또는 설치된 `worker-doctor`로 로컬 필수 도구와 Claude CLI를 확인할 수 있다. API는 호출하지 않는다.
PATH를 Bash에 등록하려면 `./install.sh --update --setup-path`를 사용한다. 생성된 shell.sh를 ~/.bashrc에서 한 번 읽게 하며 기존 설정은 보존한다.
키트 checkout을 다른 경로로 옮겼다면 새 위치에서 --update를 실행해 kit_dir를 갱신한다.
기존 설정이 없다면 일반 설치를 먼저 한다. `--update`와 `--profile`/`--render`는 함께 사용할 수 없다.
별도 설정 경로는 기존처럼 `LLM_WORKER_CONF_DIR`로 지정한다.

생성 프롬프트를 직접 수정해 사용했다면 백업과 새 파일을 비교한다. 복원하려면 필요한 파일만 백업에서 되돌린다.
env 파일은 이 업데이트에서 바뀌지 않으므로 연결 설정을 다시 입력할 필요가 없다.

## 프로젝트 운영 규칙

```bash
project-update --check ~/my-project
project-update --apply ~/my-project
```

갱신 대상은 `templates/project`가 제공하는 AGENTS·KICKOFF·역할·태스크 양식·검사 훅·`.claude/settings.json`이다.
프로젝트의 다른 코드·태스크·결과는 건드리지 않는다.

| 표시 | 의미 | apply 동작 |
|---|---|---|
| `current` | 현재 템플릿과 동일 | 유지 |
| `add` | 파일이 없음 | 새 템플릿 추가 |
| `update` | 키트 Git 이력의 과거 템플릿과 동일 | 이전 파일 백업 후 교체 |
| `conflict` | 사용자 수정 또는 과거 버전 확인 불가 | 기존 파일 보존, 새 파일을 `incoming/`에 제안 |
| `blocked` | 심볼릭 링크 또는 일반 파일이 아닌 경로 | 경로를 따라 쓰지 않고 새 파일만 제안 |

check는 파일을 쓰지 않는다. apply는 프로젝트 밖의 상태 디렉터리에 잠금·백업·제안을 만들고 파일 단위로 갱신한다.
두 명령 모두 정상 처리는 0, 충돌/차단이 있으면 1, 잘못된 요청이나 실행 오류는 2로 종료한다.
충돌이 있어도 다른 안전한 파일은 갱신될 수 있으므로 출력과 `report.json`을 확인한다.
Git stage·commit·브랜치를 변경하거나 파일을 자동 삭제하지 않는다. Git 미커밋 변경은 그대로 남는다.
다른 편집기가 동시에 같은 파일을 고치는 것을 막는 기능은 아니므로 수정 중인 프로젝트에서 apply하지 않는다.

프로젝트를 처음 초기화한 시점의 별도 manifest는 필요하지 않다. 현재 파일의 내용이 키트의 실제 Git 이력에 있는지 비교한다.
이력이 없는 소스 배포·얕은 clone·다른 방식으로 만든 규칙은 확인하지 못할 수 있다. 그런 파일은 강제로 덮어쓰지 않는다.

## 충돌 검토와 복원

기본 상태 위치는 `${XDG_STATE_HOME:-~/.local/state}/local-worker/project-updates`다.
`LLM_PROJECT_UPDATE_HOME` 또는 `--state-dir`로 바꿀 수 있으며 프로젝트 내부 위치는 거절한다.
apply가 출력한 개별 백업 폴더는 다음과 같다.

```text
<UTC시각>-<고유 ID>/
  before/<상대 경로>     실제 교체한 파일의 원본과 권한
  incoming/<상대 경로>   충돌/차단된 파일의 새 템플릿
  report.json            대상 프로젝트와 파일별 처리 결과
```

`incoming/`의 파일을 기존 파일과 비교해 필요한 규칙만 합친다. 프로젝트별 역할·보호 경로·권한·기타 훅은 보존한다.
직접 병합한 파일은 사용자 수정 파일이므로 다음 버전에서도 충돌 제안 대상으로 남을 수 있다.
자동 갱신한 내용을 되돌리려면 `before/`에서 해당 파일만 원래 위치로 복사한다. 업데이트 이후 추가 수정이 있다면 먼저 비교한다.
새로 추가된 파일은 before 사본이 없으므로 report를 보고 처리 여부를 직접 결정한다.

## 새 실행과 기존 대화에 적용

메인 대화는 같은 프로젝트에서 `claude-main --resume`으로 이어가도 된다. 워커 실행기는 별도 프로세스이므로
갱신한 worker-task/llm-worker가 새 관리 태스크를 시작할 때 새 권한 설정을 사용한다.
이미 실행 중인 프로세스에는 변경이 소급 적용되지 않는다. 진행 중인 태스크는 종료/취소 여부를 확인하고 새로 실행한다.

프로젝트 규칙을 --check/--apply로 갱신한 뒤, 재개한 대화에 다음을 한 번 전달한다.

> AGENTS.md와 agents/ORCHESTRATOR.md를 다시 읽고 현재 설치된 worker-task로 워커를 실행해 줘.
> 기존 대화의 옛 운영 지침 대신 갱신한 규칙을 적용하고, 필요한 외부 데이터는 read_paths에 넣어 줘.
> permission_denied가 발생하면 원인을 보고하고, 조용히 메인 직접 구현으로 대체하지 마.

`claude-main`은 기본 모델 Opus와 `--system-prompt-snapshot off`를 지정한다. CLI 2.1.257 이상이 필요하다.
기존 메인을 종료하고 `claude-main --resume`으로 재개하면 최신 런처 지침을 다시 적용하며,
기본 selective는 EGM·고난도 판단용 Agent/Task/Skill을 허용한다. `claude-main --resume` 또는 duo로 재개하면 적용된다.
차단을 유지하려면 `--native-agents off`를 지정한다. Workflow/TeamCreate는 계속 제한한다.
Codex도 `codex-duo -- resume --last`로 재개한다. 일반 구현·테스트는 관리 워커에 남긴다.
[선택적 네이티브 위임](NATIVE_AGENTS.md)의 결과·권한 차이를 확인한다.
추가 컨텍스트는 `--append-system-prompt`로 전달할 수 있고 필수 위임 지침과 합쳐진다.
이 옵션으로 데모 지침을 넣어도 기본 정책이 사라지지 않는다. 다른 claude 런처에는 적용되지 않는다.
프로젝트별 문서 재독은 여전히 필요하다. [공식 resume 옵션](https://code.claude.com/docs/en/cli-reference#system-prompt-flags-in-resumed-conversations).
대화형 워커의 업데이트된 역할 프롬프트가 필요하면 새 워커 세션을 시작한다.

새 workspace 권한은 SSH·scp·sftp·rsync를 명시적으로 허용한다. 런처와 생성 프롬프트의
로컬 전용 금지도 제거한다. 적용은 새 시도부터이며 사용자/프로젝트/조직의 deny·ask는 보존한다.
예전 permissions_file에 SSH deny가 복사된 태스크는 원본 파일을 고쳐도 바뀌지 않는다.
허용 규칙을 검토·수정한 뒤 새 태스크를 등록한다. Qwen의 잡 재실행 금지와 원본/보호 파일 검증은 유지한다.

기존 태스크의 기준 커밋과 명세는 바뀌지 않는다. 실패/중단한 태스크는 --retry로 새 시도를 만들 수 있지만
이전 시도의 미커밋 코드를 이어받는 기능은 아니다. 새 read_paths·권한 규칙·입력이 필요하면 새로 등록한다.
기존 성공 검증을 유지한 채 worktree를 수정하지 않는다. 랩미팅 데모는 갱신 후 demo/prepare.py로 새로 준비한다.

## 2026-11 LiteLLM / Qwen 구성

--update는 기존 env를 바꾸지 않고 위의 공통 게이트웨이를 생성한다. 모델·컨텍스트까지 새 기본값으로 옮기려면
`./install.sh --migrate-backend --non-interactive`를 명시적으로 실행한다. 대상 env를 백업하고
키/인증 모드와 사용자 값을 유지하며 URL·DeepSeek 모델·컨텍스트를 갱신한다.
기본 프로필의 명시적 마이그레이션은 `gateway.env`도 백업 후 갱신한다.
`--profile impl`처럼 프로필을 지정하면 그 env만 갱신하고 공통 연결은 바꾸지 않는다. qwen 프로필은 Qwen 모델을 사용한다.

새 Qwen 프로필은 `./install.sh --profile qwen --non-interactive`, 기존 프로필의 모델·컨텍스트 갱신은
`./install.sh --migrate-backend --profile qwen --non-interactive`다.
새 프록시의 기본 인증 모드는 none이며 Claude CLI에 전달하는 litellm-no-auth는 비밀 키가 아닌
클라이언트용 식별자다. 기존 키 인증 설정은 자동으로 해제하지 않는다.
프로젝트 규칙도 project-update로 비교·적용하고 재개한 메인에 새 역할 규칙을 다시 읽게 한다.

연결을 직접 관리한다면 `gateway.env`의 LLM_BASE_URL·LLM_AUTH_MODE·LLM_API_KEY만 수정하고 권한 `0600`을 유지한다.
변경은 다음 워커 실행부터 적용된다. 공통 연결을 삭제해도 프로필 주소로 돌아가지 않고 실행을 거절한다.
Opus 메인은 Claude 계정으로 접속하며 이 파일을 사용하지 않는다.

## effort 전달 제거

```bash
git pull --ff-only
./install.sh --update
```

새 워커는 --effort와 CLAUDE_CODE_EFFORT_LEVEL을 전달하지 않는다. env/env.<프로필>의
기존 LLM_EFFORT는 삭제하지 않고 실행 시 무시하므로 설정을 다시 만들 필요가 없다.
등록된 원본 태스크 명세도 바꾸지 않는다. 이전 effort 요청은 requested_effort에 보존하고,
새 실행 결과는 effort=null, effort_forwarded=false로 기록한다. 이미 실행 중인 워커에는 소급 적용되지 않는다.

CLI가 자체 기본 effort를 HTTP 요청에 넣는 동작은 별개다. 현재 확인한 CLI 2.1.314는
옵션·환경변수가 없어도 high를 전송했다. 이 업데이트가 HTTP effort 필드를 제거하는 것은 아니다.
