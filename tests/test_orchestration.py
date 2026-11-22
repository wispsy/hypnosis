import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from hypnosis.orchestration import RoleJob, JobLimits, coordinate
from hypnosis.runtime import RunControl

try:
    import func_seq
except ImportError:
    func_seq = None

SHA = 'a'*64


@unittest.skipUnless(func_seq, 'workflow extra required')
class OrchestrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_admission_concurrency_serial_cache_and_shared_budgets(self):
        active, peak = 0, 0
        async def job(control):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(.005)
            active -= 1
            return {'private': 'VALUE'}
        jobs = [RoleJob(str(i), 'worker', SHA, job) for i in range(4)]
        report = await coordinate(jobs, run_id='sequential', config_sha256=SHA)
        self.assertEqual((peak, report.status), (1, 'completed'))
        self.assertNotIn('VALUE', str(report.receipt()))
        peak = 0
        report = await coordinate(jobs, run_id='shared', config_sha256=SHA, limits=JobLimits(max_concurrency=3))
        self.assertEqual(peak, 1)
        jobs = [RoleJob(str(i), 'worker', SHA, job, resource='isolated-'+str(i)) for i in range(4)]
        peak = 0
        report = await coordinate(jobs, run_id='parallel', config_sha256=SHA, limits=JobLimits(max_concurrency=2, max_units=3))
        self.assertEqual(peak, 2)
        self.assertEqual(report.reserved_units, 3)
        self.assertEqual(report.outcomes[-1]['code'], 'unit_budget')
        report = await coordinate(jobs[:2], run_id='output', config_sha256=SHA, limits=JobLimits(max_output_bytes=1))
        self.assertEqual(report.output_bytes, 0)
        self.assertEqual(report.status, 'limited')

    async def test_dag_failure_cancellation_and_invalid_graph_before_effects(self):
        async def broken(control):
            raise RuntimeError('PRIVATE')
        jobs = [RoleJob('a', 'writer', SHA, broken), RoleJob('b', 'reviewer', SHA, lambda c: self.fail(), dependencies=('a',))]
        report = await coordinate(jobs, run_id='failure', config_sha256=SHA)
        self.assertEqual([e['status'] for e in report.outcomes], ['failed', 'blocked'])
        self.assertNotIn('PRIVATE', str(report.receipt()))
        with self.assertRaises(ValueError):
            await coordinate([RoleJob('a', 'writer', SHA, broken, dependencies=('a',))], run_id='cycle', config_sha256=SHA)
        control = RunControl()
        settled = []
        async def slow(c):
            try:
                await asyncio.sleep(5)
            finally:
                settled.append(True)
        task = asyncio.create_task(coordinate([RoleJob('a', 'worker', SHA, slow)], run_id='cancel', config_sha256=SHA, control=control))
        await asyncio.sleep(.01)
        control.cancel()
        report = await task
        self.assertEqual(report.status, 'canceled')
        self.assertEqual(settled, [True])

    async def test_completed_checkpoint_reopens_without_replaying_and_identity_changes_refused(self):
        calls = []
        def job(control):
            calls.append('called')
            return {'ok': True}
        with TemporaryDirectory() as temporary:
            checkpoint = Path(temporary)/'jobs.json'
            jobs = [RoleJob('a', 'worker', SHA, job)]
            first = await coordinate(jobs, run_id='persist', config_sha256=SHA, checkpoint=checkpoint)
            second = await coordinate(jobs, run_id='persist', config_sha256=SHA, checkpoint=checkpoint)
            self.assertEqual(first.receipt(), second.receipt())
            self.assertEqual(calls, ['called'])
            with self.assertRaises(func_seq.DefinitionMismatchError):
                await coordinate(jobs, run_id='persist', config_sha256='b'*64, checkpoint=checkpoint)
