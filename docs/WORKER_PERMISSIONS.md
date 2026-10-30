# 관리 워커 권한

대화형 `claude-glm`·`deepseek-worker`는 사용자에게 도구 승인을 요청할 수 있다.
`deepseek-task run`은 별도 `claude -p` 프로세스이므로 필요한 규칙을 실행 전에 전달한다.
이전 버전은 crossSessionInbound만 설정했고, 비대화 워커에 사용할 도구 허용 규칙을 준비하지 않았다.

## 프로필

| permission_profile | 동작 |
|---|---|
| workspace (기본) | worktree 파일 도구, Bash, 웹 검색/조회, 일반 에이전트 도구 허용 |
| custom | permissions_file의 allow 규칙과 명시한 외부 경로만 추가 |
| inherit | 추가 권한 없이 기존 Claude 설정 사용; 이전 동작 |

workspace/custom은 문서화된 `permissions.allow/ask/deny`와 `defaultMode: dontAsk`를 사용한다.
`--tools default`로 설치된 기본 도구를 노출하고, 실행기에서 생성한 설정 파일 하나를 `--settings`로 전달한다.
허용되지 않은 호출을 프롬프트로 대기하지 않고 거절한다. 사용자/프로젝트/조직의 deny와 ask를 제거하거나,
setting-sources를 끄거나, bypassPermissions/권한 우회 옵션을 사용하지 않는다.
별도 MCP·조직 connector의 권한과 백엔드가 지원하지 않는 기능까지 자동으로 활성화하는 설정은 아니다.

## GRE 같은 작업의 명세

아래 필드를 목적·저장소·기준 커밋·검증 명령 등이 있는 명세에 추가한다.

```json
{
  "permission_profile": "workspace",
  "read_paths": ["/mnt/d/Gateact"],
  "scratch_paths": ["/tmp/gre_*"],
  "allowed_paths": ["reports/", "gre/", "candidate-tests/"],
  "protected_paths": ["tests/", "config/"]
}
```

read_paths는 절대 경로나 명세 디렉터리 기준의 실제 상대 경로를 받는다. 외부 드라이브는 등록 뒤 마운트할 수 있지만
실행 시 경로가 없으면 워커를 시작하지 않는다. 파일 도구의 Read를 허용하고 Edit는 거절한다.
scratch_paths는 절대 경로/패턴이며 루트·상위 경로 이동은 거절한다. 지정 경로의 Read/Edit를 허용하고 자동 삭제하지 않는다.
원본 checkout, `.git`, `.claude/`, tests/, config/, .task-inputs/와 명세의 보호 경로는 native Edit에서 제외한다.
git add/commit/checkout 등의 변경 명령과 ssh/rsync도 기본 거절한다. Bash의 모든 간접 동작을 막는 보안 경계는 아니다.

## 기존 제안 파일 사용

```json
{
  "permission_profile": "custom",
  "permissions_file": "/home/lee/gre_orch/proposed/settings.json",
  "read_paths": ["/mnt/d/Gateact"],
  "scratch_paths": ["/tmp/gre_*"]
}
```

permissions_file은 절대 경로나 명세 JSON 디렉터리 기준 경로다. `permissions` 객체 또는 직접 allow/ask/deny 객체를 받는다.
허용·질문·거절 목록만 태스크 명세에 고정하며 hooks, env, 모델, 인증, defaultMode 등은 복사하지 않는다.
파일이 나중에 바뀌어도 등록한 태스크의 권한은 바뀌지 않는다. 새 규칙으로 바꾸려면 새 태스크를 등록한다.
workspace와 함께 사용하면 기본 허용에 추가된다. custom은 workspace의 넓은 허용 목록을 추가하지 않는다.
기존 사용자·프로젝트 allow도 CLI에서 병합되므로 custom을 전역 권한 축소용 샌드박스로 취급하지 않는다. 제한이 필요하면 명시적 deny를 검토한다.

`Read(/path)`의 단일 /는 설정 기준 상대 경로이며 절대 경로는 `Read(//path)`다.
실행기의 설정 파일은 worktree 밖에 있으므로 `/reports/**` 같은 상대 경로는 배정 worktree로 고정한다.
`Write(path)`·`NotebookEdit(path)`·`Glob(path)`는 해당 경로 권한 검사에 매칭되지 않아 각각 Edit/Read 규칙으로 정규화한다.
[공식 권한 문서](https://code.claude.com/docs/en/permissions)의 경로 문법과 우선순위를 따른다.

## 결과 확인

`worker_settings_path`, `worker_settings_digest`, `permission_profile`, `permission_denial_count`,
`permission_denied_tools`를 상태/결과에 남긴다. 도구 입력은 상태에 복사하지 않는다.
CLI의 permission_denials가 있으면 정상 종료나 자연어 보고와 무관하게 permission_denied로 실패한다.
설정 파일은 worker와 검증 종료 뒤 해시를 대조하며, 바뀌면 기존 검증을 인정하지 않는다.

Bash·Python은 현재 사용자 권한으로 실행된다. native Read/Edit 규칙은 Python 코드 내부의 파일 접근을 막지 않는다.
허용 범위 밖 worktree 변경은 외부 검증에서 실패하지만, 외부 파일 접근의 강제 격리가 필요하면 별도 OS 샌드박스가 필요하다.

## 기존 설치에 적용

```bash
git pull --ff-only
./install.sh --update
```

기존 API 키와 모델 설정은 유지된다. 기존 명세에 권한 필드가 없으면 새 실행은 workspace를 기본으로 사용한다.
실패 시도는 보존하고 명시적으로 --retry한다. 외부 데이터 경로/규칙이 필요한 태스크는 그 필드를 넣어 새로 등록한다.
메인 checkout에 권한 파일을 임의로 commit하거나 사용자 변경을 stash할 필요는 없다.

## 기존 GLM 세트와 비교

이 컴퓨터의 claude-main/claude-glm을 읽기 전용으로 비교했다. 기존 파일과 설정은 수정하지 않았다.
claude-glm은 crossSessionInbound를 켜고 대화형 Claude Code를 시작하며 별도 우회 플래그를 넣지 않는다.
대화형 승인을 받을 수 있는 실행과 새 -p 관리 프로세스의 권한 동작을 같다고 가정하지 않는다.
관리 모드는 별도의 고정 권한 파일과 기본 도구 목록을 전달한다.
GLM 래퍼에서 쓰던 CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1도 반영해 일반 서브에이전트가 설정된 DeepSeek 모델을 사용하게 했다.
메인 래퍼에서는 해당 워커용 변수를 제거한다.

검증은 모의 CLI 회귀 검사와 실제 DeepSeek 호출을 구분한다. 실제 호출에서는 임시 Git 저장소·외부 입력 fixture를 사용했으며,
/mnt/d의 연구 데이터에는 접근하지 않았다. Read/Write/Bash 실행, 보고서·코드·후보 테스트 생성과 독립 Python 검증을 확인한다.
원시 API 키나 thinking 원문을 저장소에 남기지 않는다. 실행 결과 요약은 validation/managed-permissions.json에 기록한다.
