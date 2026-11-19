import asyncio
from contextlib import aclosing
import threading
import unittest

from hypnosis import Harness, RunControl, RunLimits
from hypnosis.execution import from_sync
from hypnosis.runtime import demo_source, run_demo


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def events(self, factory, **options):
        return [event async for event in Harness(options.pop('limits', None)).stream(factory, run_id='test', **options)]

    async def test_completion_is_incremental_ordered_and_bounded(self):
        observed = asyncio.Event()
        async def source():
            yield 'first'
            await observed.wait()
            yield 'second'
        values = []
        async for event in Harness().stream(source, run_id='test'):
            values.append(event)
            if event.kind == 'delta':
                observed.set()
        self.assertEqual([e.kind for e in values], ['started', 'delta', 'delta', 'completed'])
        self.assertEqual([e.sequence for e in values], list(range(4)))
        self.assertEqual(await run_demo('abc'), {'schema': 1, 'run_id': 'demo', 'status': 'completed', 'text': 'abc', 'events': 5})

    async def test_output_event_and_time_budgets_are_explicit(self):
        for limits, code in [(RunLimits(max_output_bytes=1), 'output_budget'),
                             (RunLimits(max_events=2), 'event_budget')]:
            events = await self.events(lambda: demo_source('é'), limits=limits)
            self.assertEqual((events[-1].kind, events[-1].code), ('limited', code))
            self.assertLessEqual(len(events), limits.max_events)
            self.assertEqual(events[-1].sequence, len(events) - 1)
        closed = []
        async def blocked():
            try:
                await asyncio.Event().wait()
                yield 'unreachable'
            finally:
                closed.append(True)
        events = await self.events(blocked, limits=RunLimits(max_seconds=0.01))
        self.assertEqual(events[-1].code, 'time_budget')
        self.assertEqual(closed, [True])

    async def test_cancellation_while_source_is_blocked_closes_before_outcome(self):
        control, entered, closed = RunControl(), asyncio.Event(), []
        async def source():
            try:
                entered.set()
                await asyncio.Event().wait()
                yield 'unreachable'
            finally:
                closed.append(True)
        task = asyncio.create_task(self.events(source, control=control))
        await entered.wait()
        control.cancel()
        events = await asyncio.wait_for(task, 1)
        self.assertEqual(events[-1].kind, 'canceled')
        self.assertEqual(closed, [True])

    async def test_consumer_task_cancellation_propagates_without_terminal_success(self):
        entered, closed, events = asyncio.Event(), [], []
        async def source():
            try:
                entered.set()
                await asyncio.Event().wait()
                yield 'unreachable'
            finally:
                closed.append(True)
        async def consume():
            async for event in Harness().stream(source, run_id='test'):
                events.append(event)
        task = asyncio.create_task(consume())
        await entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(closed, [True])
        self.assertEqual([e.kind for e in events], ['started'])

    async def test_failures_are_structural_and_close_source(self):
        for value in (object(), 'secret exception'):
            closed = []
            async def source():
                try:
                    if isinstance(value, str):
                        raise RuntimeError(value)
                    yield value
                finally:
                    closed.append(True)
            events = await self.events(source)
            self.assertEqual((events[-1].kind, events[-1].code), ('failed', 'source_error'))
            self.assertNotIn('secret', str([event.as_dict() for event in events]))
            self.assertEqual(closed, [True])

    async def test_sync_source_uses_one_worker_and_cooperative_close(self):
        threads, closed = [], []
        def source():
            try:
                threads.append(threading.get_ident())
                yield 'first'
                threads.append(threading.get_ident())
                yield 'second'
            finally:
                closed.append(threading.get_ident())
        async with aclosing(from_sync(source)) as stream:
            self.assertEqual(await anext(stream), 'first')
        self.assertEqual(threads, closed)
        self.assertNotEqual(threads[0], threading.get_ident())

    async def test_sync_source_cancel_waits_for_inflight_next_before_close(self):
        entered, release = threading.Event(), threading.Event()
        closed = []
        def source():
            try:
                entered.set()
                release.wait(1)
                yield 'late'
            finally:
                closed.append(True)
        task = asyncio.create_task(self.events(lambda: from_sync(source)))
        await asyncio.to_thread(entered.wait, 1)
        task.cancel()
        release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(closed, [True])

    async def test_failing_sync_iterator_is_closed_on_its_worker(self):
        calls = []
        class Source:
            def __iter__(self): return self
            def __next__(self):
                calls.append(('next', threading.get_ident()))
                raise RuntimeError('source failure')
            def close(self):
                calls.append(('close', threading.get_ident()))
        with self.assertRaisesRegex(RuntimeError, 'source failure'):
            async for _value in from_sync(Source):
                self.fail('A failed source cannot yield a value')
        self.assertEqual([name for name, _thread in calls], ['next', 'close'])
        self.assertEqual(calls[0][1], calls[1][1])

    def test_invalid_limits(self):
        for kwargs in ({'max_events': True}, {'max_output_bytes': -1}, {'max_seconds': float('nan')}):
            with self.assertRaises(ValueError):
                RunLimits(**kwargs)
