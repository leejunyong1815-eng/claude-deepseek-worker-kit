#!/usr/bin/env python3
"""Small sequential HTTP/SSE benchmark. API key is read privately, never written."""
import argparse
import datetime
import getpass
import json
import os
from pathlib import Path
import random
import statistics
import time
import urllib.error
import urllib.request

KIT = Path(__file__).resolve().parents[1]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('redirect refused')


def stream_request(opener, base, model, key, prompt, max_tokens, timeout):
    body = dict(model=model, messages=[{'role': 'user', 'content': prompt}],
                max_tokens=max_tokens, stream=True, stream_options={'include_usage': True})
    request = urllib.request.Request(base.rstrip('/') + '/v1/chat/completions',
        data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + key})
    start = time.perf_counter()
    first = last = first_reasoning = first_content = None
    usage = {}
    chunks = first_chunk_chars = reasoning_chars = content_chars = 0
    finish = []
    done = False
    with opener.open(request, timeout=timeout) as response:
        header_seconds = time.perf_counter() - start
        for line in response:
            if time.perf_counter() - start > timeout:
                raise TimeoutError('request time limit')
            if not line.startswith(b'data:'):
                continue
            raw = line[5:].strip()
            if raw == b'[DONE]':
                done = True
                break
            row = json.loads(raw)
            if row.get('error'):
                raise ValueError('SSE error event')
            if row.get('usage'):
                usage = row['usage']
            for choice in row.get('choices', []):
                delta = choice.get('delta', {})
                reasoning = delta.get('reasoning_content') or delta.get('reasoning') or ''
                content = delta.get('content') or ''
                if reasoning or content:
                    stamp = time.perf_counter()
                    if first is None:
                        first = stamp
                        first_chunk_chars = len(reasoning) + len(content)
                    last = stamp
                    chunks += 1
                    if reasoning and first_reasoning is None:
                        first_reasoning = stamp
                    if content and first_content is None:
                        first_content = stamp
                    reasoning_chars += len(reasoning)
                    content_chars += len(content)
                if choice.get('finish_reason'):
                    finish.append(choice['finish_reason'])
    end = time.perf_counter()
    if first is None or not done or not finish:
        raise ValueError('incomplete token stream')
    if not all(isinstance(usage.get(k), int) and usage[k] >= 0 for k in ('prompt_tokens','completion_tokens')):
        raise ValueError('API token usage is required for speed measurement')
    result = dict(header_seconds=header_seconds, ttft_seconds=first-start,
                  stream_seconds=last-first, total_seconds=end-start,
                  first_reasoning_seconds=None if first_reasoning is None else first_reasoning-start,
                  first_content_seconds=None if first_content is None else first_content-start,
                  content_chunks=chunks, first_chunk_chars=first_chunk_chars,
                  reasoning_chars=reasoning_chars, content_chars=content_chars,
                  usage=usage, finish_reasons=finish)
    return metrics(result)


def metrics(row):
    usage = row['usage']
    prompt = usage.get('prompt_tokens')
    output = usage.get('completion_tokens')
    reasoning = (usage.get('completion_tokens_details') or {}).get('reasoning_tokens')
    cached = (usage.get('prompt_tokens_details') or {}).get('cached_tokens')
    reasoning_span = (row['first_content_seconds']-row['first_reasoning_seconds']
                      if row.get('first_content_seconds') is not None and row.get('first_reasoning_seconds') is not None else None)
    row.update(prompt_tokens=prompt, completion_tokens=output, reasoning_tokens=reasoning,
               observed_reasoning_seconds=reasoning_span,
               visible_tokens=output-reasoning if output is not None and reasoning is not None else None,
               cached_prompt_tokens=cached,
               # Includes queue/network/TTFT. Always distinguish from server decode speed.
               output_tokens_per_second=output/row['total_seconds'] if output is not None else None,
               # Gateway may buffer/batch chunks; this is the observed stream rate only.
               stream_tokens_per_second=output/row['stream_seconds']
               if output is not None and row['stream_seconds'] > 0 else None,
               input_tokens_per_ttft=prompt/row['ttft_seconds'] if prompt is not None else None,
               output_limited='length' in row['finish_reasons'])
    return row


def prefill_fit(rows):
    groups = {}
    for row in rows:
        if row['phase'] == 'prefill' and row.get('prompt_tokens') is not None:
            groups.setdefault(row['target_input_tokens'], []).append(row)
    points = [(statistics.median(r['prompt_tokens'] for r in runs),
               statistics.median(r['ttft_seconds'] for r in runs)) for _, runs in sorted(groups.items())]
    if len(points) < 3:
        return dict(tokens_per_second=None, reason='need at least three input sizes')
    xs, ys = zip(*points)
    mx, my = statistics.mean(xs), statistics.mean(ys)
    ssx = sum((x-mx)**2 for x in xs)
    slope = sum((x-mx)*(y-my) for x,y in points)/ssx
    intercept = my-slope*mx
    residual = sum((y-intercept-slope*x)**2 for x,y in points)
    variation = sum((y-my)**2 for y in ys)
    return dict(tokens_per_second=1/slope if slope > 0 else None, slope_seconds_per_token=slope,
                intercept_seconds=intercept, r_squared=1-residual/variation if variation else None,
                method='linear fit: median TTFT versus API-reported input tokens; includes gateway effects',
                cache_status='reported hits' if any((r.get('cached_prompt_tokens') or 0)>0 for r in rows)
                else 'not independently verified; unique synthetic payloads', points=points)


def summarize(rows):
    prefill = []
    for size in sorted({r['target_input_tokens'] for r in rows if r['phase']=='prefill'}):
        group = [r for r in rows if r['phase']=='prefill' and r['target_input_tokens']==size]
        prefill.append(dict(target_tokens=size, repeats=len(group),
                            input_tokens=statistics.median(r['prompt_tokens'] for r in group),
                            ttft_seconds=statistics.median(r['ttft_seconds'] for r in group),
                            input_tokens_per_ttft=statistics.median(r['input_tokens_per_ttft'] for r in group)))
    decode = [r for r in rows if r['phase']=='decode']
    reasoning = [r['reasoning_tokens'] for r in decode if r.get('reasoning_tokens') is not None]
    return dict(prefill=prefill, prefill_estimate=prefill_fit(rows), decode=dict(
        repeats=len(decode), reasoning_tokens=reasoning,
        median_reasoning_tokens=statistics.median(reasoning) if reasoning else None,
        median_observed_reasoning_seconds=statistics.median(r['observed_reasoning_seconds'] for r in decode
            if r.get('observed_reasoning_seconds') is not None)
            if any(r.get('observed_reasoning_seconds') is not None for r in decode) else None,
        median_completion_tokens=statistics.median(r['completion_tokens'] for r in decode) if decode else None,
        median_ttft_seconds=statistics.median(r['ttft_seconds'] for r in decode) if decode else None,
        median_end_to_end_tokens_per_second=statistics.median(r['output_tokens_per_second'] for r in decode) if decode else None,
        median_observed_stream_tokens_per_second=statistics.median(r['stream_tokens_per_second'] for r in decode if r['stream_tokens_per_second'] is not None) if any(r['stream_tokens_per_second'] is not None for r in decode) else None,
        output_limited_runs=sum(r['output_limited'] for r in decode)))


def main():
    defaults = json.loads((KIT/'config/backend.defaults.json').read_text())
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url', default=defaults['LLM_BASE_URL'])
    p.add_argument('--model', default=defaults['LLM_MODEL'])
    p.add_argument('--output', type=Path, required=True, help='new JSON path; never overwrite previous results')
    p.add_argument('--repeats', type=int, default=3, choices=range(1,6))
    p.add_argument('--sizes', type=int, nargs='+', default=[512,4096,16384,65536])
    p.add_argument('--timeout', type=float, default=60)
    args = p.parse_args()
    if args.output.exists():
        p.error('output already exists')
    if len(set(args.sizes)) != len(args.sizes) or not all(128 <= n <= 65536 for n in args.sizes):
        p.error('unique input sizes must be within 128..65536 (small benchmark)')
    key = os.environ.get('LLM_API_KEY') or getpass.getpass('API key (hidden, memory only): ')
    if not key:
        p.error('API key required')
    from urllib.parse import urlsplit
    url = urlsplit(args.base_url)
    if url.scheme not in {'http','https'} or not url.hostname or url.username or url.password or url.query or url.fragment:
        p.error('use an http(s) base URL without credentials/query/fragment')
    opener = urllib.request.build_opener(NoRedirect)
    report = dict(timestamp_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        base_url=args.base_url, model=args.model, effort='server default; no reasoning_effort sent',
        repeats=args.repeats, rows=[], summary=None,
        limits=['sequential client measurements; no server compute timers',
                'TTFT includes queue/network/tokenization/first streamed chunk; not pure prefill latency',
                'observed stream rate may be inflated by gateway buffering and multi-token chunks',
                'reasoning tokens from API usage, never estimated from characters; null means unavailable',
                'small synthetic workload; not sustained capacity, long-context quality or production latency'])
    # Unique numeric payloads prevent exact shared-prompt cache reuse. Actual token counts come from usage.
    for repeat in range(args.repeats):
        for size in args.sizes:
            rng = random.Random(90531+repeat*100000+size)
            text = ' '.join(str(rng.randrange(1000,10000)) for _ in range(size//3))
            prompt = f'Ignore the numeric data below. Reply only READY, without explanation.\n<data>{text}</data>\nReply only READY.'
            row = stream_request(opener,args.base_url,args.model,key,prompt,64,args.timeout)
            row.update(phase='prefill',repeat=repeat+1,target_input_tokens=size)
            report['rows'].append(row)
            print(f"prefill {repeat+1}/{args.repeats}: {row['prompt_tokens']} input tokens, TTFT {row['ttft_seconds']:.3f}s",flush=True)
    for repeat in range(args.repeats):
        prompt = (f'Run label {random.Random(2031+repeat).randrange(100000,999999)}. '
                  'Find the number of integer triples (x,y,z) with 0 <= x,y,z <= 20 and x+y+z=30. '
                  'Reason carefully and give a short final answer.')
        row = stream_request(opener,args.base_url,args.model,key,prompt,1024,args.timeout)
        row.update(phase='decode',repeat=repeat+1)
        report['rows'].append(row)
        print(f"decode {repeat+1}/{args.repeats}: {row['completion_tokens']} output / {row['reasoning_tokens']} reasoning tokens, {row['output_tokens_per_second']:.1f} end-to-end tok/s",flush=True)
    report['summary'] = summarize(report['rows'])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    # The report schema contains no request headers, credentials, text or reasoning traces.
    serialized=json.dumps(report,indent=2)
    if key in serialized:
        raise ValueError('credential would appear in report; refusing to write')
    with args.output.open('x') as output:
        output.write(serialized+'\n')
    print('Report:',args.output)
    print(json.dumps(report['summary'],indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError,ValueError,urllib.error.URLError):
        raise SystemExit('backend-probe: request/report failed; raw errors and headers omitted to protect credentials')
