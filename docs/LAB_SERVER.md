# 연구실 DeepSeek 서버 확인 기록 (2026-10-30)

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
- 따라서 키트의 max는 요청값이며 **gateway가 max를 실제 적용했다고 확인하지 못했다**.
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
