# API 속도·thinking 소규모 측정

`python3 -B bench/backend_probe.py --output /tmp/new-deepseek-speed.json`으로 실행한다.
API 키는 숨김 입력 또는 LLM_API_KEY 환경변수로 전달한다. 네트워크와 실제 모델 요청이 발생한다.
입력 4개 길이×3회(출력 최대64토큰)와 수학 문제3회(최대1024토큰)를 순차 실행한다.
측정 시 기본 reasoning 설정을 쓰며 거절되는 reasoning_effort를 자동 우회하지 않는다.
JSON은 실제 usage의 reasoning/출력 토큰 수, TTFT, 전체 요청 속도와 관측 스트림 속도를 구분한다.
Prefill은 입력 크기별 TTFT 기울기 추정치이며 순수 서버 타이머가 아니다. 캐시·gateway 버퍼링의 영향이 남는다.
결과에는 인증 정보나 thinking 원문을 저장하지 않으며 기존 결과를 덮어쓰지 않는다.
현재 측정 결과와 한계: [서버 기록](../docs/LAB_SERVER.md).

아래 구현 능력 벤치마크는 별도 선택 기능이다.

# bench — 워커 단독 구현 벤치마크

로컬 모델 워커에게 구현 태스크를 **혼자** 풀게 하고 숨은 테스트로 채점한다. "약하다"는 평판 대신 숫자로,
모델·서버·프롬프트·훅을 바꿨을 때 어디까지 맡길 수 있는지 본다.

```bash
bench/run.sh -P impl                 # 전부 (기본 6 + 어려운 4), 훅 켬, 결과 bench/results/<날짜>_impl.md
bench/run.sh -P impl --tier hard     # 어려운 것만
bench/run.sh -P impl --no-hooks B5_module_spec   # 훅 없이 한 태스크만 (훅 효과 비교)
```

채점: (1) `tests/` 를 건드리지 않았고 (2) 공개 테스트 통과 (3) 숨은 테스트(`hidden/`, 워커에게 안 보임) 통과 → PASS.
워커는 `--permission-mode acceptEdits` 에 명령 허용 목록(python/pytest/git/ls/cat …)으로 비대화 실행되며, 태스크당 시간 제한과 `--max-turns 60` 이 있다.
작업 복사본과 원본 JSON 은 `$BENCH_WORK`(기본 `/tmp/claude-bench`)에 남는다.

## 태스크

| 단계 | 태스크 | 유형 | 측정하는 것 |
|---|---|---|---|
| 기본 | B1_bugfix | 실패 테스트 1개 고치기 | docstring 의 오류 조건까지 읽는가 |
| 기본 | B2_signature | 시그니처+docstring 에서 함수 구현 | 명세의 오류 케이스 전부 |
| 기본 | B3_cli_flag | argparse 옵션 추가 + 종료 코드 | 기존 동작 보존 |
| 기본 | B4_refactor | 중복 함수를 util 로 추출 | 동작 불변, 지시대로 import |
| 기본 | B5_module_spec | 명세만 보고 LRU+TTL 캐시 모듈 작성 | "전체 코드 작성" (스켈레톤 없음) |
| 기본 | B6_module_skeleton | B5 와 같은 모듈, 스켈레톤+docstring 제공 | 오케스트레이터가 뼈대를 주면 얼마나 나아지는가 |
| 어려움 | H1_expr_parser | 재귀 하강 수식 평가기 (우선순위·우결합·오류 위치) | 파서 설계, 오류 위치 정확성 |
| 어려움 | H2_scheduler | 의존성 그래프 리스트 스케줄러 + 사이클 보고 | 그래프 알고리즘, 결정적 타이브레이크 |
| 어려움 | H3_json_patch | RFC 6902 JSON Patch (포인터 이스케이프, 원자성, 엄격 비교) | 명세 세부 조항 준수 |
| 어려움 | H4_multifile_txn | 세 파일에 걸친 트랜잭션 기능 + CLI 하위 명령 | 다중 파일 변경, 원자성 |

새 태스크 추가: `tasks/<이름>/fixture/`(워커가 받는 파일), `tasks/<이름>/TASK.md`(지시), `tasks/<이름>/hidden/test_*.py`(채점용).
기준 해답으로 숨은 테스트가 통과하는지 먼저 확인한다.

## 결과 읽는 법

- `결과` PASS/FAIL, `공개 테스트`/`숨은 테스트` 는 pytest 마지막 줄, `tests/ 보존` 아니오면 워커가 테스트를 고쳤다.
- 공개는 통과했는데 숨은 테스트가 실패하면 명세의 구석(오류 조건, 경계)을 놓친 것 — 오케스트레이터가 테스트를 더 촘촘히 써 주면 잡힌다.
- B5 와 B6 의 차이가 "스켈레톤을 Claude 가 써 주는" 분업의 효과다.
- `--no-hooks` 와 비교하면 훅의 효과를 본다. 2026-10-29: 편집마다 테스트를 돌리는 훅은 어려운 태스크에서 역효과(0/4 vs 3/4)였고, 이후 훅 기본은 문법·lint 만으로 바꿨다.
