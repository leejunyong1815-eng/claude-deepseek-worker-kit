# 소스 출처

기반: https://github.com/leejunyong1815-eng/claude-local-worker-kit

기준 커밋: `37de483a975ac102b77059e9213735a03b0a4024`.
분리 시점의 미커밋 worker-first 정책과 안전한 프로젝트/설치 업데이트 구현도 포함했다.
원본 체크아웃의 파일·index·HEAD·remote는 변경하지 않고 별도 Git 저장소에서 작업했다.

재사용: 기존 Claude CLI wrappers, task runner, 템플릿/훅, updater, 로컬 CPU 데모와
모의 실행기 테스트. DeepSeek 전용 namespace, 설정, 역할/추론, 검증된 태스크 입력 전달은
이 별도 저장소의 변경이다. 원래 Qwen 서버의 성능/라우팅 기록은 DeepSeek의 결과가 아니므로
이 버전의 운영 문서나 성능 근거로 사용하지 않는다.
