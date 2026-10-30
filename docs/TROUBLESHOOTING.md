# 연결·실행 문제 확인

- 새 WSL 설치: README의 필수 도구·GitHub 인증·clone 절차부터 진행한다. 설치 전 `./install.sh --check`, 설치 후 `deepseek-doctor`로 확인한다.
- 명령을 못 찾음: `./install.sh --setup-path` 후 `. "$HOME/.config/deepseek-worker/shell.sh"`로 현재 터미널에 적용한다.
- Windows의 Claude가 잡힘: WSL 안에서 Linux용 Claude Code를 설치하고 ~/.local/bin을 PATH 앞에 둔다.
- checkout 이동: 새 위치에서 `./install.sh --update`를 실행해 템플릿 경로를 갱신한다.

- 설정 없음: `./install.sh --install-only`는 도구만 설치한다. 서버 정보를 받은 뒤 `./install.sh`로 설정한다.
- 401/403: 키와 서버 권한을 관리자에게 확인한다. 키를 채팅·로그·GitHub issue에 붙이지 않는다.
- 모델/컨텍스트 오류: 실제 등록 ID와 요청당 한도를 사용한다. 공식 API의 별칭이나 1M 한도를 가정하지 않는다.
- `/v1/messages`/SSE/tool_result 오류: Anthropic 호환 endpoint인지 확인한다. OpenAI 전용 URL은 지원하지 않는다.
- effort 거부: gateway가 `output_config.effort`를 지원하는지 확인한다. 필요하면 새 명세의 effort를 high로 명시한다.
  HTTP 200만으로 max가 실제 적용됐다고 판단하지 않는다. thinking.budget_tokens로 상한을 강제한다고 주장하지 않는다.
- 워커 권한 거부: 기존 Claude Code 권한을 검토한다. 관리 실행기는 허용 목록이나 우회 옵션을 자동 추가하지 않는다.
- 작업 실패: `deepseek-task result <ID>`의 reason·워커/검증 종료 코드·timeout·로그를 확인한다.
  worker_timeout과 verification_timeout, model_error와 path_policy_violation을 구분한다.
- runner_lost: `status`에서 interrupted와 살아 있는 프로세스를 확인한다. 필요하면 해당 ID만 cancel한다.
  불확실한 이전 실행을 자동 재실행하지 않는다. 확인 뒤 `run <ID> --retry`로 새 시도를 만든다.
- stale input: 생산 태스크가 변경되었거나 재시도되어 고정한 시도와 다르다. 검토·검증 후 소비 태스크를 새로 등록한다.
- 원본 미커밋 입력: 자동 포함되지 않는다. 필요한 기준 커밋을 사용자가 준비하거나 검증된 태스크 inputs로 전달한다.

오프라인 검사는 `./tests/selftest.sh`, 실제 연결 검사는 `deepseek-probe`로 구분한다.
후자는 명시적으로 모델 요청을 보낸다. 실제 CLI 검증은 작은 관리 태스크로 추가 확인한다.
