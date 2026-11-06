# Qwen Compute Jobs

일반 서브에이전트 업무는 DeepSeek에 맡긴다. Qwen은 명시된 CPU/GPU 잡의 운영 보고를 담당한다.
메인이 명령·호스트·입력 코드·검증·자원·예산을 고정한다. 실행기가 실제 대기와 실행을 처리한 뒤
Qwen에 결과를 전달한다. Qwen의 자연어 판단으로 GPU를 비었다고 간주하거나 성공 처리하지 않는다.

## 로컬 CPU로 먼저 확인

```bash
./install.sh --profile qwen --non-interactive
cd /path/to/project
# 키트의 config/compute-task.example.json을 프로젝트에 맞게 편집해 /tmp에 저장한다.
TASK=$(deepseek-task submit /tmp/compute-task.json)
deepseek-task run "$TASK"
deepseek-task status "$TASK"
deepseek-task result "$TASK"
```

예시 명세는 별도 worktree에서 CPU로 합계를 계산하고, 독립 명령으로 결과를 확인한다.
그 다음 Qwen이 reports/compute-summary.md를 작성한다. 실제 모델을 사용하는 명령이다.
서버 없이 동작을 확인하려면 `./tests/selftest.sh`를 사용한다.

`role: compute-runner`에는 `compute_job`이 필요하다. profile을 생략하면 qwen이다.
다른 DeepSeek 역할에는 compute_job을 넣을 수 없다. 기존 task 상태·worktree·로그·잠금·검증을 재사용한다.

## 잡 명세

```json
{
  "resource": "gpu",
  "transport": "ssh",
  "ssh_host": "lab-gpu",
  "cwd": "/srv/experiments/my-project",
  "command": ["python3", "train.py", "--config", "experiment.json"],
  "verify": [["python3", "scripts/check_result.py"]],
  "gpus": [0, 1],
  "gpu_count": 1,
  "max_memory_mb": 1024,
  "max_utilization": 10,
  "idle_samples": 2,
  "poll_interval": 5,
  "wait_timeout": 1800,
  "timeout": 7200,
  "verify_timeout": 300
}
```

이 객체를 태스크의 compute_job에 넣는다. ssh_host는 사용자가 설정한 SSH 별칭 또는 user@host다.
LiteLLM 주소에서 추정하지 않는다. BatchMode=yes, StrictHostKeyChecking=yes를 사용하며
기존 SSH 키·agent·known_hosts로 연결한다. 비밀번호나 호스트 키 승인을 자동 입력하지 않는다.
대상에는 Linux, Python 3.9+, Git이 필요하며 GPU 모드는 nvidia-smi도 필요하다.

기본 transport는 local, resource는 gpu다. CPU 잡은 resource=cpu를 명시한다.
local의 cwd=@worktree는 이번 태스크의 worktree로 치환한다. 원본 checkout 아래의 로컬 cwd는 거절한다.
SSH의 cwd는 원격 컴퓨터에 이미 있는 절대 경로여야 한다. 명령·검증은 argv 배열로 전달해
SSH 셸에 사용자 인자를 삽입하지 않는다. bash -c처럼 셸이 필요한 잡은 명세에서 명시해야 한다.

모든 잡은 검증 명령이 하나 이상 필요하다. 모델 워커의 timeout/max_turns와 별개로
wait_timeout, timeout, 각 명령의 verify_timeout을 적용한다. 출력·결과는 자동 삭제하지 않는다.

## GPU 배정

nvidia-smi의 메모리·사용률과 compute process 목록을 함께 확인한다. 지정한 후보 중
프로세스가 없고 두 임계값 이하인 GPU가 idle_samples회 연속 관찰돼야 한다.
그 뒤 같은 사용자 계정의 GPU UUID별 flock을 획득하고 실제 상태를 다시 확인한다.
배정한 UUID만 CUDA_VISIBLE_DEVICES로 전달하며 CPU 모드는 이를 비운다.
계측 실패·N/A·없는 GPU는 실행하지 않는다. GPU 대기 제한과 잡/검증 시간 초과는 구분한다.

잠금은 같은 계정의 이 도구를 쓰는 잡끼리 협력하는 방식이다. 다른 사용자나 외부 스케줄러의
동시 시작을 강제로 차단하지 않는다. Slurm 같은 클러스터 예약 서비스나 GPU 보안 격리를 대신하지 않는다.

## 코드와 결과의 대응

원격 소스 업로드·Git checkout·commit·패키지 설치는 하지 않는다. 원격 작업 디렉터리는
사용자가 미리 준비한다. 관련 코드의 실행임을 고정하려면 expected_commit에 전체 Git SHA를 넣는다.
실행 전 clean revision을 확인하고, 실행·검증 뒤 HEAD와 tracked source 변경을 다시 검사한다.
생략하면 source_pinned=false와 관찰한 source_commit/source_dirty를 남긴다.
이 경우 잡의 종료·검증 성공을 특정 로컬 수정본의 검증 증거로 사용하면 안 된다.
원격 미추적 파일 전체의 출처나 데이터셋 버전까지 증명하지는 않는다.

## 로그와 취소

태스크 시도 폴더에 compute.spec.json, compute.result.json, compute.stdout.log,
compute.stderr.log를 보존한다. status/result의 compute_result에 실제 잡 종료 코드, 검증 코드,
선택 GPU, 원격 로그 경로, 실행 시간과 실패 이유가 들어간다. Qwen 보고와 무관하게 검사한다. 로컬 잡은 해당 run의 stdout/stderr·검증 로그와 원본 결과 파일만
Qwen의 읽기 경로에 추가하며 파일 도구 수정은 허용하지 않는다. 다른 run이나 원격 경로는 포함하지 않는다.
성공 뒤 로컬 compute 명세/결과가 바뀌어도 성공은 무효다.

잡 stdout/stderr와 검증 로그는 실행 컴퓨터의
`${XDG_STATE_HOME:-~/.local/state}/deepseek-worker/compute/<run-id>/`에 남는다.
이 버전은 원격 로그 본문·결과 파일을 자동 다운로드하지 않는다. 분석 입력은 명시적으로 준비한다.
비밀 키를 명령 인자·명세·출력에 넣지 않는다. 추론 API 키는 잡에 전달하지 않는다.

`deepseek-task cancel <ID>`는 해당 실행만 취소한다. 원격 실행기는 새 프로세스 그룹을 만들며
그 그룹만 종료한다. EOF/SIGHUP/heartbeat 단절도 같은 잡을 정리한다. 기본 heartbeat lease는 30초다.
연결이 끊겨 종료 확인을 받지 못하면 interrupted/transport_lost와
remote_cleanup_confirmed=false를 기록한다. 이를 취소 완료로 간주하거나 자동 재실행하지 않는다.
원격 상태를 확인한 뒤 명시적으로 재시도한다. 재시도는 이전 잡을 다시 실행할 수 있다.
스스로 다른 세션으로 이탈하는 데몬은 지원하지 않는다.

## 단독 실행

모델 없이 동일 실행기만 확인할 때는 아래 명령을 쓴다. 이때 cwd는 실제 절대 경로를 지정한다.

```bash
worker-compute-job /tmp/job.json --result /tmp/unique-job-result.json
```

같은 결과 경로를 다시 사용하면 거절한다. 관리 태스크에는 시도별 경로가 자동 배정된다.
실제 원격 GPU 테스트는 수행하지 않았으며, 로컬 CPU 잡과 모의 SSH/GPU로 검증했다.
