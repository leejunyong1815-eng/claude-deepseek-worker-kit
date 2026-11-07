# 통합 출처

Local Worker Kit은 두 프로젝트를 하나의 서버/모델 설정과 실행기로 통합했다.

- 원본 claude-local-worker-kit 기준: 37de483a975ac102b77059e9213735a03b0a4024.
- DeepSeek 버전 가져오기 기준: 37905806e407fd85d6a3fad288f609c80454bd54.
- 원본의 진행 중이던 worker-first 지침·프로젝트 updater·설치 updater·문서·테스트 개선도 대조해 통합했다.
- 기존 remote-* 수동 도우미, proxy 예시, 벤치마크 fixture/결과와 로컬 CPU 데모는 보존했다.

핵심 실행기는 worker-task 하나다. deepseek-*와 claude-worker는 호환 dispatch 명령이며 별도 엔진이 아니다.
서버·모델·역할·동시성은 레지스트리로 선택한다. Codex/Claude 계정 메인과 LLM 워커 서버 인증은 별도다.
과거 validation/bench 기록은 당시 버전·서버의 기록으로 보존하며 통합본의 새 성능 측정으로 취급하지 않는다.

proxy/와 remote-*는 기존 수동 환경용이며 통합 레지스트리의 기본 연결을 자동 변경하지 않는다.

진행 중이던 계획·운영 문서는 docs/legacy/에 역사 자료로도 보존했다. 전체 미커밋 원본 사본은 통합 작업 시 별도 디렉터리에 유지했다.
