# 관리 워커 권한

대화형 `claude-glm`·`deepseek-worker`는 사용자에게 도구 승인을 요청할 수 있다.
`deepseek-task run`은 별도 `claude -p` 프로세스이므로 필요한 규칙을 실행 전에 전달한다.
이전 버전은 crossSessionInbound만 설정했고, 비대화 워커에 사용할 도구 허용 규칙을 준비하지 않았다.

`deepseek-main`은 별도 제한을 사용한다. 메인의 Agent·Task·Workflow·TeamCreate·Skill을 제외하고
Bash의 관리 CLI로 위임한다. 아래 일반 도구 허용은 워커에 적용하며, 메인의 차단 환경변수는 워커에 전달하지 않는다.

## 프로필

| permission_profile | 동작 |
|---|---|
| workspace (기본) | worktree 파일 도구, 일반 Bash·환경 구성, SSH/scp/sftp/rsync, 웹·에이전트 도구 허용 |
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
git add/commit/checkout 등의 변경 명령은 계속 거절한다. Bash의 모든 간접 동작을 막는 보안 경계는 아니다.

## 연구실 SSH·원격 작업

기본 workspace는 일반 Bash 외에 `Bash(ssh *)`, `Bash(scp *)`, `Bash(sftp *)`,
`Bash(rsync *)`를 명시적으로 허용한다. Python·Node·패키지/환경 도구·파일 복사도 일반 Bash 권한을 사용한다.
연구실에서 신뢰하는 워커를 전제로 하며 추가 권한 JSON 없이 원격 조사·설정·실행·전송을 맡길 수 있다.
태스크 지시문에는 실제 SSH 별칭/user@host, 원격 경로, 작업 범위와 예산을 넣는다.
추론 게이트웨이 주소를 SSH 호스트로 추정하지 않는다. 키트는 내부망 주소 여부를 판별하지 않는다.

기존 SSH config·키·agent·known_hosts를 사용한다. 키트가 호스트 키 확인을 끄거나 인증 정보를
명세/로그에 복사하지 않는다. 일반 직접 SSH는 worktree 외부의 원격 파일을 최종 diff로 검사하지 못한다.
원격 revision·명령·실제 종료 코드·산출물 근거를 로컬 보고서에 남기고 검증 명령으로 확인한다.
직접 시작한 원격 프로세스는 관리 태스크 취소만으로 종료를 보장하지 않는다. 대기/GPU 배정·원격 취소·
고정 실행 기록이 필요한 잡은 기존 compute_job 실행기를 사용한다.

custom은 permissions_file의 SSH/전송 허용 규칙을 사용할 수 있고 키트의 강제 SSH deny가 덮어쓰지 않는다.
기존 파일이나 사용자/프로젝트/조직 설정의 deny·ask는 여전히 우선한다. 예전 제안의 `Bash(ssh:*)`나
`Bash(rsync:*)` deny가 남아 있다면 그 파일의 소유자가 수정하고 새 태스크를 등록한다.
등록 시 복사한 규칙과 진행 중인 워커 권한은 자동 변경하지 않는다.

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

## Qwen Compute Job

메인이 등록 시 고정한 compute_job은 별도 실행기가 local/SSH로 수행한다. SSH는 BatchMode와 기존 known_hosts를 사용한다.
Qwen은 실행 뒤 읽기 경로로 제공된 compute.result.json과 작업 출력으로 운영 보고서를 작성한다.
로컬 잡의 해당 run 로그 파일만 읽기 허용하며 다른 잡의 폴더나 원격 로그 경로는 추가하지 않는다.
Qwen은 해당 잡의 명시된 호스트에서 로그를 조회하거나 허용 출력 경로로 회수할 수 있다.
잡 재실행·명령 변경·다른 호스트로 확대하는 일은 맡기지 않는다. 일반 DeepSeek 워커는 위의 SSH 권한으로
별도 원격 작업을 수행할 수 있다. 자세한 잡 수명 관리는 COMPUTE_JOBS.md를 참고한다.

## SSH 권한 회귀 검사 (2026-11-07)

기본 workspace와 custom SSH 허용을 실제 Claude CLI 2.1.314로 확인했다. 호스트 홈을 숨긴
bubblewrap 환경에서 모의 API가 파일 작성과 scp → SSH 명령 → rsync/sftp 회수를 요청했다.
두 태스크 모두 권한 거절 없이 외부 테스트를 통과했고 원본 checkout은 유지됐다.
별도 태스크의 기존 SSH deny는 실제 CLI에서 거절됐으며 명령이 실행되지 않았다.

모델과 SSH/전송 도구는 모의 실행이다. 실제 원격 로그인·GPU·모델 추론을 검증한 결과는 아니다.
테스트 환경의 네트워크는 공유됐지만 요청은 로컬 모의 API로만 보냈다.
오프라인 테스트와 세 사례의 결과는 [검증 기록](validation/ssh-permissions.json)에 남긴다.
