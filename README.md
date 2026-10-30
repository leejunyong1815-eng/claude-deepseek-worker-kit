# Claude + DeepSeek Worker Kit

Claude Code에서 DeepSeek를 서브에이전트로 쓰기 위한 CLI 도구입니다.
Claude가 작업을 나누고 결과를 검토하며, DeepSeek가 조사, 설계, 구현, 테스트 작성, 실험, 리뷰를 맡습니다.
모델 추론은 연구실 서버에서, 코드 편집과 실험은 로컬 컴퓨터나 WSL에서 실행합니다.

[claude-local-worker-kit](https://github.com/leejunyong1815-eng/claude-local-worker-kit)에서 분리한 버전입니다.
명령어와 설정 경로가 달라 기존 버전과 함께 설치할 수 있습니다.

## 새 WSL에 설치

WSL2의 Ubuntu 22.04/24.04 기준입니다. 아래 명령은 새 컴퓨터의 Ubuntu 터미널에서 실행합니다.
키트와 프로젝트는 `~/src` 같은 Linux 파일시스템 경로에 두세요.

### 1. 필수 도구와 Claude Code

```bash
sudo apt update
sudo apt install -y git python3 curl ca-certificates gh

curl -fsSL https://claude.ai/install.sh | bash
export PATH="$HOME/.local/bin:$PATH"
claude --version
claude auth login
```

Claude Code는 WSL 안에 설치합니다. 설치·로그인 방법은 [공식 문서](https://code.claude.com/docs/en/setup)를 참고하세요.
이 키트는 Python 3.9 이상과 `--effort`, `--name`을 지원하는 Claude Code 2.1.224 이상을 사용합니다.
`tmux`는 `deepseek-duo`를 사용할 때만 필요합니다 (`sudo apt install tmux`).

### 2. 저장소 받기

비공개 저장소이므로 접근 권한이 있는 GitHub 계정으로 로그인합니다.

```bash
gh auth login --hostname github.com --git-protocol https --web
mkdir -p ~/src
cd ~/src
gh repo clone leejunyong1815-eng/claude-deepseek-worker-kit
cd claude-deepseek-worker-kit
```

GitHub CLI의 인증·clone 옵션은 [공식 매뉴얼](https://cli.github.com/manual/gh_auth_login)을 참고하세요. 이미 Git 인증을 설정했다면 일반 `git clone`도 사용할 수 있습니다.
기존 컴퓨터의 설정 파일이나 절대 경로를 복사할 필요는 없습니다.

### 3. 환경 확인과 키트 설치

```bash
./install.sh --check
./install.sh --setup-path
. "$HOME/.config/deepseek-worker/shell.sh"
deepseek-doctor
```

`--check`는 Linux 환경, 필수 명령, Claude 버전·옵션을 확인합니다. 파일을 설치하거나 API를 호출하지 않습니다.
`--setup-path`는 키트와 Linux용 Claude의 `~/.local/bin` 경로를 등록하는 설정을 `~/.bashrc`에 한 번 추가합니다. 현재 터미널에는 위의 `shell.sh`를 읽어 적용합니다.
새 터미널부터는 자동으로 적용됩니다. 다른 셸을 쓰는 경우 설치기가 출력한 source 줄을 해당 셸 설정에 추가하세요.

URL, 모델, 컨텍스트는 Enter로 기본값을 사용합니다. API 키는 이 컴퓨터에서 새로 입력합니다.
키는 숨김 입력으로 받아 `~/.config/deepseek-worker/env`에 권한 `0600`으로 저장하며 Git에는 저장하지 않습니다.
메인 Claude 계정 로그인과 DeepSeek API 키는 별도입니다.

| 설정 | 기본값 |
|---|---|
| `LLM_BASE_URL` | `http://133.186.146.224:8081` |
| `LLM_MODEL` | `DeepSeek-V4.1-Flash` |
| `LLM_CONTEXT_WINDOW` | `1048576` (1M) |

기본값은 [config/backend.defaults.json](config/backend.defaults.json)에 있습니다.
컨텍스트 한도와 API 호환성·속도 측정 결과는 [서버 확인 기록](docs/LAB_SERVER.md)을 참고하세요.

서버 연결은 새 컴퓨터에서 별도로 확인합니다. 이 검사는 실제 모델 요청을 보냅니다.

```bash
deepseek-probe
```

`deepseek-doctor`가 통과해도 로그인, 서버 네트워크 접근, 프로젝트 권한은 별도 확인이 필요합니다.
연결 오류는 [문제 해결 문서](docs/TROUBLESHOOTING.md)를 참고하세요.

도구만 먼저 설치하려면 `./install.sh --install-only --setup-path`를 사용합니다.
자동 설치는 `LLM_API_KEY`를 환경변수로 전달하고 `./install.sh --non-interactive`를 실행합니다.
새 설정을 만들 때 URL, 모델, 컨텍스트도 같은 이름의 환경변수로 지정할 수 있습니다. 기존 설정 파일은 유지됩니다.
다른 서버를 쓰려면 Anthropic Messages API, SSE, 도구 호출을 지원해야 하며 `LLM_BASE_URL` 끝에는 `/v1`을 붙이지 않습니다.

clone 디렉터리는 프로젝트 템플릿과 업데이트에 사용합니다. 이동했다면 새 위치에서 `./install.sh --update`를 실행하세요.

## 사용법

작업할 Git 저장소에서 프로젝트 규칙을 설치하고 메인 세션을 시작합니다.

```bash
cd /path/to/project
deepseek-project-init .
deepseek-main
```

`deepseek-project-init`은 기존 파일을 덮어쓰지 않습니다. 첫 세션에서 생성된 `KICKOFF_PROMPT.md`를 붙여 넣은 뒤 작업을 요청합니다.

> CSV 입력 검증 기능을 구현해 줘. 잘못된 입력을 처리하고 테스트도 추가해 줘.

프로젝트 규칙에 따라 메인이 필요한 DeepSeek 태스크를 등록하고 실행합니다.
사용자가 워커 이름이나 task ID를 지정할 필요는 없습니다.
조사부터 모듈 전체 구현, 테스트 초안, 독립 리뷰까지 맡길 수 있으며 완료 조건과 최종 반영은 메인이 검토합니다.
테스트 초안은 `candidate-tests/`에 받고, 검토 후 프로젝트 테스트에 반영합니다.

| 역할 | 작업 |
|---|---|
| `researcher` | 코드·문서·API 조사 |
| `planner` | 설계와 구현 계획 작성 |
| `implementer` | 구현, 리팩터링, 버그 수정 |
| `test-author` | 테스트 초안 작성 |
| `runner` | 로컬 테스트·실험 실행 |
| `analyst` | 결과 집계와 분석 |
| `reviewer` | 별도 태스크에서 코드 리뷰 |

역할은 태스크 명세의 `role`로 선택합니다. 기본 프로필 하나로 모든 역할을 사용할 수 있습니다.
연결 설정을 나눠야 한다면 `./install.sh --profile review --non-interactive`처럼 프로필을 추가합니다.

## 태스크 실행과 검증

각 태스크는 별도 Git worktree에서 실행됩니다. 독립 태스크는 여러 워커로 동시에 돌릴 수 있으며,
대화형 워커를 미리 띄울 필요는 없습니다. 동시 실행 수는 메인이 정하고 전역 스케줄러는 제공하지 않습니다.

선행 태스크의 결과가 필요하면 `inputs`에 task ID와 파일 경로를 지정합니다.
검증된 시도와 파일 해시를 고정하고, 다음 worktree의 `.task-inputs/<task-id>/`에 복사합니다.
등록, 실행, 상태 조회, 결과 확인, 취소 명령은 [관리 모드 문서](docs/MANAGED_TASKS.md)에 정리했습니다.

워커가 정상 종료하면 실행기가 다음을 확인합니다.

- 미추적·ignored 파일을 포함한 변경 파일과 허용·보호 경로
- 지정한 검증 명령의 종료 코드와 시간 초과 여부
- 검증 전후 파일 해시

`status`와 `result` 조회 시 파일 해시를 다시 확인합니다. 검증한 코드가 바뀌면 기존 성공 결과는 무효가 됩니다.
리뷰 태스크도 같은 검사를 거치지만, 리뷰 내용의 타당성은 메인이 판단합니다.

기본 실행 제한은 120턴·1800초, 검증은 명령별 300초입니다. 시간 제한은 태스크 명세에서 바꿀 수 있습니다.
기본 effort는 `max`로 요청합니다. 현재 서버는 Anthropic 요청을 받지만 실제 effort 적용은 확인되지 않았고,
OpenAI 경로의 `reasoning_effort=low/high/max`는 거절됐습니다. 자세한 내용은 [측정 기록](docs/LAB_SERVER.md)에 있습니다.

원본의 미커밋 변경은 worktree에 포함되지 않습니다. 필요한 입력이 기준 커밋에 있는지 먼저 확인해야 합니다.
실패·취소·중단된 worktree와 로그는 보존하며, 자동 stash·commit·merge·push·삭제는 하지 않습니다.
worktree는 파일 충돌을 줄이기 위한 것으로, 같은 사용자 권한의 파일 접근이나 공유 Git refs를 차단하는 보안 샌드박스는 아닙니다.

수동 대화형 메시징은 `deepseek-worker`와 `deepseek-duo -w 2`로 사용할 수 있습니다.
이 모드의 작업 공간과 검증은 직접 관리해야 합니다. 사용법은 [대화형 모드 문서](docs/INTERACTIVE.md)를 참고하세요.

## 업데이트

키트 저장소에서 실행합니다.

```bash
git pull --ff-only
./install.sh --update
```

기존 API 키, 모델, 컨텍스트 설정을 유지하고 실행 파일과 프롬프트를 갱신합니다.
프로젝트에 복사한 규칙은 별도로 확인한 뒤 반영합니다.

```bash
deepseek-project-update --check /path/to/project
deepseek-project-update --apply /path/to/project
```

사용자가 수정한 파일은 유지하고 새 템플릿은 백업 폴더의 `incoming/`에 남깁니다.
백업과 충돌 처리 방법은 [업데이트 문서](docs/UPDATING.md), 기존 키트와의 차이는 [마이그레이션 문서](docs/MIGRATION.md)에 있습니다.

## 테스트와 데모

```bash
./tests/selftest.sh              # 모의 CLI와 임시 Git 저장소로 검사
python3 -B demo/rehearse.py       # 서버 없이 랩미팅 데모 실행
```

두 명령 모두 실제 모델을 호출하지 않습니다. 실제 연동은 `deepseek-probe`와 작은 관리 태스크로 확인합니다.
랩미팅 실행 절차와 입력할 프롬프트는 [demo/README.md](demo/README.md)에 있습니다.

원격 GPU 실행, 모델 자동 선택·fallback, 웹 UI, 자동 PR 생성은 지원하지 않습니다.
남은 작업은 [PLAN.md](PLAN.md), 원본 코드 출처는 [UPSTREAM.md](UPSTREAM.md)를 참고하세요.
