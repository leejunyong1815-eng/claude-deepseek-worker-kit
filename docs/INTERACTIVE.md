# 표시 모드와 수동 메시징

`claude-duo`와 `codex-duo`는 같은 관리 풀을 사용한다. 기본 `--headless`는 메인만 화면에 띄우고,
`--panes`는 tmux에 메인과 워커별 작업 상태를 표시한다. 각 워커는 queued 태스크를 가져오며
실행·worktree·검증·취소는 worker-task가 담당한다. 대기 중에는 모델을 호출하지 않는다.

`-w auto`는 등록 서버별 max_parallel 합계와 --max-workers(기본 4)를 기준으로 워커 수를 정한다.
`-w N`은 개수를 고정한다. 서버 동시 실행 한도는 별도로 유지된다. `--backends`는 서버 이름 목록,
`--models`와 `-P/--profiles`는 모델·프로필 고정 목록이다. 한 값 또는 워커 수만큼 지정한다.
모델을 고정하지 않으면 역할 등록과 큐 길이로 배정하며 실패 시 다른 모델로 자동 대체하지 않는다.

소속은 UID/pool ID/worker ID로 판단한다. --label과 뒤에 붙인 일반 단어는 표시용이며
공백·한글·셸 문자를 명령으로 평가하지 않는다. `llm-worker list`에서 owned 여부와 현재 task ID를 본다.
`llm-worker stop <pool-id>`는 해당 풀의 워커와 실행 태스크만 중단하고 결과를 보존한다.
`claude-duo --kill` 또는 `codex-duo --kill`은 현재 프로젝트에서 해당 메인의 마지막 소유 풀을 종료한다.
다른 프로젝트나 다른 종류의 메인은 종료하지 않는다.

## 이전 수동 모드

```bash
claude-duo --manual -w 2
claude-duo --manual -w 0 -P impl,review
# 메인 이름과 워커 권한을 명시하는 경우
claude-duo --manual -n ozaki -w 2 --permission-profile workspace
```

기존 Claude 세션 간 메시징을 사용한다. `claude-worker`/`llm-worker`를 별도 터미널에서 띄울 수도 있다.
이 모드에는 자동 task ID·worktree·외부 검증이 없다. 코드 편집은 직접 준비한 독립 worktree에서 수행한다.
수동 tmux pane들은 같은 프로젝트에서 시작하므로 같은 파일을 병렬 수정하면 안 된다.
관리 풀의 pane은 대화형 채팅 세션이 아니라 태스크 실행 상태를 보여 준다.

`-n/--name`은 메인의 표시 이름이다. 직접 실행하는 `claude-main -n ozaki`,
`llm-worker -n 'llm-worker-검토 v2'`에도 적용되며 지정한 이름은 바꾸지 않는다.
지정하지 않으면 독립 실행은 고유 접미사를 붙인다. 수동 duo의 tmux 이름은 프로젝트 경로와
지정한 메인 이름에서 정하므로 다른 프로젝트에 자동으로 붙지 않는다. 같은 프로젝트·이름이면 기존 세션에 붙는다.
종료도 같은 위치·이름으로 `claude-duo --manual -n ozaki --kill`을 실행한다.
기존 고정 이름이 필요하면 `LLM_DUO_SESSION=내세션`을 명시한다.

수동 duo는 워커들의 정확한 표시 이름 목록을 메인 프롬프트에 전달한다. 메인은 세션 조회에서
실제 살아 있는 세션 ID를 확인해 메시지를 보낸다. 접미사를 제거하거나 `llm-worker` 접두사로
아무 세션이나 선택하지 않는다. 사용자가 직접 중복 이름을 지정했거나 이름을 나중에 바꿨다면 대상을 다시 확인해야 한다.
임의로 따로 띄운 세션은 이 목록에 자동 편입되지 않는다.

기본 수동 워커는 기존 Claude 권한 설정을 사용하므로 승인 질문이 나올 수 있다.
질문을 볼 수 없는 운영에는 관리 모드를 권장한다. 수동 모드에서 미리 권한을 주려면
`--permission-profile workspace`를 명시한다. `--permissions-file`, `--read-path`,
`--scratch-path`도 워커에 전달한다. 사용자·프로젝트 권한 파일은 바꾸지 않으며 기존 deny/ask는 유지한다.
이 옵션이 자동 worktree나 완료 검증을 추가하지는 않는다. 상세 범위는 [권한 문서](WORKER_PERMISSIONS.md)를 따른다.

Claude 기본 Agent는 메인과 같은 CLI/연결 설정 안에서 동작한다. 여러 서버와 모델을 독립 선택하고
같은 완료 검증을 적용하기 위해 이 키트의 창 없는 모드도 별도 관리 프로세스를 사용한다.
메인의 내장 Agent 또는 Codex multi-agent 도구는 기본 selective로 EGM·고난도 판단에 사용할 수 있다.
`--native-agents off`로 차단할 수 있으며 일반 구현·테스트는 관리 워커에 남긴다. 사용자 권한·샌드박스는 우회하지 않는다.
수동 duo의 세션도 모드별로 구분하므로 off 세션에 붙거나 종료할 때는 같은 off 옵션을 지정한다.
[배정 기준과 결과 관리](NATIVE_AGENTS.md)를 참고한다.
