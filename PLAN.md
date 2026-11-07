# 구현 상태

공유 구현:
- Claude/Codex 메인, headless/panes 관리 풀, 기존 수동 메시징 모드와 호환 명령.
- 여러 서버·여러 모델 등록, 모델별 역할과 서버별 동시 실행 한도, 소유 풀/워커 ID.
- 별도 worktree, 원자적 상태·잠금, 시도 보존, 작업별 취소·복구, 모델 외부 완료 검증.
- SSH/scp/sftp/rsync·일반 도구 권한, 기존 deny/ask 보존, 보호 경로와 파일 해시 검사.
- 로컬/SSH Compute Job, GPU admission/locking, 명령·검증·원격 취소와 결과 기록.
- 기존 설정 가져오기와 안전한 프로젝트 업데이트, 오프라인 테스트와 로컬 CPU 데모.

남은 검증:
- 사용자 Codex/Claude 메인 계정의 실제 추론과 다양한 모델의 작업 품질. 연구실 DeepSeek/Qwen 워커의 실제 풀 연동은 validation/unified-kit.json에서 확인한다.
- 실제 원격 SSH/GPU 운영 환경과 장애 조건. 현재 로컬 CPU/모의 SSH 검사를 일반화하지 않는다.
- 토큰·속도·품질·동시 처리량 측정. 유휴 호출 제거를 실제 절감률로 환산하지 않는다.
- 대규모 컨텍스트 품질과 gateway의 reasoning 제어. 기존 effort 값은 실행기에 전달하지 않는다.

범위 밖: 모델 실패 시 자동 fallback, 웹 UI, 자동 merge/push/PR, 대규모 벤치마크.
계획 문구는 구현·테스트·실제 서버 연동의 증거가 아니다. 실제 확인 범위는 테스트와 validation 기록을 따른다.

통합 전 작업 문서: [계획 원문](docs/legacy/original-plan.txt), [운영 README](docs/legacy/original-readme.txt), [문제 해결 기록](docs/legacy/original-troubleshooting.txt). 과거 지침이며 현재 동작의 근거로 사용하지 않는다.
