"""GPU scheduling and SSH lifecycle tests, no GPU/server/Claude required."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT / 'bin'))
from _worker_compute import normalize


class ComputeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.mock = self.root / 'mock'
        self.mock.mkdir()
        (self.mock / 'nvidia-smi').write_text('''#!/usr/bin/env python3
import os,sys
from pathlib import Path
if '--query-compute-apps=gpu_uuid,pid' in sys.argv:
 if Path(os.environ['TEST_GPU_BUSY']).exists(): print('GPU-zero, 12345')
else:
 print('0, GPU-zero, 0, 0')
 print('1, GPU-one, 0, 0')
''')
        # Execute the exact transported Python payload, with no SSH service.
        (self.mock / 'ssh').write_text('''#!/usr/bin/env python3
import os,sys,shlex
from pathlib import Path
Path(os.environ['TEST_SSH_ARGS']).write_text(__import__('json').dumps(sys.argv[1:-1]))
a=shlex.split(sys.argv[-1]);os.execvp(a[0],a)
''')
        for p in self.mock.iterdir():
            p.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.mock) + os.pathsep + os.environ['PATH'],
                        XDG_STATE_HOME=str(self.root / 'state'), TEST_GPU_BUSY=str(self.root / 'busy'),
                        TEST_SSH_ARGS=str(self.root / 'ssh-args.json'), PYTHONDONTWRITEBYTECODE='1')
        self.job = dict(transport='local', cwd=str(self.root), command=[sys.executable,'-c','print("job ran")'],
                        verify=[[sys.executable,'-c','assert True']], gpus=[0], gpu_count=1, idle_samples=1,
                        poll_interval=.05, wait_timeout=1, timeout=2, verify_timeout=1, heartbeat_timeout=3)
        self.seq = 0

    def start(self, job=None):
        self.seq += 1
        spec = self.root / ('job%d.json' % self.seq)
        result = self.root / ('result%d.json' % self.seq)
        spec.write_text(json.dumps(job or self.job))
        proc = subprocess.Popen([str(KIT / 'bin/worker-compute-job'), str(spec), '--result', str(result)],
                                env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: proc.kill() if proc.poll() is None else None)
        return proc, result

    def finish(self, process, path, code=0):
        out, err = process.communicate(timeout=12)
        self.assertEqual(process.returncode, code, out + err)
        return json.loads(path.read_text())

    def wait_for(self, path, state):
        end = time.monotonic() + 5
        while time.monotonic() < end:
            if path.exists() and json.loads(path.read_text()).get('state') == state:
                return
            time.sleep(.02)
        self.fail('state not reached: ' + state)

    def test_local_job_records_gpu_logs_and_real_verification(self):
        proc, path = self.start()
        result = self.finish(proc, path)
        self.assertEqual(result['selected_gpu_uuids'], ['GPU-zero'])
        self.assertEqual(result['command_exit_code'], 0)
        self.assertEqual(result['verification_exit_codes'], [0])
        self.assertEqual(Path(result['stdout_path']).read_text().strip(), 'job ran')
        self.assertTrue(result['remote_cleanup_confirmed'])

    def test_busy_gpu_waits_without_running_the_job(self):
        (self.root / 'busy').touch()
        proc, path = self.start(dict(self.job, wait_timeout=.15))
        result = self.finish(proc, path, 1)
        self.assertEqual(result['reason'], 'gpu_wait_timeout')
        self.assertTrue(result['wait_timed_out'])
        self.assertIsNone(result['command_exit_code'])

    def test_gpu_can_become_available_while_waiting(self):
        busy = self.root / 'busy'
        busy.touch()
        proc, path = self.start()
        self.wait_for(path, 'waiting')
        busy.unlink()
        self.assertEqual(self.finish(proc, path)['state'], 'succeeded')

    def test_lock_prevents_two_jobs_claiming_one_idle_gpu(self):
        slow = [sys.executable,'-c','import time;time.sleep(10)']
        first, p1 = self.start(dict(self.job, command=slow, timeout=12))
        self.wait_for(p1, 'running')
        second, p2 = self.start(dict(self.job, wait_timeout=.2))
        self.assertEqual(self.finish(second, p2, 1)['reason'], 'gpu_wait_timeout')
        first.send_signal(signal.SIGTERM)
        self.assertEqual(self.finish(first, p1, 1)['state'], 'cancelled')

    def test_cancel_does_not_stop_another_gpu_job(self):
        slow = [sys.executable,'-c','import time;time.sleep(.8)']
        first, p1 = self.start(dict(self.job, command=slow, gpus=[0]))
        second, p2 = self.start(dict(self.job, command=slow, gpus=[1]))
        self.wait_for(p1, 'running');self.wait_for(p2, 'running')
        first.terminate()
        self.assertEqual(self.finish(first, p1, 1)['state'], 'cancelled')
        self.assertEqual(self.finish(second, p2)['state'], 'succeeded')

    def test_compute_and_verification_timeouts_are_distinct(self):
        slow = [sys.executable,'-c','import time;time.sleep(3)']
        p, f = self.start(dict(self.job, command=slow, timeout=.1))
        self.assertEqual(self.finish(p, f, 1)['reason'], 'compute_timeout')
        p, f = self.start(dict(self.job, verify=[slow], verify_timeout=.1))
        self.assertEqual(self.finish(p, f, 1)['reason'], 'compute_verification_timeout')

    def test_zero_job_exit_does_not_mask_failed_verification(self):
        p, f = self.start(dict(self.job, verify=[[sys.executable,'-c','raise SystemExit(7)']]))
        result = self.finish(p, f, 1)
        self.assertEqual(result['command_exit_code'], 0)
        self.assertEqual(result['verification_exit_codes'], [7])
        self.assertEqual(result['state'], 'failed')

    def test_ssh_uses_exact_host_no_shell_job_interpolation(self):
        code = 'import sys;assert sys.argv[1] == "a;$(touch NEVER)"'
        p, f = self.start(dict(self.job, transport='ssh', ssh_host='lab-fixture', command=[sys.executable,'-c',code,'a;$(touch NEVER)']))
        self.assertEqual(self.finish(p, f)['state'], 'succeeded')
        args = json.loads((self.root / 'ssh-args.json').read_text())
        self.assertIn('BatchMode=yes', args)
        self.assertIn('StrictHostKeyChecking=yes', args)
        self.assertEqual(args[-1], 'lab-fixture')
        self.assertFalse((self.root / 'NEVER').exists())

    def test_source_mismatch_fails_before_gpu_execution(self):
        p, f = self.start(dict(self.job, expected_commit='a'*40))
        self.assertEqual(self.finish(p, f, 1)['reason'], 'source_revision_mismatch')

    def test_repeated_runs_keep_distinct_remote_results(self):
        p, f = self.start();one = self.finish(p, f)
        p, f = self.start();two = self.finish(p, f)
        self.assertNotEqual(one['run_id'], two['run_id'])
        self.assertTrue(Path(one['remote_result_path']).is_file())

    def test_invalid_specs_fail_closed(self):
        for patch in [{'ssh_host':'-oProxyCommand=bad','transport':'ssh'}, {'command':'echo BAD'},
                      {'gpus':[]}, {'gpus':[0,0]}, {'gpu_count':2}, {'poll_interval':0}, {'verify':[]}, {'expected_commit':[]}, {'resource':[]}, {'transport':[]}]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                normalize(dict(self.job, **patch))

    def test_cpu_resource_needs_no_nvidia_tool(self):
        (self.mock/'nvidia-smi').write_text('#!/bin/sh\nexit 99\n')
        p, f = self.start(dict(self.job, resource='cpu'))
        result = self.finish(p, f)
        self.assertEqual(result['selected_gpus'], [])
        self.assertEqual(result['resource'], 'cpu')

    def test_lost_transport_stops_the_job_and_keeps_remote_evidence(self):
        marker = self.root/'child-pid'
        command = [sys.executable,'-c', 'import os,time;from pathlib import Path;Path('+repr(str(marker))+').write_text(str(os.getpid()));time.sleep(30)']
        p, f = self.start(dict(self.job, resource='cpu', transport='ssh', ssh_host='fixture', command=command, timeout=35))
        self.wait_for(f, 'running')
        end=time.monotonic()+3
        while not marker.exists() and time.monotonic()<end: time.sleep(.02)
        self.assertTrue(marker.exists())
        pid=int(marker.read_text())
        p.kill();p.communicate(timeout=3)
        from _worker_compute import identity
        end=time.monotonic()+4
        while identity(pid) and identity(pid)[1] != 'Z' and time.monotonic()<end: time.sleep(.03)
        self.assertTrue(identity(pid) is None or identity(pid)[1]=='Z')
        saved=list((self.root/'state/deepseek-worker/compute').glob('c-*/result.json'))
        self.assertEqual(len(saved),1)
        end=time.monotonic()+3
        while json.loads(saved[0].read_text())['state'] != 'cancelled' and time.monotonic()<end: time.sleep(.03)
        self.assertEqual(json.loads(saved[0].read_text())['state'],'cancelled')

    def test_remote_lease_expires_without_heartbeats(self):
        import uuid
        job=normalize(dict(self.job, resource='cpu', command=[sys.executable,'-c','import time;time.sleep(10)'], timeout=12))
        p=subprocess.Popen([sys.executable,'-u',str(KIT/'bin/_worker_compute.py')],env=self.env,
                           stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        self.addCleanup(lambda:p.kill() if p.poll() is None else None)
        p.stdin.write(json.dumps({'job':job,'run_id':'c-'+uuid.uuid4().hex})+'\n');p.stdin.flush()
        p.wait(timeout=6)
        p.stdin.close();p.stdin=None
        out,err=p.communicate(timeout=2)
        result=json.loads(out.splitlines()[-1])
        self.assertEqual(result['state'],'cancelled',err)
        self.assertEqual(result['reason'],'heartbeat_lost')

    def test_coalesced_events_publish_running_before_the_job_finishes(self):
        (self.mock/'ssh').write_text("""#!/usr/bin/env python3
import hashlib,json,sys,time
request=json.loads(sys.stdin.readline())
base={'run_id':request['run_id'],'spec_digest':hashlib.sha256(json.dumps(request['job'],sort_keys=True).encode()).hexdigest()}
sys.stdout.write(json.dumps(dict(base,state='waiting'))+'\\n'+json.dumps(dict(base,state='running'))+'\\n');sys.stdout.flush()
time.sleep(1.5)
print(json.dumps(dict(base,state='succeeded')),flush=True)
""")
        p,f=self.start(dict(self.job,transport='ssh',ssh_host='fixture',resource='cpu'))
        deadline=time.monotonic()+.8
        seen=False
        while time.monotonic()<deadline:
            if f.exists() and json.loads(f.read_text()).get('state')=='running':
                seen=True;break
            time.sleep(.01)
        self.assertTrue(seen,'second event was buffered until the next server write')
        self.assertIsNone(p.poll())
        self.assertEqual(self.finish(p,f)['state'],'succeeded')

    def test_unknown_gpu_telemetry_does_not_run_job(self):
        (self.mock / 'nvidia-smi').write_text('#!/bin/sh\necho "0, GPU-zero, N/A, N/A"\n')
        p, f = self.start()
        self.assertEqual(self.finish(p, f, 1)['reason'], 'compute_execution_error')


if __name__ == '__main__':
    unittest.main()
