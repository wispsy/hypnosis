import asyncio
from contextlib import aclosing
import io
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from hypnosis.process import ProcessRun, ProcessLimits, ProtocolError, RunEventDecoder, write_run_stream
from hypnosis.runtime import RunControl, demo_source


def record(kind, sequence, *, text='', code=''):
    return json.dumps(dict(schema='wispsy.run-event/1', run_id='test', sequence=sequence, kind=kind, text=text, code=code))+'\n'


class ProcessTests(unittest.IsolatedAsyncioTestCase):
    async def collect(self, source, *, limits=None, control=None):
        run = ProcessRun([sys.executable, '-u', '-c', source], limits=limits, control=control)
        async with aclosing(run.stream()) as events:
            values = [event async for event in events]
        return run, values

    async def test_first_record_before_exit_fragmented_unicode_and_real_cli(self):
        with TemporaryDirectory() as temporary:
            signal = Path(temporary)/'continue'
            source = 'import sys,time,pathlib\nsys.stdout.write('+repr(record('started', 0)+record('delta', 1, text='é\n界'))+');sys.stdout.flush()\nwhile not pathlib.Path('+repr(str(signal))+').exists(): time.sleep(.005)\nsys.stdout.write('+repr(record('completed', 2))+')'
            run = ProcessRun([sys.executable, '-u', '-c', source])
            async with aclosing(run.stream()) as events:
                self.assertEqual((await anext(events))['kind'], 'started')
                delta = await anext(events)
                self.assertEqual(delta['text'], 'é\n界')
                self.assertFalse(signal.exists())
                signal.touch()
                self.assertEqual([event['kind'] async for event in events], ['completed'])
            self.assertEqual((run.outcome.status, run.outcome.returncode), ('completed', 0))
        encoded = (record('started', 0)+record('delta', 1, text='é\n界')+record('completed', 2)).encode()
        decoder = RunEventDecoder()
        decoded = []
        for byte in encoded:
            decoded.extend(decoder.feed(bytes((byte,))))
        decoder.finish()
        self.assertEqual(decoded[1]['text'], 'é\n界')
        from hypnosis.cli import build_interface
        output = io.StringIO()
        result = await build_interface(output_stream=output).invoke_async(['stream', '--text', 'hello'])
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(json.loads(output.getvalue().splitlines()[-1])['kind'], 'completed')

    async def test_invalid_oversized_exit_and_partial_outcomes(self):
        for raw in ('{}\n', '{"schema":1,"schema":2}\n', '\ufeff{}\n', '\n', record('started', 0).rstrip(), record('started', 1)):
            run, _ = await self.collect('import sys;sys.stdout.write('+repr(raw)+')')
            self.assertFalse(run.outcome.transport_ok)
            self.assertNotEqual(run.outcome.status, 'completed')
        run, _ = await self.collect('import sys;sys.stdout.write("x"*70000+"\\n")')
        self.assertEqual(run.outcome.code, 'record_limit')
        run, _ = await self.collect('import sys;sys.stdout.write('+repr(record('started', 0)+record('delta', 1, text='partial'))+')')
        self.assertEqual(run.outcome.code, 'missing_terminal')
        self.assertTrue(run.outcome.partial_effects)
        for terminal, exit_code, code in (('completed', 1, ''), ('failed', 1, 'source_error'), ('limited', 3, 'output_budget'), ('canceled', 130, '')):
            run, _ = await self.collect('import sys;sys.stdout.write('+repr(record('started', 0)+record(terminal, 1, code=code))+');sys.exit('+str(exit_code)+')')
            self.assertEqual(run.outcome.transport_ok, terminal != 'completed')
            self.assertNotEqual(run.outcome.status, 'completed')
        run, _ = await self.collect('import sys;sys.stdout.write('+repr(record('started', 0)+record('completed', 1)+'{}\n')+')')
        self.assertFalse(run.outcome.transport_ok)

    async def test_downstream_cancel_timeout_stderr_flood_and_owned_reaping(self):
        source = 'import sys,time\nsys.stdout.write('+repr(record('started', 0))+');sys.stdout.flush()\nwhile True:\n sys.stderr.write("PRIVATE"*1000);sys.stderr.flush();time.sleep(.005)'
        run = ProcessRun([sys.executable, '-u', '-c', source], limits=ProcessLimits(stderr_bytes=128))
        async with aclosing(run.stream()) as events:
            await anext(events)
            await asyncio.sleep(.03)
        self.assertEqual(run.outcome.code, 'downstream_closed')
        self.assertIsNotNone(run.outcome.returncode)
        self.assertLessEqual(len(run.stderr_tail), 128)
        self.assertTrue(run.outcome.stderr_truncated)
        self.assertNotIn('PRIVATE', str(run.outcome.receipt()))
        run, _ = await self.collect(source, limits=ProcessLimits(max_seconds=.04, grace_seconds=.02))
        self.assertEqual((run.outcome.status, run.outcome.code), ('limited', 'time_budget'))
        control = RunControl()
        run = ProcessRun([sys.executable, '-u', '-c', source], control=control)
        async with aclosing(run.stream()) as events:
            await anext(events)
            control.cancel()
            _ = [event async for event in events]
        self.assertEqual(run.outcome.status, 'canceled')
        if os.name == 'posix':
            with self.assertRaises(ProcessLookupError):
                os.kill(run.pid, 0)

    async def test_slow_consumer_backpressure_and_ignored_termination(self):
        with TemporaryDirectory() as temporary:
            marker = Path(temporary)/'lead'
            source = ('import sys,pathlib\np=pathlib.Path('+repr(str(marker))+')\n'
                      'sys.stdout.write('+repr(record('started', 0))+');sys.stdout.flush()\n'
                      'for i in range(1,10001):\n'
                      ' sys.stdout.write('+repr(record('delta', 1, text='x'*512))+'.replace("\\\"sequence\\\": 1", "\\\"sequence\\\": "+str(i)));sys.stdout.flush()\n'
                      ' if i%64==0:p.write_text(str(i))\n')
            run = ProcessRun([sys.executable, '-u', '-c', source])
            async with aclosing(run.stream()) as events:
                await anext(events)
                await asyncio.sleep(.04)
                self.assertLess(int(marker.read_text()) if marker.exists() else 0, 10000)
            self.assertIsNotNone(run.outcome.returncode)
        if os.name == 'posix':
            source = 'import signal,sys,time\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\nsys.stdout.write('+repr(record('started', 0))+');sys.stdout.flush()\nwhile True:time.sleep(.01)'
            run, events = await self.collect(source, limits=ProcessLimits(max_seconds=.1, grace_seconds=.02))
            self.assertEqual(run.outcome.status, 'limited')
            self.assertEqual(run.outcome.returncode, -9)
