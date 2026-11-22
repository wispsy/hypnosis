"""Carets application shell over the same trusted application service entrypoint."""
import asyncio
from contextlib import aclosing
from dataclasses import dataclass, replace
import json
import sys
from threading import Event

from carets import (AppShell, CellDiffRenderer, Command, CommandErrorMsg, FocusManager,
                    KeyMsg, Msg, Program, ShellCommand, TerminalOptions, TerminalSession, WindowSizeMsg)
from carets.components import ComponentState, TableModel

from .application import run_application_demo
from .execution import job_progress
from .terminal import visible
from .tools import digest

SECTIONS = ('Jobs', 'Tools', 'Context', 'Verification', 'Trials', 'Checkpoints', 'Output')


@dataclass(frozen=True)
class ProgressMsg(Msg):
    value: dict


def snapshot(name, columns, rows, generation=0):
    from headless_spreadsheets import Cell, SourceColumn, SourceRow, TableSnapshot
    return TableSnapshot(name, '1', tuple(SourceColumn(key, key) for key in columns),
        tuple(SourceRow('row-'+digest([name, index])[:24], None, tuple(Cell(value) for value in row),
                        tuple('receipt' for _ in columns)) for index, row in enumerate(rows[:128])), generation=generation)


class Workbench:
    def __init__(self, factory, *, database='', run_id='application', exit_on_completion=False, checkpoints=()):
        self.factory, self.database, self.run_id = factory, database, run_id
        self.exit_on_completion = exit_on_completion
        self.program = None
        self.width, self.height = 80, 24
        self.section = 0
        self.status = 'ready'
        self.code = ''
        self.events = []
        self.report = None
        self.promotion = None
        self.modal = False
        self.exit_requested = False
        self.cancel_requested = Event()
        self.shell = AppShell('Hypnosis')
        self.focus = FocusManager()
        self.focus.register('navigation')
        self.focus.register('details', read_only=True)
        self.focus.add_scope('promotion')
        self.focus.register('cancel', scope='promotion')
        self.focus.register('confirm', scope='promotion')
        self.tables = {}
        self.checkpoints = tuple(checkpoints)[:128]
        self._worker_result = {}

    def settle_outcome(self):
        """Read joined worker state even when shutdown stopped message delivery."""
        report = self._worker_result.get('report')
        if report is not None:
            self.report, self.status = report, report.status
        elif self.status == 'running':
            self.status = 'failed' if 'error' in self._worker_result else 'canceled'
            if 'error' in self._worker_result:
                self.code = 'command_error'

    def start(self):
        if self.status != 'ready':
            return None
        self.status = 'running'
        def job(observer, stop):
            try:
                report = asyncio.run(self.factory(observer=observer,
                    stop=lambda: stop() or self.cancel_requested.is_set()))
            except BaseException as error:
                self._worker_result['error'] = type(error).__name__
                raise
            self._worker_result['report'] = report
            return {'status': report.status}
        async def produce():
            async with aclosing(job_progress(job)) as events:
                async for value in events:
                    yield ProgressMsg(json.loads(value))
        return Command.stream(produce)

    def _make_tables(self):
        if self.report is None:
            return
        report = self.report
        data = {
            0: (('job', 'role', 'status'), [(r['id'], r['role'], r['status']) for r in report.jobs['outcomes']]),
            1: (('tool', 'status', 'effect'), [(r['name'], r['status'], r['effect']) for r in report.tools]),
            2: (('kind', 'trusted', 'source'), [(r['kind'], r['trusted'], r['source_sha256'][:16]) for r in report.context.get('sources', [])]),
            3: (('attempt', 'passed', 'code'), [(r['attempt'], r['passed'], r.get('verification_code', '')) for r in report.verification.get('attempts', [])]),
            4: (('config', 'validation', 'heldout', 'eligible'), [(r['config_id'], r['validation_passed'], r['heldout_passed'], r['eligible']) for r in report.trials.trials] if report.trials else []),
            5: (('model', 'step', 'profile', 'checkpoint'), [(r['model_id'], r['steps'], r['profile'], r['checkpoint_sha256'][:16]) for r in self.checkpoints]),
        }
        for index, (columns, rows) in data.items():
            self.tables[index] = TableModel(snapshot('section-'+str(index), columns, rows),
                state=ComponentState('details', SECTIONS[index], focused=True, read_only=True))

    def _dismiss(self):
        self.modal = False
        self.focus.dismiss()

    def update(self, message):
        if isinstance(message, WindowSizeMsg):
            self.width, self.height = max(0, min(message.width, 4096)), max(0, min(message.height, 1024))
        elif isinstance(message, ProgressMsg):
            value = message.value
            self.events.append({k: v for k, v in value.items() if k in ('kind', 'id', 'role', 'status', 'code', 'attempt', 'passed', 'config_id')})
            self.events = self.events[-64:]
            if value.get('kind') == 'outcome':
                self.report = self._worker_result.get('report')
                self.status = value['status']
                self._make_tables()
                if self.program and (self.exit_requested or self.exit_on_completion):
                    self.program.stop()
        elif isinstance(message, CommandErrorMsg):
            self.status, self.code = 'failed', 'command_error'
            if self.program and (self.exit_requested or self.exit_on_completion):
                self.program.stop()
        elif isinstance(message, KeyMsg) and message.action != 'release':
            if self.modal:
                if message.key == 'escape':
                    self._dismiss()
                elif message.key == 'enter':
                    if self.focus.focused == 'confirm':
                        try:
                            trial = self.report.trials
                            self.promotion = trial.promote(trial.recommendation, expected_report_sha256=digest(trial.receipt()))
                            if self.database:
                                from .harness_records import HarnessLedger
                                with HarnessLedger(self.database) as ledger:
                                    ledger.record_report(self.run_id, self.promotion)
                        except (ValueError, OSError):
                            self.code = 'promotion_failed'
                    self._dismiss()
                else:
                    self.focus.route(message)
                return None
            if message.key in ('q', 'ctrl-c') or (message.key == 'c' and 'ctrl' in message.modifiers):
                if self.status == 'running':
                    self.exit_requested = True
                    self.cancel_requested.set()
                elif self.program:
                    self.program.stop()
            elif message.key == 'c' and self.status == 'running':
                self.cancel_requested.set()
            elif message.key == 'enter' and self.status == 'ready':
                return self.start()
            elif message.key == 'tab' or message.key in ('backtab', 'shift-tab'):
                self.focus.route(message)
            elif message.key in tuple(str(i) for i in range(1, len(SECTIONS)+1)):
                self.section = int(message.key)-1
            elif message.key == 'p' and self.report and self.report.trials and self.report.trials.recommendation:
                self.modal = True
                self.focus.activate('promotion', modal=True)
            elif message.key in ('up', 'down') and self.focus.focused == 'navigation':
                self.section = (self.section+(-1 if message.key == 'up' else 1)) % len(SECTIONS)
            elif self.section in self.tables:
                self.tables[self.section] = self.tables[self.section].update(message)

    def view(self):
        commands = (ShellCommand('quit', 'q', 'quit'), ShellCommand('cancel', 'c', 'cancel', self.status == 'running'),
                    ShellCommand('promote', 'p', 'review promotion', bool(self.report and self.report.trials and self.report.trials.recommendation)))
        empty = self.shell.frame(self.width, self.height, navigation=SECTIONS, selected=self.section)
        region = empty.layout.get('body').clip
        if self.section in self.tables:
            table = replace(self.tables[self.section], width=region.width, height=max(0, region.height-1),
                            state=replace(self.tables[self.section].state, focused=self.focus.focused == 'details'))
            self.tables[self.section] = table
            body = ('> ' if self.focus.focused == 'details' else '  ')+SECTIONS[self.section]+' | read only\n'+table.view()
        elif self.section == 6 and self.report:
            body = 'Private local output\n'+visible(self.report.private_output[-8192:])
        else:
            body = 'Enter run | Tab focus | 1-7 section\n'+'\n'.join(visible(json.dumps(v, sort_keys=True)) for v in self.events[-max(0, region.height-2):])
        modal = None
        if self.modal:
            trial = self.report.trials
            modal = ('Promote '+trial.recommendation+'?\nReport '+digest(trial.receipt())[:16]+
                     '\n'+self.focus.indicator('cancel')+' Cancel  '+self.focus.indicator('confirm')+' Confirm\nTab select | Enter choose | Escape cancel')
        status = self.status+(' | '+self.code if self.code else '')+(' | promotion recorded' if self.promotion else '')
        return self.shell.frame(self.width, self.height, body=body, navigation=SECTIONS, selected=self.section,
            status=status, severity='error' if self.status == 'failed' else 'success' if self.status == 'completed' else 'muted',
            commands=commands, modal=modal).buffer


async def run_workbench(*, artifact='', prompt='def solve(a, b):\n    ', database='',
                        checkpoint_database='', checkpoint_root='', messages=None,
                        input_stream=None, output_stream=None, factory=None):
    input_stream = sys.stdin.buffer if input_stream is None else input_stream
    output_stream = sys.stderr if output_stream is None else output_stream
    session = TerminalSession(input_stream, output_stream, options=TerminalOptions(alternate_screen=True))
    if messages is None and (not session.capabilities.raw or not session.capabilities.tty):
        raise ValueError('Interactive mode requires a supported POSIX TTY')
    if bool(checkpoint_database) != bool(checkpoint_root):
        raise ValueError('Select both checkpoint database and artifact root')
    checkpoints = ()
    if checkpoint_database:
        from .checkpoints import CheckpointCollection
        with CheckpointCollection(checkpoint_database, checkpoint_root) as collection:
            checkpoints = collection.page(limit=50)['checkpoints']
    if factory is None:
        async def factory(**options):
            return await run_application_demo(artifact=artifact, prompt=prompt, database=database, **options)
    model = Workbench(factory, database=database, checkpoints=checkpoints, exit_on_completion=messages is not None)
    program = model.program = Program(model, renderer=CellDiffRenderer(), terminal=session,
        input_stream=input_stream, output_stream=output_stream, stream_buffer=32, frame_interval=1/30)
    try:
        await program.run(messages, stop_on_eof=messages is None, commands=[model.start()])
    finally:
        model.settle_outcome()
    return {'schema': 1, 'status': model.status, 'code': model.code,
            'identity_sha256': model.report.identity_sha256 if model.report else None}
