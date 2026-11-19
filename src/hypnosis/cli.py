"""Expose Interface commands; one finite JSON result on stdout."""
import contextlib
import json
import sys

from expose_interface import Interface, UsageError

from .runtime import run_demo


def build_interface():
    app = Interface('hypnosis', description='Bounded harness execution and terminal presentation.')

    @app.command(name='demo')
    async def demo(text: str = 'Hello from Hypnosis.'):
        """Run the deterministic offline producer headlessly."""
        return await run_demo(text)

    @app.command(name='terminal')
    async def terminal(text: str = 'Hello from Hypnosis.'):
        """Open the Carets application on a supported POSIX TTY."""
        from .terminal import run_terminal
        return await run_terminal(text=text)

    return app


def main(argv=None):
    try:
        with contextlib.redirect_stdout(sys.stderr):
            result = build_interface().invoke(argv)
        if result is not None:
            print(json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(',', ':')))
            if result.get('status') != 'completed':
                raise SystemExit(1)
        return 0
    except Exception as error:
        print(json.dumps({'schema': 1, 'status': 'failed', 'error': type(error).__name__}), file=sys.stderr)
        raise SystemExit(2 if isinstance(error, UsageError) else 1) from None
