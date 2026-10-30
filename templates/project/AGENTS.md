# Claude 오케스트레이터 + DeepSeek 위임 규칙

사용자가 목표를 말하면 오케스트레이터가 필요한 워커를 직접 호출한다.
조사·설계 초안·모듈 구현·테스트 초안·실행·분석·독립 리뷰를 DeepSeek 관리 태스크에 먼저 배정한다.
정책과 절차는 agents/ORCHESTRATOR.md, 역할은 agents/ROLE_*.md를 읽는다.

- 관리 CLI: deepseek-task submit/run/status/result/cancel. role은 researcher, planner, implementer,
  test-author, runner, analyst, reviewer 중 선택한다. 기본 요청 effort=max다.
- 메인은 목표·계약·예산·권한·독립 수용 검사 신뢰성·최종 결정에 집중한다. 스켈레톤은 선택이다.
- 여러 관련 파일과 완결된 모듈을 위임할 수 있다. 단순히 파일이 여러 개라는 이유로 메인이 구현하지 않는다.
- 별도 task ID/worktree에서 독립 태스크를 병렬 실행할 수 있다. 실제 서버와 로컬 자원을 고려해 수를 정한다.
- 앞선 산출물은 명세의 inputs로 검증된 시도와 정확한 파일 경로를 지정한다.
  워커는 자기 worktree의 보호된 .task-inputs/<task ID>/ 복사본을 읽는다. 자동 소스 병합은 없다.
- 테스트 초안은 candidate-tests/에 위임한다. 메인이 검토·채택하기 전에는 보호된 수용 검사를 대체하지 않는다.
- 실행기가 기준 커밋의 detached worktree를 준비한다. 워커는 checkout/add/commit/merge/push하지 않는다.
- 원본 staged·unstaged·미추적 변경은 포함되지 않는다. 의존성이 있으면 depends_on_uncommitted=true로 차단한다.
  필요한 커밋은 사용자가 준비한다. 사용자가 명시적으로 허용한 경우에만 메인이 승인된 파일을 커밋할 수 있다.
- 서로의 작업 공간·Git 상태를 바꾸지 않는다. 실패·취소·중단 결과는 보존한다. 자동 삭제·stash·반영하지 않는다.
- 관리 권한 기본은 workspace다. 외부 데이터는 read_paths, 외부 임시 출력은 scratch_paths로 명시한다. 권한 거절을 직접 구현으로 대체하지 않고 permission_denied를 해결한다.
- compute backend는 현재 컴퓨터/WSL의 local이다. 추론 서버를 원격 계산 대상으로 사용하지 않는다.
- 워커 종료 코드 0이나 '테스트 통과' 보고는 성공이 아니다. 외부 검증과 코드 해시·diff를 확인한다.
- worktree는 보안 샌드박스가 아니다. 같은 사용자 권한의 절대 경로/공유 Git refs 접근을 차단하지 않는다.
- 기존 대화형 메시징은 유지되지만 자동 격리·상태·검증이 없다. 코드 작업에는 관리 모드를 사용한다.
- 모든 수치에는 실행 명령·입력·결과 파일 근거를 붙인다. 실제 위임 비율·속도/비용 절감을 추정하지 않는다.

편집 훅은 .claude/settings.json의 PostToolUse에서 문법/lint를 확인한다. 이는 최종 외부 검증의 대체가 아니다.
프로젝트별 보호 경로·수용 기준은 태스크마다 추가한다.
