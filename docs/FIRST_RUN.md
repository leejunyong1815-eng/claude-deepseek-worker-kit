# 첫 작업

README의 설치/서버 설정을 마친 뒤 대상 Git 프로젝트에서 실행한다.

```bash
deepseek-project-init .
deepseek-main
```

생성된 KICKOFF_PROMPT.md를 붙여 넣고 원하는 기능과 완료 조건을 말한다.
오케스트레이터가 조사·설계·테스트 초안·구현·독립 리뷰를 DeepSeek에 위임하고
각 task/attempt ID, 외부 검증 결과, 남은 문제를 보고해야 한다.

원본 미커밋 변경은 전달되지 않는다. 태스크가 이에 의존하면 실행 전에 알려야 한다.
관리 CLI 수동 진단은 MANAGED_TASKS.md를 따른다. 서버 없이 흐름을 먼저 보려면
`python3 -B demo/rehearse.py`를 사용한다. 이는 실제 모델의 구현 결과가 아니다.
