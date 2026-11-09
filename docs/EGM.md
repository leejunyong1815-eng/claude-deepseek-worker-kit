# Elephant Goldfish Model과 함께 쓰기

2026-11-08에 upstream `main`의 EGM 0.1.1 명세·스킬·리뷰어 어댑터를 대조했고, 2026-11-09에 선택적 네이티브 위임을 추가했다.
EGM은 프로젝트 맥락을 아는 작성자와 이전 대화를 받지 않는 리뷰어를 나누는 설계 워크플로다.
모델 가중치, vLLM 서버, LiteLLM provider가 아니며 별도 GPU 설치는 없다.
설치는 [README](../README.md#egm-설치와-설계-리뷰)의 CLI별 명령을 따른다.

## 현재 호환 범위

| 실행 경로 | 판정 | 근거와 제한 |
|---|---|---|
| 일반 `claude` + EGM | upstream이 지원하는 별도 설계 경로 | 새 Agent가 필요하다. Claude 2.1.271+의 `omitClaudeMd`를 사용한다. 이 키트에서 실제 리뷰 실행은 검증하지 않았다. |
| 일반 `codex` + EGM | upstream이 지원하는 별도 설계 경로 | 로컬 실행기와 네이티브 multi-agent가 필요하다. 부모 대화 제외와 AGENTS.md 등 지침 파일 제외는 다른 보장이다. |
| `claude-main`, `claude-duo` | 기본 `selective`에서 네이티브 호출 허용 | [런처](../bin/claude-main)는 EGM·고난도 판단에 Agent/Task/Skill을 허용한다. `--native-agents off`는 이를 차단한다. EGM 전체 리뷰 실행은 미검증이다. |
| `codex-main`, `codex-duo` | `selective`에서 네이티브 호출 허용 | [런처](../bin/codex-main)는 모드에 따라 `agents.enabled`와 기존 `features.multi_agent`를 설정한다. EGM의 새 맥락 리뷰 조건은 그대로 따라야 한다. EGM 전체 리뷰 실행은 미검증이다. |
| 직접 띄운 수동 `llm-worker` | 별도 연동 검증 필요 | 런처는 자식 모델도 선택한 백엔드로 연결하고 workspace 권한은 Agent를 허용한다. 다만 EGM 자원 접근·스킬 발견·역할 지침과 실제 리뷰 격리는 검증하지 않았다. |
| `worker-task`의 관리 워커 | 설치만으로 자동 연동되지 않음 | 비대화 실행, 고정 입력, 별도 worktree, 경로·시간 검증과 EGM의 승인 단계·여러 리뷰어 호출을 연결하는 어댑터가 없다. |

EGM 스킬은 `disable-model-invocation: true`로 명시적 호출을 전제로 한다. Claude의 Skill 도구도 원래 이 스킬들을 직접 실행하지 않는다.
따라서 Skill 차단만 풀거나 프롬프트에 EGM을 쓰라고 적는 것으로 리뷰가 연결되지 않는다.
Claude에서는 사용자가 `/egm:egm-review ...`처럼 시작하고, 이어지는 EGM 스킬은 upstream 안내에 따라 본문을 읽어 수행한다.
명시적 off의 네이티브 Agent 차단은 결정적인 충돌이며 기본 selective에서는 호출을 허용한다.
기존 사용자·조직의 deny가 있으면 여전히 사용할 수 없다. [EGM Claude 안내](https://github.com/google/elephant-goldfish-model/blob/main/docs/claude.md)

## 설치 확인과 별도 설계 세션

CLI가 설치된 같은 WSL 사용자 환경에서 설치한다. Windows 측 플러그인 설치가 WSL에 자동으로 전달되지는 않는다.
사용할 CLI의 명령이 있는지 먼저 확인한다.

```bash
claude --version
claude plugin install --help
# Codex를 쓰는 경우
codex --version
codex plugin add --help
```

EGM을 설치한 뒤 `claude plugin list` 또는 `codex plugin list --json`에서 설치·활성 상태를 확인하고 새 세션을 연다.
`skills/`만 복사하지 않는다. 리뷰어의 `agents/`, 기준 문서의 `resources/`, 호스트별 `docs/`와 플러그인 명세가 함께 필요하다.
새 세션에서도 EGM이 보이지 않으면 해당 CLI의 플러그인 목록·오류와 설치 범위를 확인한다.
Codex의 설치 명령은 [OpenAI 공식 CLI 문서](https://learn.chatgpt.com/docs/developer-commands#codex-plugin)와도 대조했다.

프로젝트에서 키트를 사용할 때는 지침을 갱신하고 `claude-duo` 또는 `codex-duo`로 시작한다.
기본 selective에서 일반 구현 위임은 관리 풀에 남고 EGM·고난도 판단은 네이티브로 실행할 수 있다.
별도 설계 세션을 원하면 README처럼 `~/egm-design` 디렉터리에서 일반 CLI를 실행하고 소스 저장소를 읽기 자료로 지정한다.
필요한 외부 파일의 Read는 정상 권한 절차로 허용한다. `--add-dir`는 편집 범위도 넓히므로 읽기 전용 허용의 대체로 쓰지 않는다.

Claude의 첫 입력 예시다. 저장소 경로와 기능 설명을 실제 값으로 바꾼다.

```text
/egm:egm-brainstorm 작업 큐에 태스크 우선순위를 추가하는 기능을 설계해 줘.
EGM artifact directory: docs/egm
이번 세션은 설계와 문서 리뷰만 수행한다.
소스 저장소는 /absolute/path/to/project 이며 읽기 전용으로 참고한다.
소스 코드·Git 상태는 변경하지 말고, 산출물은 현재 디렉터리의 docs/egm에 저장해 줘.
검토에 쓴 소스 커밋과 참고 파일 목록을 산출물에 남겨 줘.
```

그다음 같은 세션에서 브리프 경로를 지정해 `/egm:egm-draft docs/egm/concepts_brief.md`를 실행한다.
작성한 문서는 `/egm:egm-review docs/egm/design_draft.md`로 검토한다. 실제 반환된 파일 경로를 우선한다.
Codex에서는 동일한 목적과 경로를 주고 스킬 선택기에서 대응하는 EGM 스킬을 고른다.
확인 질문·섹션 승인·설계 선택은 EGM 흐름에 따라 처리한다. 설치 명령은 모델을 호출하는 설계 명령과 구분한다.

승인한 문서는 사용자가 선택한 기준 커밋에 포함하거나 검증된 태스크 `inputs`로 전달한 뒤 키트 구현에 사용한다.
원본의 미커밋 문서가 새 worktree로 따라오지는 않는다. 그 문서가 필수 입력이면 `depends_on_uncommitted=true`로 차단하고 입력을 준비한다.
자동 commit·stash·merge는 하지 않는다. EGM 설계 리뷰 통과도 코드 태스크의 `succeeded`나 테스트 통과를 대신하지 않는다.

## 모델·권한·비용에서 달라지는 점

- **모델 선택:** upstream Claude 리뷰어는 `model: inherit`다. 일반/키트 selective 세션의 Goldfish는 네이티브 모델 설정을 사용하며 DeepSeek/Qwen 레지스트리로 자동 전환되지 않는다. Codex의 네이티브 리뷰어도 키트의 워커 배정기를 거치지 않는다.
- **권한:** EGM은 자원 읽기 승인 훅을 설치하지 않는다. 비대화 실행에는 실제 설치 경로의 `agents/`, `docs/`, `resources/`, `skills/` 읽기를 명시해야 한다. `read_paths`는 고정된 실제 경로를 사용하며, 플러그인 버전 경로가 바뀌면 새 명세가 필요할 수 있다. 전체 플러그인 캐시에 쓰기 권한을 줄 필요는 없다.
- **리뷰어 도구:** Claude의 개별 리뷰어 어댑터는 Read/Grep/Glob만 허용하지만, 종합자와 bootstrap은 다른 도구 목록을 가진다. 이 제한이 Codex의 일반 에이전트나 키트의 넓은 Bash 권한에 자동으로 적용되지는 않는다.
- **맥락 격리:** Claude의 `omitClaudeMd`는 지침 파일 제외용이며 관리 정책은 유지한다. Codex의 `fork_turns: none` 계열 설정은 부모 대화 제외를 뜻하며 지침 파일까지 제외했다고 판단하면 안 된다. 어느 쪽도 파일시스템 샌드박스가 아니다.
- **무인 실행:** brainstorm과 draft는 사용자 확인을 포함한다. review의 `uninterrupted`도 모든 스킬의 입력·승인 질문을 없애는 옵션은 아니다. 현재 `worker-task`는 이런 질문을 사용자에게 중계하지 않는다.
- **처리량:** EGM은 단계별로 여러 리뷰어를 호출하고 수정 후 반복할 수 있다. 네이티브 자식 호출은 키트의 task 단위 서버 동시 실행 한도에 개별 집계되지 않는다. 설치만으로 토큰 절감이나 속도 개선이 보장되지 않는다.

프로젝트 규칙·언어·보고서 형식도 함께 확인한다. EGM의 기본 문서 작성 지침은 영어를 전제로 하므로 한국어 산출물이 필요하면 사용자가 명시한다.
원격 URL을 읽지 못하는 리뷰어에는 필요한 페이지를 파일로 준비하고 그 경로를 전달한다.
플러그인 자원이나 기준 문서를 읽지 못한 리뷰어는 미실행·불완전으로 기록하며, 발견 사항 0건으로 처리하지 않는다.
자세한 동작은 [Claude 통합](https://github.com/google/elephant-goldfish-model/blob/main/docs/claude.md),
[Codex 통합](https://github.com/google/elephant-goldfish-model/blob/main/docs/codex.md),
[리뷰 절차](https://github.com/google/elephant-goldfish-model/blob/main/skills/egm-review/SKILL.md)를 따른다.

## 관리 워커에 직접 연결하려면

EGM을 네이티브 모델로 실행하는 데에는 기본 selective 모드를 사용한다. 아래는 리뷰어까지 DeepSeek 등의
관리 태스크로 실행하려는 경우에만 필요한 별도 어댑터이며, 현재 미구현이다. 일반 키트 실행에서
네이티브 차단을 전역으로 해제하지 않고 기존 모델 배정·취소·검증에 연결하는 설계 제안이다.

필요한 작업은 다음과 같다.

1. 리뷰어별로 새 task/attempt를 만들고, 읽을 persona·standard·대상 문서의 버전과 해시를 고정한다. 부모 대화·작성자의 결론은 전달하지 않는다.
2. 문서·코드를 같은 기준 커밋 또는 검증된 입력으로 제공하고, 결과는 해당 worktree의 허용 보고서 경로에만 쓴다. EGM의 기본 작업 디렉터리 출력을 그대로 원본 저장소에 쓰게 하지 않는다.
3. 한 단계의 리뷰어만 병렬 실행하고 전부 완료한 뒤 다음 단계로 진행한다. 실패·시간 초과·권한 거절은 미실행으로 기록하며, 모델의 보고 대신 실제 결과 파일과 고정 입력·검증 결과를 확인한다.
4. 승인 단계는 메인 세션이 담당하고, DeepSeek 모델·동시 실행 수·턴·시간 예산은 기존 레지스트리와 명세로 지정한다. 개별 리뷰어의 읽기 전용 도구 제한과 숨은 지침 제외 여부는 실제 CLI로 별도 검증한다.

## 이번 확인 범위

현재 CLI는 Claude Code 2.1.319, Codex CLI 0.165.0이다. CLI의 설치·marketplace 명령과 옵션은 로컬 `--help`로 확인했다.
upstream 플러그인 명세, 리뷰어 도구·모델 설정, 스킬의 위임 요구사항과 현재 런처의 차단 설정을 읽어 대조했다.
선택 모드의 도구·환경·프롬프트 전달과 기존 관리 태스크 실행은 오프라인 회귀 검사로 확인한다.
호스트에 EGM을 설치하거나 계정·권한·백엔드 설정을 바꾸지는 않았다. 실제 설계 리뷰·모델 호출·토큰/속도 측정도 하지 않았다.
따라서 설치 명령 확인을 실제 EGM 통합 성공으로 취급하지 않는다.
