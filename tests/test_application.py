import asyncio
import json
import subprocess
import sys
import unittest

from carets import KeyMsg
from carets.testing import TestProgram
from hypnosis.runtime import demo_source
from hypnosis.terminal import HarnessTerminal, visible


class ApplicationTests(unittest.IsolatedAsyncioTestCase):
    async def test_carets_and_headless_share_the_same_run(self):
        model = HarnessTerminal(lambda: demo_source('same output'))
        async with TestProgram(model) as app:
            model.program = app.program
            await app.send(KeyMsg('enter'))
            await app.wait_for(lambda: model.status == 'completed')
            self.assertEqual(model.output, 'same output')
            await app.resize(18, 4)
            app.assert_fits(18, 4)
        self.assertEqual(app.terminal.restore_count, 1)

    async def test_cancel_remains_responsive_and_close_is_immediate(self):
        entered, closed = asyncio.Event(), []
        async def source():
            try:
                entered.set()
                await asyncio.Event().wait()
                yield 'unreachable'
            finally:
                closed.append(True)
        model = HarnessTerminal(source)
        async with TestProgram(model) as app:
            model.program = app.program
            await app.send(KeyMsg('enter'))
            await entered.wait()
            await app.send(KeyMsg('c'))
            await app.wait_for(lambda: model.status == 'canceled')
            self.assertEqual(closed, [True])

    async def test_control_characters_are_visible_and_tail_is_bounded(self):
        text = '\x1b[2J\x07' + 'a' * 5000
        model = HarnessTerminal(lambda: demo_source(text))
        # Fewer events by selecting an explicitly finite chunk source.
        async def source():
            yield text
        model.factory = source
        async with TestProgram(model) as app:
            model.program = app.program
            await app.send(KeyMsg('enter'))
            await app.wait_for(lambda: model.status == 'completed')
            self.assertLessEqual(len(model.output), 4096)
            self.assertNotIn('\x1b', model.output)
            self.assertNotIn('\x07', visible(text))


class CommandTests(unittest.TestCase):
    def test_actual_cli_uses_one_json_result_and_separate_errors(self):
        result = subprocess.run([sys.executable, '-m', 'hypnosis', 'demo', '--text', 'abc'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['text'], 'abc')
        self.assertEqual(result.stderr, '')
        failed = subprocess.run([sys.executable, '-m', 'hypnosis', 'unknown-command'], capture_output=True, text=True)
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(failed.stdout, '')
        self.assertEqual(json.loads(failed.stderr)['status'], 'failed')
