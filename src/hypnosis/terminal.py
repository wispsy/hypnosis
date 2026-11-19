"""Carets presentation over the same finite harness used by headless commands."""
from dataclasses import dataclass
from contextlib import aclosing
import sys
import unicodedata

from carets import (CellDiffRenderer, Command, CommandErrorMsg, KeyMsg, Msg, Program,
                    TerminalOptions, TerminalSession, WindowSizeMsg, truncate_ansi)

from .runtime import Harness, RunControl, RunEvent, TERMINAL_KINDS, demo_source


def visible(text):
    return ''.join(character if character == '\n' or not unicodedata.category(character).startswith('C')
                   else f'\\x{ord(character):02x}' for character in text)


@dataclass(frozen=True)
class EventMsg(Msg):
    event: RunEvent


class HarnessTerminal:
    def __init__(self, factory, *, harness=None, run_id='terminal', exit_on_completion=False):
        self.factory = factory
        self.harness = harness if harness is not None else Harness()
        self.run_id = run_id
        self.control = RunControl()
        self.program = None
        self.width, self.height = 80, 24
        self.status, self.output, self.code = 'ready', '', ''
        self.exit_on_completion = exit_on_completion
        self.exit_requested = False
        self.command_id = None

    def start(self):
        if self.status != 'ready':
            return None
        self.status = 'running'
        async def produce():
            async with aclosing(self.harness.stream(self.factory, run_id=self.run_id, control=self.control)) as events:
                async for event in events:
                    yield EventMsg(event)
        return Command.stream(produce)

    def update(self, message):
        if isinstance(message, WindowSizeMsg):
            self.width, self.height = max(1, message.width), max(1, message.height)
        elif isinstance(message, KeyMsg):
            if message.key in ('q', 'ctrl-c'):
                if self.status == 'running':
                    self.exit_requested = True
                    self.control.cancel()
                elif self.program is not None:
                    self.program.stop()
            elif message.key == 'c' and self.status == 'running':
                self.control.cancel()
            elif message.key == 'enter':
                return self.start()
        elif isinstance(message, EventMsg):
            event = message.event
            if event.run_id != self.run_id:
                return None
            if event.kind == 'delta':
                self.output = (self.output + visible(event.text))[-4096:]
            elif event.kind in TERMINAL_KINDS:
                self.status, self.code = event.kind, event.code
                if self.program is not None and (self.exit_requested or self.exit_on_completion):
                    self.program.stop()
        elif isinstance(message, CommandErrorMsg):
            self.status, self.code = 'failed', 'command_error'
            if self.program is not None and (self.exit_requested or self.exit_on_completion):
                self.program.stop()

    def view(self):
        header = [f'Hypnosis | {self.status}', 'Enter run | c cancel | q quit']
        if self.code:
            header.append(self.code)
        room = max(0, self.height - len(header))
        lines = header + (self.output.splitlines()[-room:] if room else [])
        return '\n'.join(truncate_ansi(line, self.width) for line in lines[:self.height])


class Renderer:
    def __init__(self, model):
        self.model, self.size, self.renderer = model, None, None

    def render(self, view):
        size = self.model.width, self.model.height
        if size != self.size:
            self.size, self.renderer = size, CellDiffRenderer(*size)
        return self.renderer.render(view)


async def run_terminal(*, text='Hello from Hypnosis.', messages=None, input_stream=None, output_stream=None):
    input_stream = sys.stdin.buffer if input_stream is None else input_stream
    output_stream = sys.stderr if output_stream is None else output_stream
    session = TerminalSession(input_stream, output_stream, options=TerminalOptions(alternate_screen=True))
    if messages is None and (not session.capabilities.raw or not session.capabilities.tty):
        raise ValueError('Interactive mode requires a supported POSIX TTY')
    model = HarnessTerminal(lambda: demo_source(text), exit_on_completion=messages is not None)
    program = model.program = Program(model, renderer=Renderer(model), terminal=session,
        input_stream=input_stream, output_stream=output_stream, stream_buffer=32)
    command = model.start()
    await program.run(messages, stop_on_eof=messages is None, commands=[command])
    return {'schema': 1, 'status': model.status, 'code': model.code}
