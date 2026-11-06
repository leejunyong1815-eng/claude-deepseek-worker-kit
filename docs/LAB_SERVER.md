# 연구실 LiteLLM 서버

현재 기본 주소는 http://1.233.219.161:4000 이다. 새 설치는 인증 모드 none을 사용한다.
기본값에 실제 API 키는 없다. 모델 목록과 /model/info를 조회해 아래 구성을 확인했다.

| 역할 | Anthropic 모델 ID | OpenAI 호환 모델 ID | 프록시 max_input_tokens |
|---|---|---|---|
| 일반 위임 | deepseek-v4.1-flash | deepseek-v4.1-flash-oai | 262144 |
| Compute Job 운영 | qwen3.8-flash-next | qwen3.8-flash-next-oai | 262144 |

컨텍스트는 프록시 메타데이터 값이며 256K 입력을 실제로 채워 품질을 검증한 결과는 아니다.
출력 예산을 합쳐 무제한으로 사용할 수 있다는 뜻도 아니다. 이전 서버의 1M 설정은 승계하지 않는다.

실제 모델에 도구 호출과 tool-result 연속 요청, SSE 종료, thinking/effort 요청,
Responses 텍스트 요청을 보냈다. 키·thinking 원문 없이 [API 검사](validation/litellm-compatibility.json),
[초기 실패](validation/litellm-initial.json), [Responses 재검사](validation/litellm-responses-recheck.json)에 요약을 남겼다.
DeepSeek의 복잡한 영문 marker 문자열 재현에는 실패 사례가 있었다. 단순 PONG의 SSE 전달은
재검사에서 통과했으며, 이 사실을 모든 프롬프트의 내용 정확성으로 일반화하지 않는다.
Responses의 단순 텍스트 통과도 Codex 전체 도구 호환성을 증명하지 않는다.

[실제 Claude CLI 검사](validation/managed-local-cpu.json)로 DeepSeek 구현/보호 테스트와 Qwen CPU 잡 운영 태스크를 실행했다.
CPU 잡은 실행기가 수행하고 독립 검증 후 Qwen에 결과를 전달했다. 실제 원격 GPU 호출은 하지 않았다.
속도·동시 처리량·모델 간 품질/비용 우위는 새 서버에서 측정하지 않았다.
Claude CLI의 costUSD는 서버 청구액이 아니므로 비용 근거로 쓰지 않는다.

```bash
python3 -B bench/litellm_check.py --base-url http://1.233.219.161:4000 --output /tmp/litellm-check.json
```

이 명령은 실제 모델 요청을 보낸다. 인증이 필요하면 LLM_API_KEY를 환경변수로 제공한다.
기존 env의 마이그레이션은 README/UPDATING.md를 따른다.

## 워커 effort 생략

워커 실행에서는 --effort와 CLAUDE_CODE_EFFORT_LEVEL을 생략한다. 기존 env/task의 effort 값은
실행에 적용하지 않는다. 일반 deepseek-probe도 output_config.effort를 보내지 않는다.
bench/litellm_check.py의 effort 호환 검사는 --check messages_effort로 명시할 때만 실행한다.

격리된 새 HOME에서 옵션·환경변수 생략 시 DeepSeek 구현과 Qwen CPU 잡 운영이 성공했다.
[검증 기록](validation/effort-omission.json)에 98개 오프라인 검사, 실제 모델·로그 읽기·기존 설정 호환 결과를 남겼다.
현재 Claude CLI 2.1.314의 요청 기록에는 기본 high가 있었다. 따라서 CLI 명시 설정 생략과
HTTP effort 필드 제거를 구분한다. 앞선 max 시간 초과에는 프록시 HTTP 500도 있어 원인을 하나로 단정하지 않는다.

## 이전 서버의 기록 (2026-10-30)

아래는 이전 주소에서 당시 측정한 기록이다. 현재 기본값이나 새 서버의 속도 측정이 아니다.


기본값은 [backend.defaults.json](../config/backend.defaults.json)에 저장한다. API 키는 포함하지 않는다.
이 기록은 해당 날짜의 서버 응답이며 이후 배포 설정이 바뀌면 다시 확인해야 한다.

| 항목 | 확인값 |
|---|---|
| 기본 주소 | `http://133.186.146.224:8081` |
| 기본 모델 ID | `DeepSeek-V4.1-Flash` |
| 컨텍스트 설정 | **1,048,576토큰 (1M)** |
| 그 외 등록 ID | `qwen3.8-27b-fp8`, `qwen3.8-flash-next` |

`GET /v1/models`와 `/model/info`를 인증해서 조회했다. 목록은 gateway의 등록 이름이며 다른 모델을 fallback으로 설정하지 않는다.
메타데이터의 토큰 한도는 null이었다. 짧은 입력에 지나치게 큰 `max_tokens`를 지정했을 때 서버가 반환한
HTTP 400에 `max_model_len=1048576`이 명시됐다. 같은 값의 출력 예산을 지정한 짧은 요청도 HTTP 200으로 끝났다.
이는 **서버가 설정한 한도**의 확인이다. 1M 입력 처리 시간이나 장문 품질을 검증한 결과는 아니다.
이번 측정에서 가장 긴 실제 입력은 65,589토큰이다.

OpenAI Chat Completions와 Anthropic Messages 모두 HTTP 200을 확인했다.
기존 deepseek-probe의 실제 tool_use → tool_result 연속 요청과 SSE 검사도 통과했다.
Claude CLI를 사용하는 관리 태스크의 실제 모델 연동은 아직 실행하지 않았다.

## thinking 제어의 현재 제한

OpenAI 응답은 usage.completion_tokens_details.reasoning_tokens와 스트리밍 reasoning_content를 반환한다.
실제로 reasoning이 생성되지만 양은 문제·호출마다 달랐다.

- OpenAI 경로의 `reasoning_effort=low/high/max`는 각각 HTTP 400 UnsupportedParamsError로 거절됐다.
- Anthropic 경로의 thinking/output_config.effort=max 요청은 받아들였지만 thinking 블록은 관찰되지 않았다.
- 따라서 당시 키트의 max는 요청값이며 **gateway가 max를 실제 적용했다고 확인하지 못했다**.
  이 측정은 서버 기본 reasoning 설정으로 수행했다. 서버 옵션을 변경하거나 거절된 필드를 자동 우회하지 않았다.

## 속도 측정

각 길이마다 다른 합성 숫자 입력을 3회씩 순차 요청했다. 출력 예산은 64토큰이다.
별도 수학 문제는 3회, 출력 예산 1024토큰으로 측정했고 모두 stop으로 종료했다.
토큰 수는 실제 API usage를 사용하며 문자 수나 SSE chunk 수를 토큰으로 세지 않는다.

| 실제 입력 토큰 | 첫 토큰 지연 중앙값 |
|---:|---:|
| 564 | 0.070초 |
| 4,149 | 0.081초 |
| 16,437 | 0.193초 |
| 65,589 | 0.676초 |

길이별 중앙 TTFT를 입력 토큰 수에 선형 적합한 **유효 prefill 추정치**는 약 **105,017 tok/s**다.
고정 지연 추정은 0.049초, R²는 0.998이다. TTFT에는 네트워크·대기·tokenization·첫 chunk 전달이 포함된다.
고유 입력을 사용했으나 실제 prefix cache 적중 여부는 독립 확인하지 못했다.
서버 내부 prompt 처리 시간을 직접 측정한 GPU prefill 수치로 해석하지 않는다.

수학 문제 반복 측정:

| 지표 | 결과 |
|---|---:|
| reasoning 토큰 | 179 / 134 / 172 (중앙값 **172**) |
| 첫 reasoning~첫 본문 구간 중앙값 | **0.293초** (클라이언트 관측) |
| 전체 출력 토큰 | 231 / 240 / 340 |
| 전체 요청 시간을 포함한 출력 속도 중앙값 | **560.5 tok/s** |
| 첫 출력~마지막 출력 구간의 관측 스트림 속도 중앙값 | **607.1 tok/s** |
| 첫 토큰 지연 중앙값 | 0.032초 |

출력 속도는 reasoning과 본문 토큰을 합친 값이다. 스트림은 gateway가 묶어서 전달할 수 있으므로
607.1 tok/s를 순수 서버 decode 속도로 단정하지 않는다. 별도 사전 요청에서는 reasoning 288토큰,
전체 출력 465토큰, 총 1.993초(233.4 tok/s)가 관찰됐다. 문제·시점·캐시·부하에 따라 달라질 수 있다.
이 소규모 순차 측정은 동시 처리량이나 서비스 보장 수치가 아니다.

원시 요청별 수치: [속도 JSON](../bench/results/2026-10-30_deepseek-server.json),
[호환성·한도 근거](../bench/results/2026-10-30_deepseek-compatibility.json).

재측정 (API 키는 숨김 입력 또는 LLM_API_KEY 환경변수; 기존 결과는 덮어쓰지 않음):

```bash
python3 -B bench/backend_probe.py --output /tmp/new-deepseek-speed.json
```

키·인증 헤더·생성 본문·thinking 원문은 결과 파일에 기록하지 않는다.
