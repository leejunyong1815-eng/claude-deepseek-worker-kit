# 기존 키트와 함께 사용하기

이 버전은 기존 키트의 in-place 모델 교체가 아니다. 별도 저장소와 namespace를 사용한다.

| 항목 | 기존 키트 | DeepSeek 버전 |
|---|---|---|
| 명령 | claude-main / claude-worker / worker-task | deepseek-main / deepseek-worker / deepseek-task |
| 실행 파일 기본 경로 | ~/.local/bin | ~/.local/deepseek-worker/bin |
| 설정 | ~/.config/claude-worker | ~/.config/deepseek-worker |
| 태스크 상태 | ~/.local/state/claude-worker/tasks | ~/.local/state/deepseek-worker/tasks |
| 규칙 설치/업데이트 | project-init / project-update | deepseek-project-init / deepseek-project-update |
| tmux 세션 | claude-duo | deepseek-duo |

기존 API 키·Qwen 설정·상태를 자동 복사하지 않는다. 연구실 DeepSeek 서버 정보를 별도로 입력한다.
프로젝트에 이미 기존 키트 규칙이 있다면 `deepseek-project-init`은 이를 덮어쓰지 않는다.
`deepseek-project-update --check`의 충돌을 읽고 incoming 제안을 수동으로 합친다.
기존 키트의 template history와 다른 파일은 자동 갱신 대상으로 추정하지 않는다.

수동 메시징은 두 버전에서 유지된다. 관리 모드의 task ID와 기록은 각 상태 디렉터리에 속하므로
서로 바꾸어 사용하지 않는다. 원격 실행 도우미와 Qwen fallback 설정은 이 버전에 포함하지 않는다.
