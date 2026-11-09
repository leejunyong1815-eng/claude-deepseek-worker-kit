# Codex/Claude 오케스트레이터 + LLM 워커 규칙

관리 워커(LLM_TASK_MANAGED=1)는 배정된 태스크 계약과 역할을 수행한다. 아래 오케스트레이터 절차로
자기 태스크를 다시 등록하거나 claude-main을 실행하지 않는다. 작업 공간·검증·보존 규칙은 동일하게 적용한다.

메인은 Claude 계정의 Opus 또는 Codex 계정/설정의 모델을 사용한다. 사용자가 목표를 말하면 필요한 관리 워커를 직접 호출한다.
메인의 native Agent/Task/fork Skill은 기본 selective 모드에서 EGM·고난도 추론/설계 판단에 선택적으로 사용할 수 있다.
`--native-agents off`면 차단한다. 현재 런처가 전달한 Native delegation mode를 따른다.
일반 구현·테스트는 계속 등록된 LLM 워커에 맡긴다. Workflow/팀과 별도 메인 실행은 계속 제한한다.
워커 모델은 서버/모델 레지스트리로 선택한다.
조사·설계 초안·모듈 구현·테스트 초안·실행·분석·독립 리뷰를 등록된 LLM 관리 태스크에 먼저 배정한다.
정책과 절차는 agents/ORCHESTRATOR.md, 역할은 agents/ROLE_*.md를 읽는다.

- 관리 CLI: worker-task submit/run/status/result/cancel. role은 researcher, planner, implementer,
  test-author, runner, analyst, reviewer 중 선택한다. Compute Job은 Qwen의 compute-runner에 배정한다. effort는 명세에 지정하지 않는다.
- 메인은 목표·계약·예산·권한·독립 수용 검사 신뢰성·최종 결정에 집중한다. 스켈레톤은 선택이다.
- selective 세션에서는 EGM 리뷰·아키텍처 선택·복잡한 원인 분석·엄밀한 추론처럼 독립 판단이 필요한 작업을
  native Agent에 직접 배정할 수 있다. 먼저 선택 이유·범위·기대 결과를 짧게 밝히고 읽기 전용으로 검토시킨다.
  원본/관리 worktree 편집이나 Git 변경은 맡기지 않는다. native 결과를 worker-task 성공으로 표시하지 않는다.
  권한·입력·서버 오류만으로 관리 실행을 native로 대체하지 않는다. 런처의 기본 모드는 selective다.
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
- workspace는 일반 Bash·환경 도구·웹·에이전트와 SSH/scp/sftp/rsync를 허용한다. 원격 조사·설정·실행·전송은 등록된 LLM 워커에 실제 호스트·원격 경로·범위·예산을 지정해 맡긴다. 기존 deny/ask는 보존한다.
- 코드 작업은 local/WSL이다. 명시된 Compute Job은 compute_job의 local/ssh 대상에서 실행한다.
  추론 서버를 SSH 계산 대상으로 추정하지 않는다. 원격 source 자동 업로드는 없으며 필요한 전송은 별도 태스크에 명시한다.
  Qwen은 잡 운영, 일반 역할 모델은 일반 서브에이전트 업무와 실험 코드·분석을 맡는다.
- 직접 SSH의 원격 변경·프로세스는 로컬 worktree 검증/취소에 자동 포함되지 않는다. 원격 revision·결과 근거를 남기며 대기/GPU 배정·원격 취소가 필요한 잡은 compute_job을 쓴다.
- 워커 종료 코드 0이나 '테스트 통과' 보고는 성공이 아니다. 외부 검증과 코드 해시·diff를 확인한다.
- worktree는 보안 샌드박스가 아니다. 같은 사용자 권한의 절대 경로/공유 Git refs 접근을 차단하지 않는다.
- 기존 대화형 메시징은 유지되지만 자동 격리·상태·검증이 없다. 코드 작업에는 관리 모드를 사용한다.
- 모든 수치에는 실행 명령·입력·결과 파일 근거를 붙인다. 실제 위임 비율·속도/비용 절감을 추정하지 않는다.

편집 훅은 .claude/settings.json의 PostToolUse에서 문법/lint를 확인한다. 이는 최종 외부 검증의 대체가 아니다.
프로젝트별 보호 경로·수용 기준은 태스크마다 추가한다.
