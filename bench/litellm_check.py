#!/usr/bin/env python3
"""Explicit small live compatibility checks; saves metadata, never keys or thinking."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import time
import urllib.error
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError('redirect refused')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base-url', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--family', action='append', choices=['deepseek-v4.1-flash','qwen3.8-flash-next'])
    p.add_argument('--check', action='append', choices=['messages_tool_continuation','messages_sse','messages_effort','chat_tool_continuation','chat_sse','responses_text'])
    args = p.parse_args()
    key = os.environ.get('LLM_API_KEY', '')
    opener = urllib.request.build_opener(NoRedirect)
    results = []
    def request(path, body):
        headers = {'Content-Type':'application/json','anthropic-version':'2023-06-01'}
        if key:
            headers.update(Authorization='Bearer ' + key, **{'x-api-key':key})
        req = urllib.request.Request(args.base_url.rstrip('/') + path, data=json.dumps(body).encode(), headers=headers)
        with opener.open(req, timeout=90) as r:
            raw = r.read(8 * 1024 * 1024).decode()
            return raw if body.get('stream') else json.loads(raw)
    def check(model, kind, operation):
        if args.check and kind not in args.check:
            return
        start = time.monotonic()
        row = {'model':model,'check':kind}
        try:
            detail = operation()
            row.update(passed=True, **detail)
        except urllib.error.HTTPError as e:
            row.update(passed=False, http_status=e.code)
        except (ValueError, OSError, KeyError, IndexError, TypeError, AssertionError):
            row.update(passed=False, error='invalid_or_incomplete_response')
        row['duration_seconds'] = round(time.monotonic() - start, 3)
        results.append(row)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps({'base_url':args.base_url,'checked_at':datetime.now(timezone.utc).isoformat(),
                                          'authentication':'api_key' if key else 'none','checks':results}, indent=2) + '\n')
        print(json.dumps(row), flush=True)
    for family in (args.family or ['deepseek-v4.1-flash','qwen3.8-flash-next']):
        def messages_tool():
            common = {'model':family, 'max_tokens':2048}
            tools = [{'name':'lab_token','description':'Return the test token. Must be called before answering.',
                      'input_schema':{'type':'object','properties':{'label':{'type':'string'}},'required':['label']}}]
            turns = [{'role':'user','content':'Call lab_token with label probe. Then repeat its returned token exactly.'}]
            first = request('/v1/messages', dict(common, messages=turns, tools=tools))
            calls = [b for b in first['content'] if b.get('type') == 'tool_use']
            assert calls and all(c['name']=='lab_token' for c in calls)
            token = secrets.token_hex(10)
            turns += [{'role':'assistant','content':first['content']}, {'role':'user','content':[
                {'type':'tool_result','tool_use_id':c['id'],'content':token} for c in calls]}]
            final = request('/v1/messages', dict(common, messages=turns, tools=tools))
            assert final.get('stop_reason')=='end_turn'
            assert token in ''.join(b.get('text','') for b in final['content'])
            return {'tool_calls':len(calls),'continuation_verified':True,'usage':final.get('usage',{})}
        check(family, 'messages_tool_continuation', messages_tool)
        def messages_stream():
            raw = request('/v1/messages', {'model':family,'max_tokens':512,'stream':True,
                           'messages':[{'role':'user','content':'Reply with exactly PONG.'}]})
            events = [json.loads(line[6:]) for line in raw.splitlines() if line.startswith('data: ') and line[6:]!='[DONE]']
            assert any(e.get('type')=='message_start' for e in events)
            assert any(e.get('type')=='message_stop' for e in events)
            text = ''.join(e.get('delta',{}).get('text','') for e in events)
            assert 'PONG' in text
            return {'stream_completed':True}
        check(family, 'messages_sse', messages_stream)
        def effort():
            r = request('/v1/messages', {'model':family,'max_tokens':2048,
                        'thinking':{'type':'enabled','budget_tokens':1024},'output_config':{'effort':'max'},
                        'messages':[{'role':'user','content':'Reply with exactly LAB_EFFORT_OK.'}]})
            assert 'LAB_EFFORT_OK' in ''.join(b.get('text','') for b in r['content'])
            return {'effort_request_accepted':True,'thinking_block_observed':any(b.get('type')=='thinking' for b in r['content']),
                    'honored_effort_proven':False,'usage':r.get('usage',{})}
        check(family, 'messages_effort', effort)
        model = family + '-oai'
        def chat_tool():
            tools = [{'type':'function','function':{'name':'lab_token','description':'Return the test token.',
                      'parameters':{'type':'object','properties':{'label':{'type':'string'}},'required':['label']}}}]
            turns = [{'role':'user','content':'Call lab_token with label probe. Then repeat its returned token exactly.'}]
            first = request('/v1/chat/completions', {'model':model,'max_tokens':2048,'messages':turns,'tools':tools})
            message = first['choices'][0]['message']
            calls = message.get('tool_calls',[])
            assert calls and all(c['function']['name']=='lab_token' for c in calls)
            token = secrets.token_hex(10)
            turns += [message] + [{'role':'tool','tool_call_id':c['id'],'content':token} for c in calls]
            final = request('/v1/chat/completions', {'model':model,'max_tokens':2048,'messages':turns,'tools':tools})
            assert token in (final['choices'][0]['message'].get('content') or '')
            return {'tool_calls':len(calls),'continuation_verified':True,'usage':final.get('usage',{})}
        check(model, 'chat_tool_continuation', chat_tool)
        def chat_stream():
            raw = request('/v1/chat/completions', {'model':model,'max_tokens':512,'stream':True,
                           'messages':[{'role':'user','content':'Reply with exactly PONG.'}]})
            assert 'data: [DONE]' in raw
            events = [json.loads(line[6:]) for line in raw.splitlines() if line.startswith('data: ') and line[6:]!='[DONE]']
            text = ''.join(c.get('delta',{}).get('content') or '' for e in events for c in e.get('choices',[]))
            assert 'PONG' in text
            return {'stream_completed':True}
        check(model, 'chat_sse', chat_stream)
        def responses():
            r = request('/v1/responses', {'model':model,'max_output_tokens':512,'input':'Reply with exactly PONG.'})
            text = ''.join(c.get('text','') for item in r.get('output',[]) for c in item.get('content',[]))
            assert r.get('status')=='completed' and 'PONG' in text
            return {'completed':True,'usage':r.get('usage',{})}
        check(model, 'responses_text', responses)
    return int(any(not r['passed'] for r in results))


if __name__ == '__main__':
    raise SystemExit(main())
