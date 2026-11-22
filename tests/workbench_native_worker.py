"""Independent native-TTY application worker for the POSIX qualification test."""
import asyncio
from dataclasses import replace
import sys

from carets import CellDiffRenderer, Program, TerminalSession
from hypnosis.application import run_application_demo
from hypnosis.workbench import Workbench


class Session(TerminalSession):
    def start(self, program):
        super().start(program)
        print('READY', flush=True)


async def main():
    report = await run_application_demo()
    async def factory(*, observer, stop):
        while not stop():
            await asyncio.sleep(.005)
        return replace(report, status='canceled')
    model = Workbench(factory)
    program = model.program = Program(model, terminal=Session(sys.stdin.buffer, sys.stderr),
        input_stream=sys.stdin.buffer, output_stream=sys.stderr, renderer=CellDiffRenderer())
    await program.run(commands=[model.start()])
    print('DONE:'+model.status, flush=True)


if __name__ == '__main__':
    asyncio.run(main())
