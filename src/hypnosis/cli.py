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

    @app.command(name='prepare')
    def prepare(sources: str, destination: str, documents_per_source: int = 32, max_documents: int = 512):
        """Prepare a finite corpus from an explicitly selected source JSON list."""
        from .data import Source,DataLimits,prepare_corpus
        from .training import _read
        selected=_read(sources,65536)
        if type(selected) is not list or not 1<=len(selected)<=16: raise ValueError('Select a finite source list')
        receipt=prepare_corpus([Source(**value) for value in selected],destination,
            limits=DataLimits(documents_per_source=documents_per_source,max_documents=max_documents))
        return {'status':'completed','corpus':receipt}

    @app.command(name='train')
    def train(corpus: str, destination: str, config: str, parent_artifact: str = '', retry: bool = False):
        """Run or explicitly recover a bounded homegrown training job."""
        from .training import load_job,run_job
        def progress(value): print(json.dumps(value,allow_nan=False),file=sys.stderr,flush=True)
        return run_job(corpus,destination,load_job(config),parent_artifact=parent_artifact or None,
                       retry=retry,observer=progress)

    @app.command(name='train-terminal')
    async def train_terminal(corpus: str, destination: str, config: str, parent_artifact: str = '', retry: bool = False):
        """Run the same job with live Carets progress and cooperative cancellation."""
        from .training import load_job
        from .terminal import run_training_terminal
        return await run_training_terminal(corpus,destination,load_job(config),
            parent_artifact=parent_artifact or None,retry=retry)

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
