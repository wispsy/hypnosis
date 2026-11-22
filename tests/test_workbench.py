import asyncio
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

AVAILABLE = all(importlib.util.find_spec(name) for name in ('hidden_moves', 'hidden_moves_workspace', 'parse_md', 'func_seq', 'backpack_store', 'headless_spreadsheets'))


@unittest.skipUnless(AVAILABLE, 'application extra required')
class WorkbenchTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_services_and_private_backpack_receipts_in_fresh_process(self):
        from hypnosis.application import run_application_demo
        with TemporaryDirectory() as temporary:
            database = Path(temporary)/'receipts.db'
            report = await run_application_demo(database=database)
            self.assertEqual(report.status, 'completed', report.receipt())
            self.assertEqual([a['passed'] for a in report.verification['attempts']], [False, True])
            self.assertEqual(len(report.tools), 2)
            self.assertEqual(report.trials.recommendation, 'candidate')
            raw = json.dumps(report.receipt())
            for private in ('task.md', 'answer.txt', 'Compute 2 + 3', '"answer":'):
                self.assertNotIn(private, raw)
            code = 'from hypnosis.harness_records import HarnessLedger;import sys;\nwith HarnessLedger(sys.argv[1]) as l: print(len(l.recall("application",kind="application")),len(l.recall("application",kind="trial")))'
            result = await asyncio.to_thread(subprocess.run, [sys.executable, '-I', '-c', code, str(database)], capture_output=True, text=True, timeout=5)
            self.assertEqual((result.returncode, result.stdout.strip()), (0, '1 1'), result.stderr)

    async def test_ui_resize_focus_modal_explicit_promotion_and_owned_cleanup(self):
        from carets import KeyMsg
        from carets.testing import TestProgram
        from hypnosis.application import run_application_demo
        from hypnosis.workbench import Workbench
        model = Workbench(run_application_demo)
        async with TestProgram(model) as app:
            model.program = app.program
            await app.send(KeyMsg('enter'))
            for _ in range(200):
                await asyncio.sleep(.005)
                await app.settle()
                if model.status != 'running':
                    break
            self.assertEqual(model.status, 'completed', model.report.receipt() if model.report else model.code)
            for index in range(1, 8):
                await app.send(KeyMsg(str(index)))
                await app.resize(22, 6)
                app.assert_fits(22, 6)
            await app.send(KeyMsg('p'))
            self.assertTrue(model.modal)
            self.assertEqual(model.focus.active_scope, 'promotion')
            await app.send(KeyMsg('enter'))
            self.assertIsNone(model.promotion)
            await app.send(KeyMsg('p'), KeyMsg('tab'), KeyMsg('enter'))
            self.assertEqual(model.promotion.config_id, 'candidate')
            self.assertFalse(model.modal)
        self.assertEqual(app.terminal.restore_count, 1)

    async def test_cancel_and_quit_settle_owned_worker_before_restoration(self):
        from carets import KeyMsg
        from carets.testing import TestProgram
        from hypnosis.application import run_application_demo
        from hypnosis.workbench import Workbench
        report = await run_application_demo()
        closed = []
        async def factory(*, observer, stop):
            try:
                while not stop():
                    await asyncio.sleep(.005)
                return replace(report, status='canceled')
            finally:
                closed.append(True)
        model = Workbench(factory)
        async with TestProgram(model) as app:
            model.program = app.program
            await app.send(KeyMsg('enter'), KeyMsg('q'))
            await asyncio.wait_for(app.task, 5)
            self.assertEqual(model.status, 'canceled')
            self.assertEqual(closed, [True])
        self.assertEqual(app.terminal.restore_count, 1)

    async def test_direct_signal_shutdown_reports_joined_worker_outcome(self):
        from threading import Event
        from carets import TerminalSession
        from carets.testing import FakeTerminal
        from hypnosis.application import run_application_demo
        from hypnosis.workbench import run_workbench
        report = await run_application_demo()
        started, settled = Event(), Event()
        async def factory(*, observer, stop):
            started.set()
            try:
                while not stop():
                    await asyncio.sleep(.005)
                return replace(report, status='canceled')
            finally:
                settled.set()
        terminal = FakeTerminal()
        session = TerminalSession(terminal.input, terminal.output, backend=terminal)
        with patch('hypnosis.workbench.TerminalSession', return_value=session):
            task = asyncio.create_task(run_workbench(messages=[], input_stream=terminal.input,
                output_stream=terminal.output, factory=factory))
            for _ in range(200):
                if started.is_set() and 'terminate' in terminal.handlers:
                    break
                await asyncio.sleep(.005)
            self.assertTrue(started.is_set())
            terminal.handlers['terminate']()
            outcome = await asyncio.wait_for(task, 5)
        self.assertEqual(outcome['status'], 'canceled')
        self.assertTrue(settled.is_set())
        self.assertEqual(terminal.restore_count, 1)

    @unittest.skipUnless(importlib.util.find_spec('thoughtformula'), 'native models profile required')
    async def test_explicit_native_artifact_is_loaded_without_weight_training(self):
        from thoughtformula import BPETokenizer, TrainingConfig, TrainingState, save_training_checkpoint
        from thoughtform.recipes import HERO, initialize
        from thoughtform.artifacts import artifact_metadata, publish_artifact
        from hypnosis.application import run_application_demo
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            tokenizer = BPETokenizer()
            tokenizer.train(''.join(chr(i) for i in range(32, 127))+'\n', max_merges=0)
            recipe = replace(HERO, width=8, layers=1, heads=2, kv_heads=1, experts=1, hidden=8, lora_rank=2)
            model = initialize(recipe, tokenizer)
            checkpoint = root/'model.tft'
            save_training_checkpoint(checkpoint, model, tokenizer, TrainingConfig(block_size=4), TrainingState(), metadata=artifact_metadata(recipe, 'a'*64))
            artifact = root/'artifact.json'
            publish_artifact(artifact, checkpoint, recipe, corpus_sha256='a'*64)
            before = checkpoint.read_bytes()
            report = await run_application_demo(artifact=str(artifact), prompt='1')
            self.assertIn(report.status, ('completed', 'failed', 'limited'))
            self.assertTrue(report.verification['attempts'])
            self.assertEqual(report.verification['attempts'][0]['verification_code'], 'syntax_only')
            self.assertEqual(checkpoint.read_bytes(), before)


@unittest.skipUnless(AVAILABLE and os.name == 'posix', 'application native POSIX profile required')
class NativeWorkbenchTests(unittest.TestCase):
    def test_actual_buffered_key_quits_and_restores_raw_terminal(self):
        import pty
        import select
        import termios
        master, slave = pty.openpty()
        original = termios.tcgetattr(slave)
        process = subprocess.Popen([sys.executable, '-I', str(Path(__file__).with_name('workbench_native_worker.py'))],
            stdin=slave, stdout=subprocess.PIPE, stderr=slave)
        try:
            self.assertTrue(select.select([process.stdout], [], [], 8)[0], 'Workbench did not start')
            self.assertEqual(process.stdout.readline().strip(), b'READY')
            os.write(master, b'q')
            output, _ = process.communicate(timeout=8)
            self.assertEqual(process.returncode, 0, output)
            self.assertIn(b'DONE:canceled', output)
            restored = termios.tcgetattr(slave)
            if sys.platform == 'darwin':
                # Match Carets' native test: Darwin's PENDIN is kernel state
                # set while restoring canonical input, not a retained raw mode.
                restored[3] &= ~termios.PENDIN
                original[3] &= ~termios.PENDIN
            self.assertEqual(restored, original)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
            os.close(master)
            os.close(slave)
