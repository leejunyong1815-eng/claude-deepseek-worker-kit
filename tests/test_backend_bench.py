"""Benchmark arithmetic and streaming parsing without a model or network."""
import io
import importlib.util
import itertools
import json
from pathlib import Path
import unittest
from unittest.mock import patch

KIT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('backend_bench', KIT/'bench/backend_probe.py')
bench = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bench)


class BenchmarkTests(unittest.TestCase):
    def row(self, **values):
        row = dict(usage={'prompt_tokens':1000,'completion_tokens':100,
                          'completion_tokens_details':{'reasoning_tokens':60}},
                   total_seconds=2.0, stream_seconds=0.5, ttft_seconds=1.5, finish_reasons=['stop'])
        row.update(values)
        return bench.metrics(row)

    def test_reported_reasoning_tokens_and_distinct_rate_denominators(self):
        row = self.row()
        self.assertEqual(row['reasoning_tokens'],60)
        self.assertEqual(row['visible_tokens'],40)
        self.assertEqual(row['output_tokens_per_second'],50)
        self.assertEqual(row['stream_tokens_per_second'],200)
        self.assertFalse(row['output_limited'])

    def test_missing_reasoning_data_is_unknown_and_length_cap_is_explicit(self):
        row = self.row(usage={'prompt_tokens':10,'completion_tokens':20},
                       stream_seconds=0,finish_reasons=['length'])
        self.assertIsNone(row['reasoning_tokens'])
        self.assertIsNone(row['visible_tokens'])
        self.assertIsNone(row['stream_tokens_per_second'])
        self.assertTrue(row['output_limited'])

    def test_prefill_slope_subtracts_fixed_latency_instead_of_claiming_ttft_is_pure_prefill(self):
        rows=[]
        for size in (1000,4000,16000):
            for repeat in range(3):
                rows.append(dict(phase='prefill',target_input_tokens=size,prompt_tokens=size,
                                 ttft_seconds=0.2+size/10000,cached_prompt_tokens=None))
        fit=bench.prefill_fit(rows)
        self.assertAlmostEqual(fit['tokens_per_second'],10000)
        self.assertAlmostEqual(fit['intercept_seconds'],0.2)
        self.assertAlmostEqual(fit['r_squared'],1)
        self.assertIsNone(bench.prefill_fit(rows[:2])['tokens_per_second'])
        for row in rows:row['ttft_seconds']=1
        self.assertIsNone(bench.prefill_fit(rows)['tokens_per_second'])

    def test_sse_parser_preserves_usage_and_measures_first_reasoning_before_answer(self):
        payloads=[{'choices':[{'delta':{'role':'assistant'}}]},
                  {'choices':[{'delta':{'reasoning_content':'reason'}}]},
                  {'choices':[{'delta':{'content':'answer'},'finish_reason':'stop'}]},
                  {'choices':[],'usage':{'prompt_tokens':42,'completion_tokens':9,
                                        'completion_tokens_details':{'reasoning_tokens':5}}}]
        stream=b''.join(b'data: '+json.dumps(x).encode()+b'\n\n' for x in payloads)+b'data: [DONE]\n'
        class Opener:
            def open(inner,req,timeout):return io.BytesIO(stream)
        with patch.object(bench.time,'perf_counter',side_effect=itertools.count(0,0.05)):
            row=bench.stream_request(Opener(),'http://unused.invalid','fixture-model','fixture-key','hello',32,60)
        self.assertEqual(row['prompt_tokens'],42)
        self.assertEqual(row['reasoning_tokens'],5)
        self.assertEqual(row['reasoning_chars'],6)
        self.assertEqual(row['content_chunks'],2)
        self.assertLess(row['first_reasoning_seconds'],row['first_content_seconds'])
        self.assertAlmostEqual(row['observed_reasoning_seconds'],row['first_content_seconds']-row['first_reasoning_seconds'])

    def test_incomplete_sse_never_becomes_a_measurement(self):
        class Opener:
            def open(inner,req,timeout):
                return io.BytesIO(b'data: {"choices":[{"delta":{"content":"partial"}}]}\n')
        with self.assertRaisesRegex(ValueError,'incomplete'):
            bench.stream_request(Opener(),'http://unused.invalid','fixture-model','fixture-key','hello',32,60)


if __name__=='__main__':unittest.main()
