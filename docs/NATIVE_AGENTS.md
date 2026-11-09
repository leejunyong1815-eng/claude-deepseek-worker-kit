# 선택적 네이티브 위임

기본 위임은 등록된 LLM 관리 워커다. 네이티브 모드는 기본 selective이며 EGM 리뷰나 고난도 판단에
메인이 선택적으로 사용한다. `--native-agents off`를 명시하면 네이티브를 차단한다.
설정 파일은 수정하지 않는다. 상태 표시용 `LLM_MAIN_NATIVE_AGENTS` 환경변수로 실행 모드를 바꾸지 않는다.

```bash
claude-duo -n my-project -w 3
codex-duo -w 3
claude-main --resume
codex-main resume --last
claude-duo --manual -n design -w 2
# 네이티브 없이 관리 워커만 사용하는 세션
claude-duo --native-agents off
```

duo의 headless·panes와 직접 실행하는 두 main이 같은 모드를 사용한다. `--` 뒤 메인 인자로 전달해도 된다.
관리 풀은 pool.json의 `native_agents`에 선택을 기록한다. 재개한 메인은 현재 실행 옵션과 지침을 사용한다.
수동 duo는 모드도 세션 구분에 포함한다. 기본 selective 세션은 옵션 없이 `--kill`하고, off 세션에는 같은 off 옵션을 지정한다.
기존 수동 tmux 세션에 붙는 것만으로 그 세션의 지침이 바뀌지는 않는다.

## 배정 기준

| 작업 | 기본 경로 |
|---|---|
| 일반 코드 조사, 초안, 구현, 후보 테스트, 실행, 정형 리뷰 | 등록된 LLM 관리 태스크 |
| EGM의 독립 리뷰어 | selective의 네이티브 에이전트; 플러그인 별도 설치 |
| 아키텍처 선택, 엄밀한 추론·증명, 복잡한 원인 분석, 더 강한 독립 판단 요청 | 메인이 이유를 밝히고 selective의 네이티브 에이전트 선택 |
| 권한 거절, 입력 누락, 게이트웨이 장애, 단순 시간 초과 | 원인 해결·태스크 조정; 그 사유만으로 네이티브로 대체하지 않음 |

메인은 네이티브 호출 전에 이유·범위·기대 결과를 짧게 밝힌다. 사용자가 매번 특정 워커를 지정할 필요는 없다.
이 기준은 모델 지침이다. 런처는 도구 사용 가능 여부를 바꾸지만 호출 목적이나 난이도를 코드로 판별하지 않는다.
네이티브를 쓰는 편이 더 싸거나 더 빠르다고 가정하지 않는다. 반복 횟수와 동시 호출을 작업에 맞게 제한한다.

## 권한과 작업 공간

Claude의 selective는 Agent/Task/Skill에 대한 키트의 차단과 내장 에이전트 차단 환경변수를 제거한다.
Workflow/TeamCreate와 Bash에서 별도 claude 메인을 시작하는 제한은 유지한다. 사용자가 추가한
`--disallowedTools Agent` 등과 사용자·프로젝트·조직의 deny/ask는 제거하지 않는다.

Codex는 모드에 따라 현재 `agents.enabled`와 기존 `features.multi_agent`를 함께 지정한다.
현재 CLI와의 호환을 유지하며 승인·샌드박스·계정·모델·effort 설정은 바꾸지 않는다.
설정과 부모 권한 상속은 [OpenAI 공식 서브에이전트 문서](https://learn.chatgpt.com/docs/agent-configuration/subagents)를 따른다.

네이티브 에이전트는 소스·고정 입력을 읽고 판단·반례·리뷰 결과를 반환하도록 지시한다.
원본 checkout이나 관리 worktree의 파일·Git 상태를 변경하지 않으며, 제품 코드 변경은 기존 관리 태스크로 수행한다.
메인이나 EGM 종합자는 요청된 설계·보고서 파일을 작성할 수 있다. 읽기 전용 지시는 별도 OS 샌드박스를 만드는 기능이 아니다.
실제로 가능한 도구·경로는 해당 호스트의 권한 설정에 달려 있다. 임의 파일 편집을 기술적으로 차단했다고 주장하지 않는다.

네이티브의 모델은 메인 CLI의 계정·모델 설정을 사용한다. DeepSeek/Qwen 워커의 gateway나 모델 강제 환경을
Claude 메인에 전달하지 않는다. 워커에는 메인의 선택 모드를 전달하지 않으며 기존 워커 모델·권한·effort 생략은 유지한다.

## 결과와 중단

네이티브 호출은 별도 worker-task가 아니다. task/attempt ID, 관리 worktree, 검증 결과를 자동으로 만들지 않으며,
풀의 backend 동시 실행 제한과 관리 태스크 취소에도 포함되지 않는다. 중단·대기·결과 확인은 각 CLI의 세션 도구를 사용한다.
완료를 기다린 뒤 실패·누락을 보고하고 에이전트를 정리한다. 네이티브 보고를 worker-task의 succeeded로 표시하지 않는다.
관리 워커가 만든 제품 코드에는 기존 외부 검증을 그대로 적용한다.

EGM은 매 리뷰어를 새 맥락에서 실행하고 단계별 의존성과 사용자 승인 단계를 유지한다.
플러그인 설치나 호출 허용만으로 EGM 리뷰가 검증된 것은 아니다. 자세한 설치·제한은 [EGM 문서](EGM.md)를 따른다.

## 기존 설치에 적용

```bash
git pull --ff-only
./install.sh --update --setup-path
project-update --check /path/to/project
project-update --apply /path/to/project
```

기존 메인을 종료한 뒤 재개하면 기본 selective를 적용한다. 차단을 유지하려면 off를 지정한다. 수정한 프로젝트 문서는 incoming/의 제안을 검토한다.
오래된 지침에 네이티브 절대 금지가 남아 있으면 이번 세션의 모드와 맞게 갱신한다. 기존 deny 규칙은 별도로 존중한다.
