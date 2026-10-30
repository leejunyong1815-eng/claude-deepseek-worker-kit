# 구현과 연결 대기 사항

구현됨 (코드/검증 기록으로 확인):
- 관리 모드 workspace/custom/inherit 권한 프로필, 외부 read/scratch 경로, 고정된 --settings 전달.
- 권한 거절의 별도 실패 기록, 권한 파일 무결성 검사와 일반 도구 활성화.
- 새 WSL 설치 문서, 로컬 진단(--check/deepseek-doctor), 명시적 Bash PATH 설정(--setup-path).
- 새 HOME·공백 경로·독립 clone에서 설치된 CLI로 관리 태스크를 실행하는 회귀 검사.
- 기존 원자적 상태/잠금, 시도별 detached worktree, 프로세스 식별·취소·복구, 외부 검증 재사용.
- DeepSeek 전용 명령·설정·상태 namespace, 인증 정보 없는 실행 차단.
- 일곱 역할, 요청 effort=max, 120턴 및 별도 워커/검증 시간 제한.
- 검증된 앞선 태스크의 파일/시도/해시를 고정하는 inputs 전달과 입력 보호.
- 프로젝트 규칙·역할·업데이트·데모 문서 갱신, 모의 CLI 기반 테스트.

서버 확인됨 (2026-10-30, docs/LAB_SERVER.md):
- 등록 모델 세 개, DeepSeek 기본 URL/ID와 서버 max_model_len=1048576 확인.
- 실제 Anthropic tool_use/tool_result 연속 처리·SSE 검사 통과.
- 4개 입력 길이×3회 + reasoning 문제 3회의 실제 API 측정, API 키 없는 원시 결과 저장.

남은 확인:
- max effort의 실제 적용: OpenAI reasoning_effort는 gateway에서 거절, Anthropic 수락만으로 적용을 보장하지 않음.
- 1M 입력 품질·서버 내부 prefill/decode 시간·동시 처리량과 최대 출력 한도는 미측정.
- Claude Code의 실제 권한 설정에서 작은 관리 태스크 한 개와 독립 리뷰 한 개.
- 동시성/작업 품질 측정 후 예산 조정. 단일 서버 측정만으로 기존 버전 대비 향상을 주장하지 않음.

제외: 원격 스케줄러, 모델 자동 선택/fallback 변경, 웹 UI, 자동 merge/push/PR,
대규모 벤치마크. 문서의 계획은 구현이나 실제 연동의 증거가 아니다.
