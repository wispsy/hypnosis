"""Cooperative token execution outside the terminal event loop."""
import asyncio
from concurrent.futures import ThreadPoolExecutor


def _next(iterator):
    try:
        return True, next(iterator)
    except StopIteration:
        return False, None


async def from_sync(factory):
    """Iterate and close a synchronous source on one owned worker thread.

    Only one next() is in flight. Cancellation waits for that operation before
    closing on the same thread. This is cooperative at token boundaries, not
    forced thread termination or a hard computation deadline.
    """
    loop = asyncio.get_running_loop()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='hypnosis-model')
    iterator, pending = None, None
    try:
        pending = loop.run_in_executor(executor, lambda: iter(factory()))
        iterator = await asyncio.shield(pending)
        pending = None
        while True:
            pending = loop.run_in_executor(executor, _next, iterator)
            available, value = await asyncio.shield(pending)
            pending = None
            if not available:
                break
            yield value
    finally:
        try:
            if pending is not None:
                result = await asyncio.shield(pending)
                if iterator is None:
                    iterator = result
            close = getattr(iterator, 'close', None)
            if close is not None:
                await asyncio.shield(loop.run_in_executor(executor, close))
        finally:
            executor.shutdown(wait=True, cancel_futures=True)


async def model_text(adapter, prompt):
    """Use a configured Thoughtform adapter without importing a model provider."""
    from contextlib import aclosing, closing
    def pieces():
        with closing(adapter.stream(prompt)) as tokens:
            for token in tokens:
                yield token.text
    async with aclosing(from_sync(pieces)) as source:
        async for text in source:
            yield text
