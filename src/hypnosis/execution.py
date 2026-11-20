"""Cooperative token execution outside the terminal event loop."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
from threading import Event


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
                try:
                    result = await asyncio.shield(pending)
                except Exception:
                    # The original factory/next exception is already leaving
                    # the try body. Still close an acquired iterator below.
                    pass
                else:
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


async def job_progress(job):
    """Run one trusted callback-based job on an owned worker with backpressure.

    The job receives an observer and a cooperative stop predicate. Closing the
    stream requests a saved step boundary, drains pending messages and joins the
    worker. A native optimizer step cannot be forcibly interrupted by this UI.
    """
    loop=asyncio.get_running_loop();queue=asyncio.Queue(maxsize=8);stop=Event()
    executor=ThreadPoolExecutor(max_workers=1,thread_name_prefix='hypnosis-training')
    def emit(value):
        raw=json.dumps(value,sort_keys=True,allow_nan=False,separators=(',',':'))+'\n'
        if len(raw.encode())>8192: raise ValueError('Training progress event is too large')
        asyncio.run_coroutine_threadsafe(queue.put(raw),loop).result()
    def work():
        try:
            result=job(emit,stop.is_set)
            emit({'kind':'outcome','status':result['status']})
            return result
        finally:
            asyncio.run_coroutine_threadsafe(queue.put(None),loop).result()
    future=loop.run_in_executor(executor,work)
    try:
        while True:
            value=await queue.get()
            if value is None: break
            yield value
        await asyncio.shield(future)
    finally:
        stop.set()
        try:
            while not future.done():
                try: await asyncio.wait_for(queue.get(),timeout=0.1)
                except TimeoutError: pass
            await asyncio.shield(future)
        finally:
            executor.shutdown(wait=True,cancel_futures=True)
