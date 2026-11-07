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
```

기존 Claude 세션 간 메시징을 사용한다. `claude-worker`/`llm-worker`를 별도 터미널에서 띄울 수도 있다.
이 모드에는 자동 task ID·worktree·외부 검증이 없다. 코드 편집은 직접 준비한 독립 worktree에서 수행한다.
수동 tmux pane들은 같은 프로젝트에서 시작하므로 같은 파일을 병렬 수정하면 안 된다.
관리 풀의 pane은 대화형 채팅 세션이 아니라 태스크 실행 상태를 보여 준다.

Claude 기본 Agent는 메인과 같은 CLI/연결 설정 안에서 동작한다. 여러 서버와 모델을 독립 선택하고
같은 완료 검증을 적용하기 위해 이 키트의 창 없는 모드도 별도 관리 프로세스를 사용한다.
메인의 내장 Agent/Workflow 또는 Codex multi-agent 도구는 비활성화한다. 사용자 권한·샌드박스는 우회하지 않는다.
