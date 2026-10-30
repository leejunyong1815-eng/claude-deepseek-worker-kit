# Claude + DeepSeek Worker Kit

Claude가 목표와 수용 기준을 관리하고, **연구실 DeepSeek Flash 4.1 서버에 대부분의 서브에이전트 작업을 위임**하는 CLI 키트다.
조사·설계 초안·모듈 구현·테스트 초안·로컬 실험·분석·독립 리뷰를 같은 DeepSeek 백엔드의 별도 태스크로 실행한다.
사용자는 워커 이름이나 관리 명령을 매번 입력할 필요 없이, 만들 기능과 완료 조건을 말하면 된다.

기존 [claude-local-worker-kit](https://github.com/leejunyong1815-eng/claude-local-worker-kit)의 실행기·worktree 격리·외부 검증·업데이트 도구를 재사용한 **별도 저장소**다.
기존 Qwen 버전과 함께 설치할 수 있도록 실행 파일, 설정, 태스크 상태 경로를 분리했다.

기본 서버는 `http://133.186.146.224:8081`, 모델은 `DeepSeek-V4.1-Flash`, 컨텍스트는 **1,048,576토큰(1M)**이다.
서버의 모델 목록과 한도 오류로 확인했으며 공식 API나 다른 모델로 자동 fallback하지 않는다.
**API 키는 Git에 포함하지 않는다.** 설치 시 별도로 입력한다.
실제 API 호환성·thinking 토큰 수·속도 측정 근거와 제한은 [서버 확인 기록](docs/LAB_SERVER.md)에 있다.

## 시작하기

Linux 또는 WSL2, Python 3.9+, Git, Bash가 필요하다. 실제 세션에는 Claude Code CLI가 필요하고,
대화형 세션 간 메시징은 2.1.224 이상을 사용한다. `--effort`를 지원하는 CLI를 사용한다.
`deepseek-main`은 기존 Claude 계정/권한 설정을 사용한다. 키트는 로그인이나 권한 우회를 대신하지 않는다.

서버 설정 없이 실행 도구와 템플릿부터 설치할 수 있다. 이 과정에는 모델 호출이 없다.

```bash
./install.sh --install-only
export PATH="$HOME/.local/deepseek-worker/bin:$PATH"
./tests/selftest.sh
```

다음 명령으로 설정한다. URL·모델·컨텍스트 질문은 Enter로 확인된 기본값을 사용한다.
주소를 바꿀 때는 Anthropic Messages 호환 endpoint여야 하며,
끝에 `/v1`을 붙이지 않는다. 예를 들어 gateway의 `/anthropic` 경로는 유지한다.
키는 숨김 입력으로 받고 `~/.config/deepseek-worker/env`에 권한 0600으로 저장한다.

```bash
./install.sh
# URL·모델·컨텍스트: Enter로 기본값 / API 키: 숨김 입력
# API 요청은 하지 않는다. 명시적으로 연동을 검사할 때만:
deepseek-probe
```

설정 없는 `deepseek-worker`는 오류로 종료한다. 서버가 OpenAI Chat Completions만 제공하면 바로 연결할 수 없으므로,
관리자에게 Anthropic Messages·SSE·tool_use/tool_result 호환 endpoint를 요청한다. 이 키트는 별도 프록시를 설치하지 않는다.
자동 설치 시에는 `LLM_API_KEY`를 환경변수로 전달하고
`./install.sh --non-interactive`를 사용한다. URL·모델·컨텍스트는 필요할 때만 같은 이름의 환경변수로 덮어쓴다.
기존 설정/추가 프로필은 저장된 연결을 우선하며 --update는 이를 바꾸지 않는다. API 키를 명령 기록이나 저장소에 직접 적지 않는다.

## 목표 하나로 작업 맡기기

대상 프로젝트에서 한 번 규칙을 설치한 뒤 오케스트레이터를 실행한다. 기존 파일은 덮어쓰지 않는다.

```bash
cd /path/to/project
deepseek-project-init .
deepseek-main
```

첫 세션에는 생성된 `KICKOFF_PROMPT.md`를 붙여 넣고 다음처럼 목표를 말한다.

> 이 프로젝트에 CSV 입력 검증 기능을 구현해 줘. 오류 사례와 테스트도 준비하고,
> 조사·구현·테스트 초안·독립 리뷰는 DeepSeek에 맡겨 줘. 검증 결과와 남은 문제를 보고해 줘.

오케스트레이터가 역할별 계약과 검증 명령을 정하고 관리 CLI를 호출한다.
제품 코드를 미리 대부분 작성한 뒤 빈칸만 맡기지 않는다. 설계 초안과 테스트 초안도 워커에 맡기되,
메인은 수용 기준·보호된 검증의 신뢰성·권한/예산·최종 반영 결정을 유지한다.
실제 task/attempt ID와 메인이 직접 처리한 범위를 보고하게 한다. 프롬프트 정책이며 강제 위임 비율은 없다.

| `role` | DeepSeek에 맡기는 범위 |
|---|---|
| `researcher` | 코드 조사, 문서/API 확인, 근거를 남기는 조사 보고 |
| `planner` | 설계 대안, 인터페이스와 실행 계획 초안 |
| `implementer` | 완결된 모듈 또는 관련 파일 묶음 구현·수정 |
| `test-author` | 별도 `candidate-tests/`에 테스트 초안 작성 |
| `runner` | 현재 컴퓨터/WSL에서 제한된 실험·검증 실행 |
| `analyst` | 결과 재계산·해석·보고서 초안 |
| `reviewer` | 별도 worktree에서 실제 구현 파일의 독립 리뷰 |

태스크마다 `role`을 선택하므로 프로필을 일곱 개 만들 필요는 없다.
필요하면 `./install.sh --profile review --non-interactive`처럼 이름 있는 프로필도 추가할 수 있다.
프로필은 기본 연결을 상속하며 모델 자동 선택·fallback은 없다.

## 여러 워커와 결과 전달

워커는 하나로 제한되지 않는다. 독립 태스크는 각각 다른 ID/worktree에서 동시에 실행할 수 있다.
관리 모드가 워커 프로세스를 새로 띄우므로 대화형 워커를 미리 열 필요도 없다.
동시 실행 수는 서버 처리량과 로컬 자원을 보고 정한다. 이 버전에는 전역 큐/동시성 스케줄러가 없다.

구현 → 리뷰처럼 앞선 결과를 읽어야 할 때는 명세의 `inputs`로 **검증된 시도와 파일 해시**를 고정한다.
다음 워커는 자기 worktree의 `.task-inputs/<producer-task-id>/`에 복사된 파일을 읽는다.
원본 미커밋 변경이나 다른 워커의 worktree를 직접 공유하지 않는다. 자동 병합도 하지 않는다.
등록·실행·상태·결과·취소 및 연결된 태스크 예시는 [관리 모드 문서](docs/MANAGED_TASKS.md)에 있다.

기존 수동 대화형 메시징도 `deepseek-worker`, `deepseek-duo -w 2`로 사용할 수 있다.
이는 가벼운 질문/논의용이다. 자동 격리·상태·외부 검증이 없으므로 코드 작업에는 관리 모드를 사용한다.

## 추론과 완료 판정

기본 `effort: "max"`를 Claude CLI의 `--effort max`와 환경 설정으로 전달한다.
워커 기본 제한은 120턴·1800초, 검증은 명령별 300초이며 명세에서 시간을 바꿀 수 있다.
더 넓은 작업과 충분한 추론을 요청하되 무제한 재시도하지 않는다. 서버/권한 오류는 구현 실패와 구분한다.

`max`는 **요청한 effort**다. 현재 gateway는 Anthropic 요청을 받지만 실제 적용은 확인되지 않았다.
OpenAI 경로의 reasoning_effort=low/high/max는 거절됐다. 서버 기본 reasoning의 실제 토큰 수와 속도는 [측정 기록](docs/LAB_SERVER.md)에 있다.
공식 DeepSeek의 Anthropic 호환 문서는 `output_config.effort`를 지원하고 `thinking.budget_tokens`는 무시한다고 설명한다.
이 설명을 연구실 서버의 보장으로 간주하지 않으며, 고정 thinking 토큰 수나 속도 향상을 주장하지 않는다.
참고: [공식 호환 문서](https://api-docs.deepseek.com/guides/anthropic_api/).

워커 종료 코드 0은 검증 시작 조건이다. 실행기는 미추적·ignored 파일까지 허용/보호 경로를 검사하고,
고정된 검증 명령의 실제 종료 코드와 코드 해시로 성공을 기록한다. 이후 파일이 바뀌면 성공을 무효화한다.
리뷰 보고서의 `succeeded`는 지정된 기계적 검증을 통과했다는 뜻이다. 리뷰 내용의 타당성은 메인이 검토한다.

worktree는 동시 편집 충돌을 줄이는 장치이며 **보안 샌드박스가 아니다**.
같은 사용자 권한의 절대 경로 접근이나 공유 Git refs를 차단하지 않는다. 권한 우회 옵션을 자동 추가하지 않는다.
원본 미커밋 변경은 새 worktree에 포함되지 않으며, 의존성이 있으면 해당 태스크를 차단한다.
실패·취소·중단 시도는 보존한다. 자동 stash·commit·merge·push·삭제는 없다.

## 업데이트·데모·검증

```bash
# 이 별도 저장소에서:
git pull --ff-only
./install.sh --update
# 프로젝트 규칙은 별도 검토 후 반영:
deepseek-project-update --check /path/to/project
deepseek-project-update --apply /path/to/project
```

사용자 수정 규칙은 보존하고 충돌 제안 파일을 만든다. 설정·키·모델·컨텍스트는 유지한다.
업데이트 절차와 두 버전의 차이는 [UPDATING](docs/UPDATING.md), [MIGRATION](docs/MIGRATION.md)을 참고한다.

[랩미팅 데모](demo/README.md)는 기존 연구 흐름을 작은 로컬 CPU 실험으로 보여 준다.
`python3 -B demo/rehearse.py`는 실제 관리 실행기와 모의 Claude로 전체 경로를 점검하며 모델을 호출하지 않는다.
`./tests/selftest.sh` 역시 오프라인 테스트다. 실제 연동 검사는 명시적인 `deepseek-probe`와 작은 관리 태스크로 별도 수행한다.

현재 범위에는 원격 GPU 실행, 모델 자동 선택/fallback, 웹 UI, 자동 merge/push/PR, 대규모 벤치마크가 없다.
실제 CLI 연결과 남은 확인 사항은 [PLAN](PLAN.md), 소스 출처는 [UPSTREAM](UPSTREAM.md)에 기록했다.
