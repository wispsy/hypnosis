import asyncio
from contextlib import aclosing
from threading import Event,get_ident
import unittest

from hypnosis.execution import job_progress


class JobExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def test_bounded_worker_progress_and_close_joins_cooperative_job(self):
        closed=Event();threads=[];main=get_ident()
        def job(emit,stop):
            try:
                threads.append(get_ident())
                for index in range(1000):
                    if stop(): return {'status':'paused'}
                    emit({'step':index})
                return {'status':'completed'}
            finally: closed.set()
        async with aclosing(job_progress(job)) as source:
            first=await anext(source)
            self.assertIn('step',first)
        self.assertTrue(closed.is_set())
        self.assertNotEqual(threads,[main])

    async def test_worker_failure_is_propagated_after_progress(self):
        def job(emit,stop):
            emit({'step':1});raise ValueError('fixture')
        with self.assertRaises(ValueError):
            async for _value in job_progress(job): pass
