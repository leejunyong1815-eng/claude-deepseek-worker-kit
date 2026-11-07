# 첫 작업

[README 설치](../README.md#설치)를 마치고 llm-backend list로 사용할 서버·모델·역할을 확인한다.
서버 연결 검사는 llm-probe이며 실제 모델 요청을 보낸다. 설치와 worker-doctor는 모델을 호출하지 않는다.

작업할 Git 저장소에서 project-init .을 실행한다. claude-duo 또는 codex-duo를 시작하고
원하는 기능과 완료 조건을 말한다. 기본 모드는 창 없는 관리 풀이며 --panes로 진행 상황 창을 띄울 수 있다.
메인이 태스크를 등록하고 풀의 워커가 격리된 worktree에서 실행한다. 사용자가 워커 이름을 고를 필요는 없다.

원본의 미커밋 변경은 자동 전달되지 않는다. 의존하는 태스크는 실행을 차단하고 필요한 입력부터 준비한다.
완료는 독립 검증 종료 코드·경로·해시로 결정한다. 메인은 task/attempt ID, 검증 근거와 남은 문제를 보고해야 한다.
서버 없이 먼저 확인하려면 ./tests/selftest.sh 또는 python3 -B demo/rehearse.py를 사용한다.
